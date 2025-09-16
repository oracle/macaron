# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes utilities functions for Macaron."""

import logging
import os
import shutil
import time
import urllib.parse
from collections.abc import Callable
from datetime import datetime
from typing import BinaryIO

import requests
from requests.models import Response

from macaron.config.defaults import defaults

logger: logging.Logger = logging.getLogger(__name__)


def send_get_http(url: str, headers: dict) -> dict:
    """Send the GET HTTP request with the given url and headers.

    This method also handle logging when the server return error status code.

    Parameters
    ----------
    url : str
        The url of the request.
    headers : dict
        The dictionary to be included as the header of the request.

    Returns
    -------
    dict
        The response's json data or an empty dict if there is an error.
    """
    logger.debug("GET - %s", url)
    timeout = defaults.getint("requests", "timeout", fallback=10)
    error_retries = defaults.getint("requests", "error_retries", fallback=5)
    retry_counter = error_retries
    response = requests.get(url=url, headers=headers, timeout=timeout)
    while response.status_code != 200:
        logger.error(
            "Receiving error code %s from server. Message: %s.",
            response.status_code,
            response.text,
        )
        if retry_counter <= 0:
            logger.debug("Maximum retries reached: %s", error_retries)
            return {}
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return {}
        retry_counter = retry_counter - 1
        response = requests.get(url=url, headers=headers, timeout=timeout)

    return dict(response.json())


