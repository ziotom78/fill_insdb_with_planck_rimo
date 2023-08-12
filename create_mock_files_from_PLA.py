#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

from argparse import ArgumentParser
from dataclasses import dataclass

import pandas as pd
from pathlib import Path
import re

from astropy.io import fits  # type: ignore
import requests as req

from common import (
    configure_logger,
    HFI_BANDPASS_FREQ_LABEL,
    MOCK_DATA_FOLDER,
    PLA_DATA_FOLDER,
    RIMO_FILES,
    LFI_BANDPASS_FREQ_LABEL,
)

log = configure_logger()


@dataclass
class Configuration:
    force_pla_file_overwrite: bool


def parse_command_line() -> Configuration:
    parser = ArgumentParser(
        description="""
Use the Planck Legacy Archive as a reference to build
a set of data files that will be uploaded to InstrumentDB""",
        epilog="""
This script does not communicate with InstrumentBD. Its only
purpose is to download data and prepare the files that will be
uploaded to InstrumentDB. Use the two scripts `create_tree.py`
and `populate_tree.py` to do the actual upload.""",
    )

    parser.add_argument(
        "--force-download",
        action="store_true",
        help="""
Force the program to download the data files from the
PLA, even if they are already present in the folder
{pla_folder}""".format(
            pla_folder=PLA_DATA_FOLDER
        ),
    )

    args = parser.parse_args()
    return Configuration(
        force_pla_file_overwrite=args.force_download,
    )


def download_pla_files(conf: Configuration) -> None:
    """Download the RIMO files from the Planck Legacy Archive

    The `conf` parameter is an instance of the `Configuration` class
    that should have been created using `parse_command_line()`.
    """

    PLA_DATA_FOLDER.mkdir(exist_ok=True)

    for cur_rimo_file in RIMO_FILES:
        if conf.force_pla_file_overwrite or (not cur_rimo_file.path.exists()):
            # See the section “Machine interface” of the Planck Legacy Archive
            # to understand the format of this URL:
            # https://pla.esac.esa.int/#aio

            cur_url = (
                "http://pla.esac.esa.int/pla/aio/product-action?DOCUMENT.DOCUMENT_ID="
                + cur_rimo_file.path.name
            )
            response = req.get(cur_url)

            with cur_rimo_file.path.open("wb") as output_file:
                log.info(
                    "saving PLA file '%s' into '%s'",
                    cur_rimo_file.path,
                    PLA_DATA_FOLDER.name,
                )
                output_file.write(response.content)
        else:
            log.debug(
                "skipping downloading '%s' as it is already present locally in '%s'",
                cur_rimo_file.path.name,
                PLA_DATA_FOLDER.name,
            )


def create_mock_folder_tree():
    # Create the tree of folders that will contain the mock data:
    #
    # mock_data
    # |
    # +--- LFI
    # |    +--- 1.10
    # |    ⋮
    # |
    # +--- HFI
    #      |
    #      +--- 1.12
    #      ⋮

    MOCK_DATA_FOLDER.mkdir(exist_ok=True)

    for cur_rimo_file in RIMO_FILES:
        cur_instrument = cur_rimo_file.instrument
        cur_version = cur_rimo_file.version

        version_path = MOCK_DATA_FOLDER / cur_instrument / cur_version
        version_path.mkdir(exist_ok=True, parents=True)


def find_rimo(instrument: str, version: str) -> Path:
    """Return the local path to the matching RIMO file

    Raise a `ValueError` exception if no match is found.
    """

    for cur_rimo_file in RIMO_FILES:
        if cur_rimo_file.instrument == instrument and cur_rimo_file.version == version:
            return cur_rimo_file.path

    raise ValueError(f"unable to find a RIMO matching {instrument=} and {version=}")


def retrieve_ellipticity(data):
    # Some versions of the HFI RIMO use "ELLIPTICITY",
    # others use "ELLIPTIC"… ☹
    try:
        return data["ELLIPTICITY"]
    except KeyError:
        return data["ELLIPTIC"]


