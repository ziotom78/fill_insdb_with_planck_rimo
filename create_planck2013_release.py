#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""Create the Planck 2013 data release

This scripts uses a lot of stuff from the `common.py`
Python file. It creates the nested tree of entries
in InstrumentDB, fills it with quantities, and then
uploads the data files of the Planck 2013 release.
"""

from tempfile import TemporaryFile

from common import (
    configure_logger,
    create_release,
    parse_connection_flags,
    get_username_and_password,
    plot_bandpass,
    HFI_DETECTORS,
    LFI_DETECTORS,
    MOCK_DATA_FOLDER,
    PRE_LAUNCH_FOLDER,
    ReleaseUploader,
    SVG_MIME_TYPE,
)
from httpinsdb import InstrumentDB, InstrumentDBError

log = configure_logger()


REL_2013_DATE = "2013-03-11T00:00:00"


class Release2013Uploader(ReleaseUploader):
    """Class used to upload the Planck 2013 release

    This class inherits `ReleaseUploader` and redefines the `.fill()`
    method
    """

    def fill(self):
        log.info("adding orbital parameters")
        self.add_data_file(
            quantity="orbital_parameters",
            parent_path="payload",
            data_file_path=PRE_LAUNCH_FOLDER / "orbital_parameters.xlsx",
        )

        log.info("adding payload characteristics")
        self.add_data_file(
            quantity="characteristics",
            parent_path="payload",
            data_file_path=PRE_LAUNCH_FOLDER / "satellite-characteristics.xlsx",
        )

        log.info("adding telescope characteristics")
        self.add_data_file(
            quantity="telescope_characteristics",
            parent_path="payload",
            data_file_path=PRE_LAUNCH_FOLDER / "telescope-characteristics.xlsx",
        )

        self.add_focal_plane_information()

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
                cur_data_file_path = (
                    instrument_mock_file_folder / f"bandpass{cur_frequency:03d}.csv"
                )

                with TemporaryFile("wb+") as plot_file:
                    plot_bandpass(
                        data_file_path=cur_data_file_path,
                        output_file=plot_file,
                        image_format="svg",
                        instrument=instrument,
                    )
                    plot_file.seek(0)

                    # Channel-wide bandpass
                    self.add_data_file(
                        quantity="bandpass",
                        parent_path=cur_frequency_path,
                        data_file_path=cur_data_file_path,
                        plot_file=plot_file,
                        plot_mime_type=SVG_MIME_TYPE,
                    )


def main() -> None:
    configuration = parse_connection_flags(
        description="""
Fill the tree of entities with data files
using a running InstrumentDB instance
"""
    )
    log.info('Will connect to "%s"', configuration.server)

    try:
        username, password = get_username_and_password()
        insdb = InstrumentDB(
            server_url=configuration.server,
            username=username,
            password=password,
        )
        del username
        del password

        create_release(
            insdb=insdb,
            year=2013,
            class_uploader=Release2013Uploader,
            release_date=REL_2013_DATE,
            lfi_rimo_version="1.12",
            hfi_rimo_version="1.10",
        )

    except InstrumentDBError as err:
        log.error(
            "error %d from %s",
            err.status_code,
            err.url,
        )
        print(err.message)
        raise


if __name__ == "__main__":
    main()
