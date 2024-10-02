# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
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
        self,
        section: str,
        option: str,
        delimiter: str | None = "\n",
        fallback: list[str] | None = None,
        strip: bool = True,
        remove_duplicates: bool = True,
    ) -> list[str]:
        r"""Parse and return a list of strings from an ``option`` for ``section`` in ``defaults.ini``.

        This method uses str.split() to split the value into list of strings.
        References: https://docs.python.org/3/library/stdtypes.html#str.split.

        The following parameters are used to modify the behavior of the split operation.

        If ``delimiter`` is set (default: "\n"), it will be used to split the list of strings
        (i.e content.split(sep=delimiter)).

        If ``strip`` is True  (default: True), strings are whitespace-stripped and empty strings
        are removed from the final result.

        If `remove_duplicates` is True, duplicated elements which come after the their first instances will
        be removed from the list. This operation happens after ``strip`` is handled.

        The order of non-empty elements in the list is preserved.
        The content of each string in the list is not validated and should be handled separately.

        Parameters
        ----------
        section : str
            The section in ``defaults.ini``.
        option : str
            The option whose values will be split into the a list of strings.
        delimiter : str | None
            The delimiter used to split the strings.
        fallback : list | None
            The fallback value in case of errors.
        strip : bool
            If True, strings are whitespace-stripped and any empty strings are removed.
        remove_duplicates : bool
            If True, duplicated elements will be removed from the list.

        Returns
        -------
        list
            The result list of strings or an empty list if errors.

        Examples
        --------
        Given the following ``defaults.ini``

        .. code-block:: ini

            [git]
            allowed_hosts =
                github.com
                boo.com gitlab.com
                host com

        .. code-block:: python3

            allowed_hosts = config_parser.get_list("git", "allowed_hosts")
            allowed_hosts == ["github.com", "boo.com gitlab.com", "host com"]
        """
        try:
            value = self.get(section, option)
            if isinstance(value, str):
                content = value.split(sep=delimiter)

                if strip:
                    content = [x.strip() for x in content if x.strip()]

                if not remove_duplicates:
                    return content

                values = []
                for ele in content:
                    if ele in values:
                        continue
                    values.append(ele)
                return values
        except (configparser.NoOptionError, configparser.NoSectionError) as error:
            logger.error(error)

        return fallback or []


defaults = ConfigParser()


def load_defaults(user_config_path: str) -> bool:
    """Read the default values from ``defaults.ini`` file and store them in the defaults global object.

    Parameters
    ----------
    user_defaults_path : str
        The path to the user's defaults configuration file.

    Returns
    -------
    bool
        Return True if succeeded or False if failed.
    """
    curr_dir = pathlib.Path(__file__).parent.absolute()
    config_files = [os.path.join(curr_dir, "defaults.ini")]
    if os.path.exists(user_config_path):
        config_files.append(user_config_path)
    elif user_config_path:
        logger.error("Configuration file %s does not exist.", user_config_path)
        return False

    try:
        defaults.read(config_files, encoding="utf8")
        return True
    except (configparser.Error, ValueError) as error:
        logger.error("Failed to read the defaults.ini files.")
        logger.error(error)
        return False


def create_defaults(output_path: str, cwd_path: str) -> bool:
    """Create the ``defaults.ini`` file at the Macaron's root dir for end users.

    Parameters
    ----------
    output_path : str
        The path where the ``defaults.ini`` will be created.
    cwd_path : str
        The path to the current working directory.

    Returns
    -------
    bool
        Return True if succeeded or False if failed.
    """
    src_path = os.path.join(pathlib.Path(__file__).parent.absolute(), "defaults.ini")
    try:
        user_defaults = ConfigParser()
        user_defaults.read(src_path, encoding="utf8")
    except (configparser.Error, ValueError) as error:
        logger.error(error)
        return False

    # Since we have only one defaults.ini file and ConfigParser.write does not
    # preserve the comments, copy the file directly.
    dest_path = os.path.join(output_path, "defaults.ini")
    try:
        shutil.copy2(src_path, dest_path)
        logger.info(
            "Dumped the default values in %s.",
            os.path.relpath(os.path.join(output_path, "defaults.ini"), cwd_path),
        )
        return True
    # We catch OSError to support errors on different platforms.
    except OSError as error:
        logger.error("Failed to create %s: %s.", os.path.relpath(dest_path, cwd_path), error)
        return False
