#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

from common import (
    configure_logger,
    create_release,
    parse_connection_flags,
    get_username_and_password,
    LaterReleaseUploader,
)
from httpinsdb import InstrumentDB, InstrumentDBError

log = configure_logger()


class Release2021Uploader(LaterReleaseUploader):
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
            year=2021,
            class_uploader=Release2021Uploader,
            release_date="2021-11-03T00:00:00",
            lfi_rimo_version="4.00",
            hfi_rimo_version="4.00",
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
