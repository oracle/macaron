# Copyright (c) 2022 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module includes utilities functions for Macaron."""

import logging
import os
import shutil
import time
import urllib.parse
from datetime import datetime

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
