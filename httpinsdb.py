# -*- encoding: utf-8 -*-
import json
from io import BufferedReader
from pathlib import Path

import requests as req
from typing import Any, Optional

import requests.exceptions
import typing

SERVER_URL = "http://127.0.0.1:8000"


class InstrumentDBError(Exception):
    def __init__(
        self, status_code: int, url: str, message: str, response: req.Response
    ):
        self.status_code = status_code
        self.url = url
        self.message = message
        self.response = response

    def __str__(self):
        return (
            f"HTTP error {self.status_code} from {self.url}: "
            f"{self.message=}, {self.response=}"
        )


def _validate_response_and_return_json(response: req.Response) -> dict[str, Any]:
    """Check that the response is ok; otherwise, raise an InstrumentDBError"""

    if not response.ok:
        raise InstrumentDBError(
            status_code=response.status_code,
            url=response.url,
            message=response.text,
            response=response,
        )

    if response.content == b"":
        return {}

    try:
        return response.json()
    except requests.exceptions.JSONDecodeError as err:
        raise InstrumentDBError(
            status_code=0,
            url=response.url,
            message=f"{response=} returned {err=} with {response.reason=}",
            response=response,
        )


class InstrumentDB:
    """Interact with an InstrumentDB instance

    This class provides a wrapper around the methods implemented in the
    "requests" package. You can use it to POST, GET, and PATCH through
    the RESTful API, but it manages authentication.

    When you create an instance of the class, you must provide the URL
    to the server, the username, and the password; the __init__() method
    will try to log in, and if the process is successful, it will memorize
    the authentication information.

    Once the instance has been initialized, you can use the `.get`,
    `.post`, and `.patch` methods as you wish.
    """

    def __init__(self, server_url: str, username: str, password: str):
        """Initialize a connection with a running InstrumentDB instance

        :param: server_url The URL to the server running InstrumentDB
        :param: username The username to be used for the authentication
        :param: password The password associated with the username
        """

        self.server = server_url

        response = req.post(
            url=f"{server_url}/api/login",
            data={"username": username, "password": password},
        )
        _validate_response_and_return_json(response)

        # This dictionary must be passed as header to all the requests,
        # so we are saving it in a class field
        self.auth_header = {"Authorization": "Token " + response.json()["token"]}

    def post(
        self, url: str, data: dict[str, Any], files: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Send a POST request to the server

        This method should be used to create a *new* object in the database,
        be it a format specification, an entity, a quantity, or a data file.

        If the object requires files to be associated with it (for example,
        a PDF document), you must pass it through the `files` parameter.

        If there is an error connecting to the server, a `InstrumentDBError`
        will be raised.
        """

        response = req.post(
            url=url,
            data=data,
            files={} if files is None else files,
            headers=self.auth_header,
        )
        return _validate_response_and_return_json(response)

    def patch(
        self, url: str, data: dict[str, Any], files: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Send a PATCH request to the server

        This method should be used to modify an existing object in the database.

        If the object requires files to be associated with it (for example,
        a PDF document), you must pass it through the `files` parameter.

        If there is an error connecting to the server, a `InstrumentDBError`
        will be raised.
        """

        response = req.patch(
            url=url,
            data=data,
            files={} if files is None else files,
            headers=self.auth_header,
        )
        return _validate_response_and_return_json(response)

    def get(self, url: str, params={}) -> dict[str, Any]:
        """Send a GET request to the server

        This method should be used to retrieve information about
        one or more objects in the database.

        If the object requires files to be associated with it (for example,
        a PDF document), you must pass it through the `files` parameter.

        If there is an error connecting to the server, a `InstrumentDBError`
        will be raised.
        """

        if url != "" and url[-1] != "/":
            url = url + "/"

        response = req.get(
            url=url,
            headers=self.auth_header,
            params=params,
        )
        return _validate_response_and_return_json(response)

    def delete(self, url: str) -> dict[str, Any]:
        """Send a DELETE request to the server

        This method should be used to remove objects (entities, quantities,
        data files, format specifications) from the database.

        If there is an error connecting to the server, a `InstrumentDBError`
        will be raised.
        """

        response = req.delete(
            url=url,
            headers=self.auth_header,
        )
        return _validate_response_and_return_json(response)

    def create_format_spec(
        self,
        document_ref: str,
        document_title: str,
        document_file: typing.IO,
        document_file_name: str,
        document_mime_type: str,
        file_mime_type: str,
    ) -> str:
        response = self.post(
            url=f"{self.server}/api/format_specs/",
            data={
                "document_ref": document_ref,
                "title": document_title,
                "doc_file_name": document_file_name,
                "doc_mime_type": document_mime_type,
                "file_mime_type": file_mime_type,
            },
            files={
                "doc_file": document_file,
            },
        )
        return response["url"]

    def create_entity(self, name: str, parent_path: str | None = None) -> str:
        data = {"name": name}

        if parent_path is not None:
            response = self.get(
                url=f"{self.server}/tree/{parent_path}",
            )
            data["parent"] = response["url"]

        response = self.post(
            url=f"{self.server}/api/entities/",
            data=data,
        )
        return response["url"]

    def create_quantity(self, name: str, parent_path: str, format_spec_url: str) -> str:
        response = self.get(
            url=f"{self.server}/tree/{parent_path}",
        )
        parent_entity = response["url"]
        data = {
            "name": name,
            "format_spec": format_spec_url,
            "parent_entity": parent_entity,
        }

        response = self.post(
            url=f"{self.server}/api/quantities/",
            data=data,
        )
        return response["url"]

    def create_data_file(
        self,
        quantity: str,
        parent_path: str,
        data_file_path: Path | None = None,
        plot_file_path: Path | None = None,
        plot_file: BufferedReader | None = None,
        plot_file_name: str | None = None,
        plot_mime_type: str | None = None,
        upload_date: str | None = None,
        spec_version: str = "1.0",
        metadata: Any = None,
        comment: str = "",
    ) -> str:
        assert not (
            (plot_file is not None) and (plot_file_path is not None)
        ), "you cannot specify both 'plot_file' and 'plot_file_path'"

        quantity_dict = self.get(url=f"{self.server}/tree/{parent_path}/{quantity}")
        quantity_url = quantity_dict["url"]

        data = {
            "quantity": quantity_url,
            "spec_version": spec_version,
            "comment": comment,
            "name": "file",
        }

        if upload_date is not None:
            data["upload_date"] = upload_date

        if plot_file_name is not None:
            data["plot_file_name"] = plot_file_name

        if plot_mime_type is not None:
            data["plot_mime_type"] = plot_mime_type

        if metadata is not None:
            if isinstance(metadata, str):
                data["metadata"] = metadata
            else:
                data["metadata"] = json.dumps(metadata)

        files = {}

        files_to_close = []
        if data_file_path:
            data["name"] = data_file_path.name
            files["file_data"] = data_file_path.open("rb")
            files_to_close.append(files["file_data"])

        if plot_file:
            files["plot_file"] = plot_file
        elif plot_file_path:
            files["plot_file"] = plot_file_path.open("rb")
            files_to_close.append(files["plot_file"])

        url = f"{self.server}/api/data_files/"
        response = self.post(
            url=url,
            data=data,
            files=files,
        )

        for cur_file in files_to_close:
            # CPython automatically closes files, but this is not
            # the same with PyPy and Jython
            cur_file.close()

        return response["url"]

    def get_data_file_from_release(self, release: str, path: str):
        response = self.get(
            url=f"{self.server}/releases/{release}/{path}/",
        )
        return response["url"]

    def create_release(
        self,
        release_tag: str,
        data_file_url_list: list[str] = [],
        release_date: str | None = None,
        release_document_path: Path | None = None,
        release_document_mime_type: str | None = None,
        comment: str = "",
    ) -> str:
        data = {
            "tag": release_tag,
            "comment": comment,
            "data_files": data_file_url_list,
        }
        files = {}

        if release_date:
            data["rel_date"] = release_date

        if release_document_mime_type:
            data["release_document_mime_type"] = release_document_mime_type

        files_to_close = []
        if release_document_path:
            release_document_file = release_document_path.open("rb")
            files_to_close.append(release_document_file)
            files["release_document"] = release_document_file

        response = self.post(
            url=f"{self.server}/api/releases/",
            data=data,
            files=files,
        )
        release_url = response["url"]

        for cur_file in files_to_close:
            cur_file.close()

        return release_url