def save_hfi_focal_plane_to_json(hdu: fits.BinTableHDU, output_file_path: Path):
    detector_parameters = hdu.data
    detector_parameters_df = pd.DataFrame(
        {
            "detector": detector_parameters["DETECTOR"],
            "phi_uv_deg": detector_parameters["PHI_UV"],
            "theta_uv_deg": detector_parameters["THETA_UV"],
            "psi_uv_deg": detector_parameters["PSI_UV"],
            "psi_pol_deg": detector_parameters["PSI_POL"],
            "epsilon": detector_parameters["EPSILON"],
            "fwhm": detector_parameters["FWHM"],
            "ellipticity": retrieve_ellipticity(detector_parameters),
        }
    )
    detector_parameters_df.index = detector_parameters["DETECTOR"]

    detector_parameters_df.transpose().to_json(output_file_path)


def save_bandpass_to_csv(
    hdu: fits.BinTableHDU,
    output_file_path: Path,
    instrument: str,
) -> None:
    wavenumber_key = {"LFI": "wavenumber_ghz", "HFI": "wavenumber_invcm"}
    data_dict = {
        wavenumber_key[instrument]: hdu.data["WAVENUMBER"],
        "transmission": hdu.data["TRANSMISSION"],
    }

    try:
        data_dict["uncertainty"] = hdu.data["UNCERTAINTY"]
    except KeyError:
        # HFI RIMO V3.00 does not contain the "UNCERTAINTY" column
        data_dict["uncertainty"] = data_dict["transmission"] * 0.0

    cur_bandpass = pd.DataFrame(data_dict)

    cur_bandpass.to_csv(output_file_path)


def save_channel_bandpasses(
    input_file,
    output_path: Path,
    freq_label: list[str],
    instrument: str,
) -> None:
    for cur_frequency in freq_label:
        if cur_frequency.startswith("F"):
            # HFI frequencies start with an "F"
            cur_freq_value = int(cur_frequency[1:])
        else:
            cur_freq_value = int(cur_frequency)

        output_file_path = output_path / f"bandpass{cur_freq_value:03d}.csv"
        save_bandpass_to_csv(
            hdu=input_file[f"BANDPASS_{cur_frequency}"],
            output_file_path=output_file_path,
            instrument=instrument,
        )
        log.info(
            "bandpass '%s' detectors saved in '%s'",
            cur_frequency,
            output_file_path,
        )


def save_detector_bandpasses(
    input_file,
    output_path: Path,
    regexp: str,
) -> None:
    name_regexp = re.compile(regexp)
    for cur_hdu in input_file:
        if match_obj := name_regexp.fullmatch(cur_hdu.name):
            det_name = match_obj.group(1)
            output_file_path = output_path / f"bandpass_detector_{det_name}.csv"
            save_bandpass_to_csv(
                hdu=cur_hdu,
                output_file_path=output_file_path,
                instrument="HFI",
            )
            log.info(
                "bandpass for HFI detector '%s' saved in '%s'",
                det_name,
                output_file_path,
            )


def create_hfi_mock_files(version: str) -> None:
    log.info("Processing HFI RIMO %s", version)
    with fits.open(find_rimo(instrument="HFI", version=version)) as input_file:
        # Depending on the version of the HFI RIMO file:
        #
        # 1. The focal plane description might not be present
        # 2. It could be in "DET_PARAMS"
        # 3. It could be in "CHANNEL PARAMETERS"
        #
        # This code should handle correctly all the cases
        for focal_plane_key in ["DET_PARAMS", "CHANNEL PARAMETERS"]:
            if focal_plane_key not in input_file:
                continue
            output_file_path = MOCK_DATA_FOLDER / "HFI" / version / "focal_plane.json"
            save_hfi_focal_plane_to_json(
                hdu=input_file[focal_plane_key],
                output_file_path=output_file_path,
            )
            log.info("focal plane information saved in '%s'", output_file_path)

        save_channel_bandpasses(
            input_file=input_file,
            output_path=MOCK_DATA_FOLDER / "HFI" / version,
            freq_label=HFI_BANDPASS_FREQ_LABEL,
            instrument="HFI",
        )

        save_detector_bandpasses(
            input_file=input_file,
            output_path=MOCK_DATA_FOLDER / "HFI" / version,
            regexp=r"BANDPASS_([0-9][0-9][0-9]-.*)",
        )


def create_hfi_110_mock_files():
    create_hfi_mock_files(version="1.10")


def create_hfi_200_mock_files():
    create_hfi_mock_files(version="2.00")


def create_hfi_300_mock_files():
    create_hfi_mock_files(version="3.00")


def create_hfi_400_mock_files():
    create_hfi_mock_files(version="4.00")