def send_head_http_raw(
    url: str, headers: dict | None = None, timeout: int | None = None, allow_redirects: bool = True
) -> Response | None:
    """Send the HEAD HTTP request with the given url and headers.

    This method also handle logging when the API server return error status code.

    Parameters
    ----------
    url : str
        The url of the request.
    headers : dict | None
        The dict that describes the headers of the request.
    timeout: int | None
        The request timeout (optional).
    allow_redirects: bool
        Whether to allow redirects. Default: True.

    Returns
    -------
    Response | None
        If a Response object is returned and ``allow_redirects`` is ``True`` (the default) it will have a status code of
        200 (OK). If ``allow_redirects`` is ``False`` the response can instead have a status code of 302. Otherwise, the
        request has failed and ``None`` will be returned.
    """
    logger.debug("HEAD - %s", url)
    if not timeout:
        timeout = defaults.getint("requests", "timeout", fallback=10)
    error_retries = defaults.getint("requests", "error_retries", fallback=5)
    retry_counter = error_retries
    try:
        response = requests.head(
            url=url,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )
    except requests.exceptions.RequestException as error:
        logger.debug(error)
        return None
    if not allow_redirects and response.status_code == 302:
        # Found, most likely because a redirect is about to happen.
        return response
    while response.status_code != 200:
        logger.debug(
            "Receiving error code %s from server.",
            response.status_code,
        )
        if retry_counter <= 0:
            logger.debug("Maximum retries reached: %s", error_retries)
            return None
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return None
        retry_counter = retry_counter - 1
        response = requests.head(
            url=url,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

    return response


def send_get_http_raw(
    url: str,
    headers: dict | None = None,
    timeout: int | None = None,
    allow_redirects: bool = True,
    check_response_fails: bool = True,
    stream: bool = False,
) -> Response | None:
    """Send the GET HTTP request with the given url and headers.

    This method also handle logging when the API server return error status code.

    Parameters
    ----------
    url : str
        The url of the request.
    headers : dict | None
        The dict that describes the headers of the request.
    timeout: int | None
        The request timeout (optional).
    allow_redirects: bool
        Whether to allow redirects. Default: True.
    check_response_fails: bool
        When True, check if the response fails. Otherwise, return the response.
    stream: bool
        Indicates whether the response should be immediately downloaded (False) or streamed (True). Default: False.

    Returns
    -------
    Response | None
        If a Response object is returned and ``allow_redirects`` is ``True`` (the default) it will have a status code of
        200 (OK). If ``allow_redirects`` is ``False`` the response can instead have a status code of 302. Otherwise, the
        request has failed and ``None`` will be returned. If ``check_response_fails`` is False, the response will be
        returned regardless of its status code.
    """
    logger.debug("GET - %s", url)
    if not timeout:
        timeout = defaults.getint("requests", "timeout", fallback=10)
    error_retries = defaults.getint("requests", "error_retries", fallback=5)
    retry_counter = error_retries
    try:
        response = requests.get(
            url=url, headers=headers, timeout=timeout, allow_redirects=allow_redirects, stream=stream
        )
    except requests.exceptions.RequestException as error:
        logger.debug(error)
        return None
    if not allow_redirects and response.status_code == 302:
        # Found, most likely because a redirect is about to happen.
        return response
    while response.status_code != 200:
        logger.debug(
            "Receiving error code %s from server.",
            response.status_code,
        )
        if retry_counter <= 0:
            logger.debug("Maximum retries reached: %s", error_retries)
            return None
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return None if not check_response_fails else response
        retry_counter = retry_counter - 1
        response = requests.get(
            url=url,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

    return response


def send_post_http_raw(
    url: str,
    json_data: dict | None = None,
    headers: dict | None = None,
    timeout: int | None = None,
    allow_redirects: bool = True,
) -> Response | None:
    """Send a POST HTTP request with the given url, data, and headers.

    This method also handle logging when the API server returns error status code.

    Parameters
    ----------
    url : str
        The url of the request.
    json_data: dict | None
        The request payload.
    headers : dict | None
        The dict that describes the headers of the request.
    timeout: int | None
        The request timeout (optional).
    allow_redirects: bool
        Whether to allow redirects. Default: True.

    Returns
    -------
    Response | None
        If a Response object is returned and ``allow_redirects`` is ``True`` (the default) it will have a status code of
        200 (OK). If ``allow_redirects`` is ``False`` the response can instead have a status code of 302. Otherwise, the
        request has failed and ``None`` will be returned.
    """
    logger.debug("POST - %s", url)
    if not timeout:
        timeout = defaults.getint("requests", "timeout", fallback=10)
    error_retries = defaults.getint("requests", "error_retries", fallback=5)
    retry_counter = error_retries
    try:
        response = requests.post(
            url=url,
            json=json_data,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )
    except requests.exceptions.RequestException as error:
        logger.debug(error)
        return None
    if not allow_redirects and response.status_code == 302:
        # Found, most likely because a redirect is about to happen.
        return response
    while response.status_code != 200:
        logger.debug(
            "Receiving error code %s from server.",
            response.status_code,
        )
        if retry_counter <= 0:
            logger.debug("Maximum retries reached: %s", error_retries)
            return None
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return None
        retry_counter = retry_counter - 1
        response = requests.post(
            url=url,
            json=json_data,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
        )

    return response


class StreamWriteDownloader:
    """A class to handle writing a streamed download to a file."""

    def __init__(self, file: BinaryIO) -> None:
        """Initialise the class with the file path."""
        self.file = file

    def chunk_function(self, chunk: bytes) -> None:
        """Write the chunk to the file."""
        self.file.write(chunk)


def download_file_with_size_limit(
    url: str, headers: dict, file_path: str, timeout: int = 40, size_limit: int = 0
) -> bool:
    """Download a file with a size limit that will abort the operation if exceeded.

    Parameters
    ----------
    url: str
        The target of the request.
    headers: dict
        The headers to use in the request.
    file_path: str
        The path to download the file to.
    timeout: int
        The timeout in seconds for the request.
    size_limit: int
        The size limit in bytes of the downloaded file.
        A download will terminate if it reaches beyond this amount.

    Returns
    -------
    bool
        True if the operation succeeded, False otherwise.
    """
    try:
        with open(file_path, "wb") as file:
            downloader = StreamWriteDownloader(file)
            return stream_file_with_size_limit(url, headers, downloader.chunk_function, timeout, size_limit)
    except OSError as error:
        logger.error(error)
        return False


def stream_file_with_size_limit(
    url: str, headers: dict, chunk_function: Callable[[bytes], None], timeout: int = 40, size_limit: int = 0
) -> bool:
    """Stream a file download and perform the passed function on the chunks of its data.

    If data in excess of the size limit is received, this operation will be aborted.

    Parameters
    ----------
    url: str
        The target of the request.
    headers: dict
        The headers to use in the request.
    chunk_function: Callable[[bytes], None]
        The function to use with each downloaded chunk.
    timeout: int
        The timeout in seconds for the request.
    size_limit: int
        The size limit in bytes of the downloaded file.
        A download will terminate if it reaches beyond this amount.
        The default value of zero disables the limit.

    Returns
    -------
    bool
        True if the operation succeeded, False otherwise.
    """
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=timeout)
        response.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        logger.debug("HTTP error occurred when trying to stream source: %s", http_err)
        return False

    if response.status_code != 200:
        return False

    data_processed = 0
    for chunk in response.iter_content(chunk_size=512):
        if data_processed >= size_limit > 0:
            response.close()
            logger.warning(
                "The download of file '%s' has been unsuccessful due to the configured size limit. "
                "To be able to download this file, increase the size limit and try again.",
                url,
            )
            return False

        chunk_function(chunk)
        data_processed += len(chunk)

    return True


def check_rate_limit(response: Response) -> None:
    """Check the remaining calls limit to GitHub API and wait accordingly.

    Parameters
    ----------
    response : Response
        The latest response from GitHub API.
    """
    if "X-RateLimit-Remaining" in response.headers:
        remains = int(response.headers["X-RateLimit-Remaining"])
    else:
        remains = 2

    if remains <= 1:
        rate_limit_reset = response.headers.get("X-RateLimit-Reset", default="")

        if not rate_limit_reset:
            return

        try:
            reset_time = float(rate_limit_reset)
        except ValueError:
            logger.critical("X-RateLimit-Reset=%s in the response's header is not a valid number.", rate_limit_reset)
            return

        time_to_sleep: float = reset_time - datetime.timestamp(datetime.now()) + 1
        if time_to_sleep > 0:
            logger.info("Exceeding rate limit. Sleep for %s seconds", time_to_sleep)
            time.sleep(time_to_sleep)


def construct_query(params: dict) -> str:
    """Construct a URL query from the provided keywords params.

    Parameters
    ----------
    params : dict
        The dictionary of parameters for the search.

    Returns
    -------
    str
        The constructed query as string.

    Examples
    --------
    >>> construct_query({"bar":1,"foo":2})
    'bar=1&foo=2'
    """
    return urllib.parse.urlencode(params)


def download_github_build_log(url: str, headers: dict) -> str:
    """Download and return the build log from a GitHub API build log url.

    Parameters
    ----------
    url : str
        The url of the request.
    headers : dict
        The dict that describes the headers of the request.

    Returns
    -------
    str
        The content of the downloaded build log or empty if error.
    """
    logger.debug("Downloading content at link %s", url)
    response = requests.get(
        url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10)
    )  # nosec B113:request_without_timeout

    return response.content.decode("utf-8")


