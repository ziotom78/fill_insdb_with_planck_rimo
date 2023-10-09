#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

from pathlib import Path
from typing import Any

from common import (
    configure_logger,
    parse_connection_flags,
    get_username_and_password,
    HFI_DETECTORS,
    LFI_DETECTORS,
)
from libinsdb import RemoteInsDb, InstrumentDbConnectionError


log = configure_logger()


EXCEL_MIME_TYPE = "application/vnd.ms-excel"
JSON_MIME_TYPE = "application/json"
CSV_MIME_TYPE = "text/csv"
TEXT_MIME_TYPE = "text/plain"


def create_frequency_and_detector_entities(
    insdb: RemoteInsDb, instrument: str, detector_dict: dict[int, Any]
) -> None:
    """Create the leaves of the tree associated with frequencies and detectors

    This works for one instrument, so you have to call this twice: once for
    HFI and once for LFI.

    The names of the frequencies are like "frequency_030_ghz", etc., while
    the detectror names are "27M", "1-a", etc.
    """
    for frequency in detector_dict.keys():
        frequency_name = f"frequency_{frequency:03d}_ghz"
        log.info("creating entity '%s' for '%s'", frequency_name, instrument)
        insdb.create_entity(name=frequency_name, parent_path=instrument)

        for detector in detector_dict[frequency]:
            log.info("creating entity '%s' for '%s'", detector, instrument)
            insdb.create_entity(
                name=detector, parent_path=f"{instrument}/{frequency_name}/"
            )


def create_tree_of_entities(insdb: RemoteInsDb) -> None:
    insdb.create_entity(name="payload")

    insdb.create_entity(name="LFI")
    insdb.create_entity(name="cryo_harness", parent_path="LFI")
    create_frequency_and_detector_entities(
        insdb=insdb,
        instrument="LFI",
        detector_dict=LFI_DETECTORS,
    )

    insdb.create_entity(name="HFI")
    create_frequency_and_detector_entities(
        insdb=insdb, instrument="HFI", detector_dict=HFI_DETECTORS
    )


def create_format_spec_and_quantity(
    insdb: RemoteInsDb,
    quantity: str,
    parent_path: str,
    document_file_path: Path,
    document_ref: str,
    document_title: str,
    document_mime_type: str,
    file_mime_type: str,
) -> tuple[str, str]:
    """Create a quantity together with its format specification

    Return a pair of strings containing the URL of the new format specification
    and of the new quantity
    """

    log.info("creating format specification '%s' for '%s'", document_title, quantity)

    with document_file_path.open("rb") as f:
        fmt_spec_url = insdb.create_format_spec(
            document_ref=document_ref,
            document_title=document_title,
            document_file=f,
            document_file_name=document_file_path.name,
            document_mime_type=document_mime_type,
            file_mime_type=file_mime_type,
        )

    log.info("creating quantity '%s'", quantity)

    quantity_url = insdb.create_quantity(
        name=quantity,
        parent_path=parent_path,
        format_spec_url=fmt_spec_url,
    )

    return (fmt_spec_url, quantity_url)


