#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

"""Create the Planck 2015 data release

This script should be executed *after* a successful completion of
`create_planck2013_release.py`. It uploads data files from the 2015
RIMO files into the tree of entities created for the 2013 data release.
"""

from common import (
    configure_logger,
    create_release,
    parse_connection_flags,
    get_username_and_password,
    LaterReleaseUploader,
)
from httpinsdb import InstrumentDB, InstrumentDBError

log = configure_logger()


class Release2015Uploader(LaterReleaseUploader):
    def fill(self):
        # Add a reference to the planck2013 data files
        self.add_reference_to_payload_files()
        self.add_focal_plane_information()
        self.add_bandpasses()


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
            year=2015,
            class_uploader=Release2015Uploader,
            release_date="2014-11-20T00:00:00",
            lfi_rimo_version="2.50",
            hfi_rimo_version="2.00",
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
