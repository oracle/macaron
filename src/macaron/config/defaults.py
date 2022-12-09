# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module provides functions to manage default values."""

import configparser
import logging
import os
import pathlib
import shutil

logger: logging.Logger = logging.getLogger(__name__)


class ConfigParser(configparser.ConfigParser):
    """This class extends ConfigParser with useful methods."""

    def get_list(
        self, section: str, item: str, delimiter: str = None, fallback: list = None, duplicated_ok: bool = False
    ) -> list:
        """Parse and return a list of strings from an item in ``defaults.ini``.

        If ``delimiter`` is not set (default: None), return strings are split on any whitespace character
        and will discard empty strings from the result. If `delimiter` is set, it will be used to split
        the list of strings only (any whitespace character are not removed).

        If ``duplicated_ok`` is True (default: False), duplicated values are not removed from the final list.

        The content of each string in the list is not validated and should be handled separately.

        Parameters
        ----------
        section : str
            The section in ``defaults.ini``.
        item : str
            The item to parse the list.
        delimiter : str
            The delimiter used to split the strings.
        fallback : list
            The fallback value in case of errors.
        duplicated_ok : bool
            If True allow duplicate values.

        Returns
        -------
        list
            The result list of strings or an empty list if errors.

        Examples
        --------
        Given the following ``defaults.ini``

        .. code-block::

            [git]
            allowed_hosts =
                github.com gitlab.com
                host com

        >>> config_parser.get_list("git", "allowed_hosts")
        ['github.com', 'gitlab.com', 'host', 'com']
        """
        try:
            value = self.get(section, item)
            if isinstance(value, str):
                content = value.split(sep=delimiter)

                if duplicated_ok:
                    return content

                distinct_values = set()
                distinct_values.update(content)

                return list(distinct_values)

            return fallback or []
        except configparser.NoOptionError as error:
            logger.error(error)
            return fallback or []


defaults = ConfigParser()


def load_defaults(macaron_path: str) -> bool:
    """Read the default values from ``defaults.ini`` file and store them in the defaults global object.

    Parameters
    ----------
    macaron_path : str
        The path to Macaron's root dir.

    Returns
    -------
    bool
        Return True if succeeded or False if failed.
    """
    curr_dir = pathlib.Path(__file__).parent.absolute()
    config_files = [os.path.join(curr_dir, "defaults.ini")]
    if os.path.exists(os.path.join(macaron_path, "defaults.ini")):
        config_files.append(os.path.join(macaron_path, "defaults.ini"))

    try:
        defaults.read(config_files, encoding="utf8")
        return True
    except ValueError:
        logger.error("Failed to read the defaults.ini files.")
        return False


def create_defaults(output_path: str, macaron_path: str) -> bool:
    """Create the ``defaults.ini`` file at the Macaron's root dir for end users.

    Parameters
    ----------
    output_path : str
        The path where the ``defaults.ini`` will be created.
    macaron_path : str
        The path to Macaron's root dir.

    Returns
    -------
    bool
        Return True if succeeded or False if failed.
    """
    src_path = os.path.join(pathlib.Path(__file__).parent.absolute(), "defaults.ini")
    try:
        user_defaults = ConfigParser()
        user_defaults.read(src_path, encoding="utf8")
    except ValueError as error:
        logger.error(error)
        return False

    # Since we have only one defaults.ini file and ConfigParser.write does not
    # preserve the comments, copy the file directly.
    dest_path = os.path.join(output_path, "defaults.ini")
    try:
        shutil.copy2(src_path, dest_path)
        logger.info(
            "Dumped the default values in %s.",
            os.path.relpath(os.path.join(output_path, "defaults.ini"), macaron_path),
        )
        return True
    except shutil.Error as error:
        logger.error("Failed to create %s: %s.", os.path.relpath(dest_path, macaron_path), error)
        return False
    except PermissionError as error:
        logger.error(error)
        return False