def copy_file(src: str, dest_dir: str) -> bool:
    """Copy a file using `shutil.copy2 <https://docs.python.org/3/library/shutil.html>`_.

    This copy operation will preserve the permission of the src file.

    Parameters
    ----------
    src : str
        The path of the source file.
    dest_dir : str
        The destination path to copy to.

    Returns
    -------
    bool
        True if succeed else False.
    """
    try:
        logger.info("Copying %s to %s", src, dest_dir)
        shutil.copy2(src, dest_dir)
        return True
    except shutil.Error as error:
        logger.error("Error while copying %s to %s", src, dest_dir)
        logger.error(str(error))
        return False


def copy_file_bulk(file_list: list, src_path: str, target_path: str) -> bool:
    """Copy multiple files using the ``copy_file`` method.

    Files in ``file_list`` will be copied from src_path to target_path.

    If a file in ``file_list`` exists in ``target_path``, it will be ignored. This method will
    handle creating intermediate dirs to store files accordingly.

    Parameters
    ----------
    file_list : list
        The list of file path need to be copied. These are relative path from src_path.
    src_path : str
        The absolute path of the source dir.
    target_path : str
        The absolute path to the target dir where all files will be copied.

    Returns
    -------
    bool
        True if succeed else False.

    See Also
    --------
    copy_file : Copy a single file.

    Examples
    --------
    ``file.txt`` will be copied from ``src/foo/bar/file.txt`` to ``target/foo/bar/file.txt``

    .. code-block:: python3

        copy_file_bulk(["foo/bar/file.txt"], "src", "target")
    """
    for file in file_list:
        file_src_path = os.path.join(src_path, file)
        file_dest_path = os.path.join(target_path, file)

        os.makedirs(os.path.dirname(file_dest_path), exist_ok=True)
        if not os.path.exists(file_dest_path):
            logger.info("%s of the repo is missing", file)
            if not copy_file(file_src_path, file_dest_path):
                return False

    return True


class BytesDecoder:
    """This class aims to decode some non-UTF8 bytes to a valid string.

    The aim is not to 'correctly' parse the passed data. Only to successfully do so.
    It is assumed that an attempt to decode using UTF8 has already failed.
    The top 10 most common encodings (after UTF-8) are tried.
    """

    # Taken from https://w3techs.com/technologies/overview/character_encoding.
    COMMON_ENCODINGS = [
        "ISO-8859-1",
        "cp1252",
        "cp1251",
        "euc-jp",
        "euc-kr",
        "shift_jis",
        "gb2312",
        "cp1250",
        "ISO-8859-2",
        "big5",
    ]

    @staticmethod
    def decode(data: bytes) -> str | None:
        """Attempt to decode the passed bytes using common encodings.

        Parameters
        ----------
        data: bytes
            The data to decode.

        Returns
        -------
        str | None
            The data as a string if successful, or None.
        """
        for encoding in BytesDecoder.COMMON_ENCODINGS:
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                pass

        logger.debug("Failed to decode bytes using most common character encodings.")
        return None