def create_quantities(insdb: RemoteInsDb) -> None:
    format_spec_folder = Path(__file__).parent / "format_specifications"

    create_format_spec_and_quantity(
        insdb=insdb,
        quantity="orbital_parameters",
        parent_path="payload",
        document_file_path=format_spec_folder / "payload_orbital_parameters.txt",
        document_ref="MOCK_DOCUMENT_REF_001",
        document_title="Definition of the orbital parameters",
        document_mime_type=TEXT_MIME_TYPE,
        file_mime_type=EXCEL_MIME_TYPE,
    )

    create_format_spec_and_quantity(
        insdb=insdb,
        quantity="characteristics",
        parent_path="payload",
        document_file_path=format_spec_folder / "payload_characteristics.txt",
        document_ref="MOCK_DOCUMENT_REF_002",
        document_title="Characteristics of the Planck payload",
        document_mime_type=TEXT_MIME_TYPE,
        file_mime_type=JSON_MIME_TYPE,
    )

    create_format_spec_and_quantity(
        insdb=insdb,
        quantity="telescope_characteristics",
        parent_path="payload",
        document_file_path=format_spec_folder / "telescope_characteristics.txt",
        document_ref="MOCK_DOCUMENT_REF_003",
        document_title="Telescope reference frames",
        document_mime_type=TEXT_MIME_TYPE,
        file_mime_type=EXCEL_MIME_TYPE,
    )

    with (format_spec_folder / "bandpasses.txt").open("rb") as f:
        bandpass_format_spec_url = insdb.create_format_spec(
            document_file=f,
            document_ref="MOCK_DOCUMENT_REF_005",
            document_title="Specification of bandpasses for HFI and LFI",
            document_mime_type=TEXT_MIME_TYPE,
            document_file_name="planck_bandpasses.txt",
            file_mime_type=CSV_MIME_TYPE,
        )

    with (format_spec_folder / "rimo.txt").open("rb") as f:
        rimo_format_spec_url = insdb.create_format_spec(
            document_file=f,
            document_ref="MOCK_DOCUMENT_REF_006",
            document_title="Specification of the RIMO for HFI and LFI",
            document_mime_type=TEXT_MIME_TYPE,
            document_file_name="planck_rimo.txt",
            file_mime_type=TEXT_MIME_TYPE,
        )

    with (format_spec_folder / "reduced_focal_plane.txt").open("rb") as f:
        reduced_focal_plane_spec_url = insdb.create_format_spec(
            document_file=f,
            document_ref="MOCK_DOCUMENT_REF_007",
            document_title="Specification of the focal plane (reduced)",
            document_file_name="planck_reduced_focal_plane.txt",
            document_mime_type=TEXT_MIME_TYPE,
            file_mime_type="text/json",
        )

    with (format_spec_folder / "full_focal_plane.txt").open("rb") as f:
        full_focal_plane_spec_url = insdb.create_format_spec(
            document_file=f,
            document_ref="MOCK_DOCUMENT_REF_008",
            document_title="Specification of the focal plane (full)",
            document_file_name="planck_full_focal_plane.txt",
            document_mime_type=TEXT_MIME_TYPE,
            file_mime_type="text/json",
        )

    for instrument, detector_dictionary in [
        ("LFI", LFI_DETECTORS),
        ("HFI", HFI_DETECTORS),
    ]:
        if instrument == "LFI":
            log.info("creating the reduced focal plane for '%s'", instrument)
            insdb.create_quantity(
                name="reduced_focal_plane",
                parent_path=instrument,
                format_spec_url=reduced_focal_plane_spec_url,
            )

        log.info("creating the full focal plane for '%s'", instrument)
        insdb.create_quantity(
            name="full_focal_plane",
            parent_path=instrument,
            format_spec_url=full_focal_plane_spec_url,
        )

        for frequency in detector_dictionary:
            log.info("creating quantities for %s GHz channels", frequency)
            cur_frequency_path = f"{instrument}/frequency_{frequency:03d}_ghz/"
            insdb.create_quantity(
                name="bandpass",
                parent_path=cur_frequency_path,
                format_spec_url=bandpass_format_spec_url,
            )
            insdb.create_quantity(
                name="rimo",
                parent_path=cur_frequency_path,
                format_spec_url=rimo_format_spec_url,
            )

            for detector_name in detector_dictionary[frequency]:
                cur_detector_path = f"{cur_frequency_path}/{detector_name}/"
                insdb.create_quantity(
                    name="bandpass",
                    parent_path=cur_detector_path,
                    format_spec_url=bandpass_format_spec_url,
                )

                cur_detector_path = f"{cur_frequency_path}/{detector_name}/"
                insdb.create_quantity(
                    name="rimo",
                    parent_path=cur_detector_path,
                    format_spec_url=rimo_format_spec_url,
                )


def main() -> None:
    configuration = parse_connection_flags(
        description="""
Create the tree of entities and quantities
using a running RemoteInsDb instance
"""
    )
    log.info('Will connect to "%s"', configuration.server)

    try:
        username, password = get_username_and_password()
        insdb = RemoteInsDb(
            server_address=configuration.server,
            username=username,
            password=password,
        )
        del username
        del password

        create_tree_of_entities(insdb=insdb)
        create_quantities(insdb=insdb)
    except InstrumentDbConnectionError as err:
        log.error(
            "error %d from %s: %s",
            err.response.status_code,
            err.url,
            err.message,
        )
        raise


if __name__ == "__main__":
    main()
