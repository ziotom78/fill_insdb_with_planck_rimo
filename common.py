# -*- encoding: utf-8 -*-

from argparse import ArgumentParser
from dataclasses import dataclass
from io import BufferedReader
from pathlib import Path
from tempfile import TemporaryFile
from typing import Any

import typing

from httpinsdb import InstrumentDB

# MIME type used for the bandpass plots
SVG_MIME_TYPE = "image/svg+xml"

DEFAULT_SERVER = "http://localhost:8000"
PLA_DATA_FOLDER = Path(__file__).parent / "pla_data"
MOCK_DATA_FOLDER = Path(__file__).parent / "mock_data"
PRE_LAUNCH_FOLDER = Path(__file__).parent / "pre_launch"
RELEASE_DOCUMENT_PATH = Path(__file__).parent / "release_documents"

HFI_DETECTORS = {
    100: sorted([f"{num}-{pol}" for num in (1, 2, 3, 4) for pol in ("a", "b")]),
    143: sorted([f"{num}-{pol}" for num in (1, 2, 3, 4) for pol in ("a", "b")]),
    217: ["1", "2", "3", "4"],
    353: (
        ["1", "2", "7", "8"]
        + sorted([f"{num}-{pol}" for num in (3, 4, 5, 6) for pol in ("a", "b")])
    ),
    545: ["1", "2", "3", "4"],
    857: ["1", "2", "3", "4"],
}
HFI_FREQUENCIES = list(HFI_DETECTORS.keys())

LFI_DETECTORS = {
    30: sorted([f"{num}{arm}" for num in range(27, 28 + 1) for arm in ("M", "S")]),
    44: sorted([f"{num}{arm}" for num in range(24, 26 + 1) for arm in ("M", "S")]),
    70: sorted([f"{num}{arm}" for num in range(18, 23 + 1) for arm in ("M", "S")]),
}
LFI_FREQUENCIES = list(LFI_DETECTORS.keys())

HFI_BANDPASS_FREQ_LABEL = ["F100", "F143", "F217", "F353", "F545", "F857"]
LFI_BANDPASS_FREQ_LABEL = ["030", "044", "070"]


@dataclass
class RimoFile:
    path: Path
    instrument: str
    version: str


RIMO_FILES: list[RimoFile] = [
    RimoFile(
        path=PLA_DATA_FOLDER / "HFI_RIMO_R1.10.fits", instrument="HFI", version="1.10"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "HFI_RIMO_R2.00.fits", instrument="HFI", version="2.00"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "HFI_RIMO_R3.00.fits", instrument="HFI", version="3.00"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "HFI_RIMO_R4.00.fits", instrument="HFI", version="4.00"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "LFI_RIMO_R1.12.fits", instrument="LFI", version="1.12"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "LFI_RIMO_R2.50.fits", instrument="LFI", version="2.50"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "LFI_RIMO_R3.31.fits", instrument="LFI", version="3.31"
    ),
    RimoFile(
        path=PLA_DATA_FOLDER / "LFI_RIMO_R4.00.fits", instrument="LFI", version="4.00"
    ),
]


def configure_logger():
    """Configure a logging object using Rich"""

    import logging
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler()]
    )
    return logging.getLogger("rich")


@dataclass
class ConnectionConfiguration:
    server: str


def parse_connection_flags(description: str) -> ConnectionConfiguration:
    parser = ArgumentParser(description=description)
    parser.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"The address of the server. The default is {DEFAULT_SERVER}",
    )

    parsed_args = parser.parse_args()

    return ConnectionConfiguration(
        server=parsed_args.server,
    )


def get_username_and_password() -> tuple[str, str]:
    import configparser

    conf = configparser.ConfigParser()
    conf.read(Path(__file__).parent / "credentials.ini")

    return (conf["Authentication"]["username"], conf["Authentication"]["password"])


def plot_bandpass(
    data_file_path: Path, output_file: typing.IO, image_format: str, instrument: str
) -> None:
    from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas  # type: ignore
    from matplotlib.figure import Figure  # type: ignore
    import pandas as pd

    fig = Figure()
    canvas = FigureCanvas(fig)
    ax = fig.add_subplot(111)

    if instrument == "LFI":
        ax.set_xlabel("Frequency [GHz]")
    else:
        ax.set_xlabel("Wavenumber [cm⁻¹]")

    ax.set_ylabel("Transmission")

    data = pd.read_csv(
        data_file_path, header=0, names=["index", "wavelength", "transmission", "error"]
    )
    ax.plot(data["wavelength"], data["transmission"])
    fig.set_size_inches(8, 5)
    fig.set_dpi(150)

    canvas.print_figure(output_file, format=image_format)


log = configure_logger()