def save_lfi_reduced_focal_plane_to_json(
    hdu: fits.BinTableHDU, output_file_path: Path
) -> None:
    focal_plane_df = pd.DataFrame(
        {
            "frequency": [x[0] for x in hdu.data["FREQUENCY"]],
            "fwhm": hdu.data["FWHM"],
            "noise": hdu.data["NOISE"],
            "centralfreq": hdu.data["CENTRALFREQ"],
            "fwhm_eff": hdu.data["FWHM_EFF"],
            "fwhm_eff_sigma": hdu.data["FWHM_EFF_SIGMA"],
            "ellipticity_eff": hdu.data["ELLIPTICITY_EFF"],
            "ellipticity_eff_sigma": hdu.data["ELLIPTICITY_EFF_SIGMA"],
            "solid_angle_eff": hdu.data["SOLID_ANGLE_EFF"],
            "solid_angle_eff_sigma": hdu.data["SOLID_ANGLE_EFF_SIGMA"],
        }
    )
    focal_plane_df.index = pd.Index(focal_plane_df["frequency"])
    focal_plane_df.transpose().to_json(output_file_path)


def save_lfi_full_focal_plane_to_json(
    hdu: fits.BinTableHDU, output_file_path: Path
) -> None:
    focal_plane_df = pd.DataFrame(
        {
            "detector": [x[0] for x in hdu.data["detector"]],
            "phi_uv_deg": hdu.data["PHI_UV"],
            "theta_uv_deg": hdu.data["THETA_UV"],
            "psi_uv_deg": hdu.data["PSI_UV"],
            "psi_pol_deg": hdu.data["PSI_POL"],
            "epsilon": hdu.data["EPSILON"],
            "fwhm_arcmin": hdu.data["FWHM"],
            "ellipticity": hdu.data["ELLIPTICITY"],
        }
    )
    focal_plane_df.index = pd.Index(focal_plane_df["detector"])
    focal_plane_df.transpose().to_json(output_file_path)


def create_lfi_mock_files(version: str) -> None:
    log.info("Processing LFI RIMO %s", version)

    with fits.open(find_rimo(instrument="LFI", version=version)) as input_file:
        output_file_path = (
            MOCK_DATA_FOLDER / "LFI" / version / "reduced_focal_plane.json"
        )
        save_lfi_reduced_focal_plane_to_json(
            hdu=input_file["FREQUENCY_MAP_PARAMETERS"],
            output_file_path=output_file_path,
        )
        log.info("reduced focal plane information saved in '%s'", output_file_path)

        if "CHANNEL_PARAMETERS" in input_file:
            output_file_path = (
                MOCK_DATA_FOLDER / "LFI" / version / "full_focal_plane.json"
            )
            save_lfi_full_focal_plane_to_json(
                hdu=input_file["CHANNEL_PARAMETERS"],
                output_file_path=output_file_path,
            )
            log.info("full focal plane information saved in '%s'", output_file_path)

        save_channel_bandpasses(
            input_file=input_file,
            output_path=MOCK_DATA_FOLDER / "LFI" / version,
            freq_label=LFI_BANDPASS_FREQ_LABEL,
            instrument="LFI",
        )

        save_detector_bandpasses(
            input_file=input_file,
            output_path=MOCK_DATA_FOLDER / "LFI" / version,
            regexp=r"BANDPASS_[0-9][0-9][0-9]-([0-9][0-9][MS])",
        )


def create_lfi_112_mock_files() -> None:
    create_lfi_mock_files(version="1.12")


def create_lfi_250_mock_files() -> None:
    create_lfi_mock_files(version="2.50")


def create_lfi_331_mock_files() -> None:
    create_lfi_mock_files(version="3.31")


def create_lfi_400_mock_files() -> None:
    create_lfi_mock_files(version="4.00")


def create_mock_files():
    create_mock_folder_tree()

    create_hfi_110_mock_files()
    create_hfi_200_mock_files()
    create_hfi_300_mock_files()
    create_hfi_400_mock_files()

    create_lfi_112_mock_files()
    create_lfi_250_mock_files()
    create_lfi_331_mock_files()
    create_lfi_400_mock_files()


def main() -> None:
    conf = parse_command_line()

    log.info("checking if the PLA RIMO files are available")
    download_pla_files(conf=conf)

    log.info("creating mock files")
    create_mock_files()

    log.info("done, the files are available in '%s'", MOCK_DATA_FOLDER)


if __name__ == "__main__":
    main()
