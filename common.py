# -*- encoding: utf-8 -*-

"""Common functions and classes used by multiple scripts

In this file we save all the functions and classes that
are used by more than one script.
"""

from argparse import ArgumentParser
from dataclasses import dataclass
from io import BufferedReader
from pathlib import Path
from tempfile import TemporaryFile
from typing import Any

import typing

from httpinsdb import InstrumentDB, InstrumentDBError

# MIME type used for the bandpass plots
SVG_MIME_TYPE = "image/svg+xml"

# By default, we always connect to a local instance
# of the InstrumentDB database
DEFAULT_SERVER = "http://localhost:8000"

# These are all sub-folders within this repository.
# A few of them do not exist once the repository has
# been cloned (e.g., `mock_data`): they will be created
# automatically
PLA_DATA_FOLDER = Path(__file__).parent / "pla_data"
MOCK_DATA_FOLDER = Path(__file__).parent / "mock_data"
PRE_LAUNCH_FOLDER = Path(__file__).parent / "pre_launch"
RELEASE_DOCUMENT_PATH = Path(__file__).parent / "release_documents"

# Dictionary associating a frequency number with the name of the detectors
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

# The same for LFI
LFI_DETECTORS = {
    30: sorted([f"{num}{arm}" for num in range(27, 28 + 1) for arm in ("M", "S")]),
    44: sorted([f"{num}{arm}" for num in range(24, 26 + 1) for arm in ("M", "S")]),
    70: sorted([f"{num}{arm}" for num in range(18, 23 + 1) for arm in ("M", "S")]),
}
LFI_FREQUENCIES = list(LFI_DETECTORS.keys())

# These are the labels used to identify frequencies in the RIMO files.
# Alas, their format differ between HFI and LFI!
HFI_BANDPASS_FREQ_LABEL = ["F100", "F143", "F217", "F353", "F545", "F857"]
LFI_BANDPASS_FREQ_LABEL = ["030", "044", "070"]


@dataclass
class RimoFile:
    """Details about a RIMO file downloaded from the PLA"""

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
    """Connection settings specified through the command line"""

    server: str


def parse_connection_flags(description: str) -> ConnectionConfiguration:
    """Read connection configuration from the command line"""

    # In a real-world case, this code would probably have been
    # originally put in create_planck2013_release.py. Then, once
    # release 2015 was being prepared, the code was moved in
    # `common.py` because the authors realized that it could have
    # been reused without changes for the newer release.

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
    """Read username and password for InstrumentDB from file `credentials.ini`"""

    import configparser

    conf = configparser.ConfigParser()
    conf.read(Path(__file__).parent / "credentials.ini")

    return (conf["Authentication"]["username"], conf["Authentication"]["password"])


def plot_bandpass(
    data_file_path: Path, output_file: typing.IO, image_format: str, instrument: str
) -> None:
    """Use Matplotlib to create a plot of a bandpass

    The plot is saved in SVG format and uploaded to InstrumentDB.
    """

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


# We need an instance of `log` in the implementation
# of the classe `ReleaseUploader` (see below)
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

    def prepare_release(self) -> None:
        """Prepare stuff before uploading data files for a new release

        This code is executed *before* the data files of the new release
        are actually being uploded. The purpose of this method is to
        check that the release was not already uploaded by mistake and
        to inform the user that the upload is going to start.
        """

        # Check that the release was not already uploaded
        try:
            self.insdb.get(url=f"{self.insdb.server}/api/releases/{self.release_tag}")

            # If we reach this line, it means that the GET
            # request got completed successfully, and thus
            # that the release is already present
            raise ValueError(
                f"error, release {self.release_tag} is already present in the database"
            )
        except InstrumentDBError as err:
            if err.status_code == 404:  # HTTP 404: not found
                # That's ok, we're happy that this release is not found
                pass
            else:
                # Something else went wrong: propagate the exception
                raise

        log.info(
            "creating release [bold]%s[/bold]", self.release_tag, extra={"markup": True}
        )

    def finish_release(self) -> None:
        """This method is called once the new data files have been uploaded"""

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
        """Add a new data file to the current release

        This is a wrapper around the InstrumentDB.create_data_file method.
        It keeps a list of the URLs of the data files that have been
        successfully uploaded, so that the method `.finish_release()`
        will be able to tag the new release.
        """

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
        """Add to the current release a reference to an older data file

        This method is used whenever a new release references
        a file from an older release instead of uploading a new
        version of it. This is the case of the Excel file containing
        the telescope caracteristics, for example."""

        self.data_file_urls.append(
            self.insdb.get_data_file_from_release(
                release=release,
                path=path,
            )
        )

    def fill(self) -> None:
        """Upload the data files"""

        # Of course, we have nothing to do here! The method `.fill`
        # is meant to be overridden by derived classes
        pass

    def create_release(self) -> None:
        """Create the new release"""

        self.prepare_release()
        self.fill()
        self.finish_release()

    def add_focal_plane_information(self):
        """Upload focal plane information to the InstrumentDB database

        This function was originally part of the script
        `create_planck2013_release.py`. It was moved here
        once the Planck team realized that the code would
        have been exactly the same for the 2015, 2018,
        and 2021 releases.
        """

        log.info("adding focal plane characteristics")

        # We must perform *three* uploads:
        # 1. The LFI “reduced” data file, containing just the 30, 44, and 70 GHJz focal
        #    plane parameters
        # 2. The LFI “full” data file
        # 3. The HFI data file, whose structure is the same as the LFI “full” data file
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
    """Class to upload files from the 2015, 2018, and 2021 data releases

    Once the `create_planck2015_release.py` was created, the Planck
    team realized that `create_planck2018_release.py` would have
    shared several methods, which were however *not* needed for
    the 2013 data release. Thus, they decided to move those parts of
    the code in this class, which is used as the ancestor for
    the classes `Release2015Uploader`, `Release2018Uploader`,
    and `Release2021Uploader`.
    """

    def add_reference_to_payload_files(self):
        """Add references to the payload files in the current release"""

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
    """Use an instance of a `Release*Uploader` class to create a new release"""

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