class ReleaseUploader:
    """Class used to upload an entire release

    The class manages the connection to a `InstrumentDB` instance
    and keeps track of all the data files that have been uploaded.

    The way you are supposed to use this class is the following:

    1. Create a new class that inherits from `ReleaseUploader`
    2. Override the `.fill()` method
    3. In your script, create an instance of your inherited class
    4. Invoke the method `.create_release()`
    """

    def __init__(
        self,
        insdb: InstrumentDB,
        release_tag: str,
        release_date: str,
        release_document_path: Path,
        release_comment: str,
        lfi_rimo_version: str,
        hfi_rimo_version: str,
    ):
        self.insdb = insdb
        self.release_tag = release_tag
        self.release_date = release_date
        self.data_file_urls = []  # type: list[str]
        self.release_document_path = release_document_path
        self.release_comment = release_comment
        self.lfi_rimo_version = lfi_rimo_version
        self.hfi_rimo_version = hfi_rimo_version

    def prepare_release(self):
        log.info(
            "creating release [bold]%s[/bold]", self.release_tag, extra={"markup": True}
        )

    def finish_release(self):
        log.info(
            "finalizing release [bold]%s[/bold]",
            self.release_tag,
            extra={"markup": True},
        )
        self.insdb.create_release(
            release_tag=self.release_tag,
            data_file_url_list=self.data_file_urls,
            release_date=self.release_date,
            release_document_path=self.release_document_path,
            release_document_mime_type="text/plain",
            comment=self.release_comment,
        )

    def add_data_file(
        self,
        quantity: str,
        parent_path: str,
        data_file_path: Path | None = None,
        metadata: Any = None,
        plot_file: BufferedReader | None = None,
        plot_mime_type: str | None = None,
    ):
        """Add a new data file to the current release"""
        self.data_file_urls.append(
            self.insdb.create_data_file(
                quantity=quantity,
                parent_path=parent_path,
                data_file_path=data_file_path,
                upload_date=self.release_date,
                metadata=metadata,
                plot_file=plot_file,
                plot_mime_type=plot_mime_type,
            )
        )

    def add_data_file_reference(self, release: str, path: str):
        """Add to the current release a reference to an older data file"""
        self.data_file_urls.append(
            self.insdb.get_data_file_from_release(
                release=release,
                path=path,
            )
        )

    def fill(self):
        pass

    def create_release(self):
        self.prepare_release()
        self.fill()
        self.finish_release()

    def add_focal_plane_information(self):
        log.info("adding focal plane characteristics")

        for instrument, rimo_version, file_name, quantity in [
            (
                "LFI",
                self.lfi_rimo_version,
                "reduced_focal_plane.json",
                "reduced_focal_plane",
            ),
            ("LFI", self.lfi_rimo_version, "full_focal_plane.json", "full_focal_plane"),
            ("HFI", self.hfi_rimo_version, "focal_plane.json", "full_focal_plane"),
        ]:
            cur_file_path = MOCK_DATA_FOLDER / instrument / rimo_version / file_name
            try:
                with cur_file_path.open("rt") as inpf:
                    self.add_data_file(
                        quantity=quantity,
                        parent_path=instrument,
                        metadata="".join(inpf.readlines()),
                    )
            except FileNotFoundError:
                # HFI RIMO 2013 and 2018 do not have a focal plane specification
                pass


class LaterReleaseUploader(ReleaseUploader):
    def add_reference_to_payload_files(self):
        # Nothing was changed for the payload files, as they contain
        # measurements done before the launch

        self.add_data_file_reference(
            release="planck2013",
            path="payload/orbital_parameters",
        )

        self.add_data_file_reference(
            release="planck2013",
            path="payload/characteristics",
        )

        self.add_data_file_reference(
            release="planck2013",
            path="payload/telescope_characteristics",
        )

    def add_bandpasses(self):
        for instrument, rimo_version, detectors_dict in [
            ("LFI", self.lfi_rimo_version, LFI_DETECTORS),
            ("HFI", self.hfi_rimo_version, HFI_DETECTORS),
        ]:
            instrument_mock_file_folder = MOCK_DATA_FOLDER / instrument / rimo_version
            for cur_frequency in detectors_dict.keys():
                log.info(
                    "adding bandpasses for %s at %d GHz", instrument, cur_frequency
                )
                cur_frequency_path = f"{instrument}/frequency_{cur_frequency:03d}_ghz/"

                # Channel-wide bandpass
                with TemporaryFile("wb+") as plot_file:
                    cur_data_file_path = (
                        instrument_mock_file_folder / f"bandpass{cur_frequency:03d}.csv"
                    )
                    plot_bandpass(
                        data_file_path=cur_data_file_path,
                        output_file=plot_file,
                        image_format="svg",
                        instrument=instrument,
                    )
                    plot_file.seek(0)

                    self.add_data_file(
                        quantity="bandpass",
                        parent_path=cur_frequency_path,
                        data_file_path=cur_data_file_path,
                        plot_file=plot_file,
                        plot_mime_type=SVG_MIME_TYPE,
                    )

                # Detector bandpasses
                for cur_detector in detectors_dict[cur_frequency]:
                    if instrument == "LFI":
                        file_name = f"bandpass_detector_{cur_detector}.csv"
                    else:
                        short_name = cur_detector.replace("-", "").upper()
                        file_name = (
                            f"bandpass_detector_{cur_frequency}-{short_name}.csv"
                        )

                    cur_data_file_path = instrument_mock_file_folder / file_name
                    try:
                        with TemporaryFile("wb+") as plot_file:
                            plot_bandpass(
                                data_file_path=cur_data_file_path,
                                output_file=plot_file,
                                image_format="svg",
                                instrument=instrument,
                            )
                            plot_file.seek(0)

                            self.add_data_file(
                                quantity="bandpass",
                                parent_path=f"{cur_frequency_path}{cur_detector}/",
                                data_file_path=cur_data_file_path,
                                plot_mime_type=SVG_MIME_TYPE,
                            )
                    except FileNotFoundError:
                        # HFI release 3.00 does not contain detector bandpasses
                        pass


def create_release(
    insdb: InstrumentDB,
    class_uploader,
    year: int,
    release_date: str,
    lfi_rimo_version: str,
    hfi_rimo_version: str,
) -> None:
    cur_release = class_uploader(
        insdb=insdb,
        release_tag=f"planck{year}",
        release_date=release_date,
        release_document_path=RELEASE_DOCUMENT_PATH / f"planck{year}.txt",
        release_comment=f"Instrument specification for the Planck {year} data release",
        lfi_rimo_version=lfi_rimo_version,
        hfi_rimo_version=hfi_rimo_version,
    )
    cur_release.create_release()
