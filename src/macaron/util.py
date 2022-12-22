# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
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
    response = requests.get(url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10))
    while response.status_code != 200:
        logger.error(
            "Receiving error code %s from server. Message: %s.",
            response.status_code,
            response.text,
        )
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return {}
        response = requests.get(url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10))

    return dict(response.json())


def send_get_http_raw(url: str, headers: dict) -> Response | None:
    """Send the GET HTTP request with the given url and headers.

    This method also handle logging when the API server return error status code.

    Parameters
    ----------
    url : str
        The url of the request.
    headers : dict
        The dict that describes the headers of the request.

    Returns
    -------
    Response
        The response object or None if there is an error.
    """
    logger.debug("GET - %s", url)
    response = requests.get(url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10))
    while response.status_code != 200:
        logger.error(
            "Receiving error code %s from server. Message: %s.",
            response.status_code,
            response.text,
        )
        if response.status_code == 403:
            check_rate_limit(response)
        else:
            return None
        response = requests.get(url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10))

    return response


def check_rate_limit(response: Response) -> None:
    """Check the remaining calls limit to GitHub API and wait accordingly.

    Parameters
    ----------
    response : Response
        The latest response from GitHub API.
    """
    remains = 0
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
    response = requests.get(url=url, headers=headers, timeout=defaults.getint("requests", "timeout", fallback=10))

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

    >>> copy_file_bulk(['foo/bar/file.txt'], 'src', 'target')
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
