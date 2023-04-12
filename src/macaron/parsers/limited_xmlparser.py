# Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This module performs limited parsing of xml files to retrieve the contents of specific tags."""
from macaron.config.global_config import logger


def extract_tags(xml: str, target: set[str]) -> list[str]:
    """Extract the passed tags from the passed xml file.

    Parameters
    ----------
    xml : str
        xml file data as a string
    target : set[str]
        the tags to extract in the format of: 'tag1[.tag2 ... .tagN]'

    Returns
    -------
    str
        The extracted tag contents
    """
    brackets_open = False
    closing_tag = False
    tag_had_space = False
    comment_block = False
    quote_block = False
    quote_char: str = ""
    tag: list[str] = []
    tags: list[str] = []
    content: list[str] = []
    sliding_window: list[str] = []
    results: list[str] = []
    matches: int = 0

    for char in xml:
        if char in ("\n", "\r"):
            continue

        # Maintain a sliding window of the last n characters
        if len(sliding_window) == 4:
            sliding_window = sliding_window[1:]
        sliding_window.append(char)

        # Ignore contents of comments, except the terminating tag
        if not quote_block:
            if comment_block:
                if char == ">":
                    if char == ">" and "".join(sliding_window[1:]) == "-->":
                        comment_block = False
                continue
            if char == "-" and "".join(sliding_window) == "<!--":
                comment_block = True
                brackets_open = False
                closing_tag = False
                tag_had_space = False
                tag = []
                continue

        # Ignore contents of quotes, except when this char would terminate it
        if quote_block:
            if char == quote_char:
                quote_block = False
            continue
        if char in ('"', "'"):
            quote_block = True
            quote_char = char
            continue

        # Parse XML
        match char:
            case "<":
                if brackets_open:
                    logger.warning("Unexpected character: <")
                    return []
                # Start of a new tag
                brackets_open = True
                comment_block = False
            case "/":
                if brackets_open:
                    if closing_tag:
                        logger.warning("Unexpected character: /")
                        return []
                    # The current tag is a closing tag
                    closing_tag = True
                else:
                    content.append(char)
            case ">":
                if brackets_open:
                    joined_tag = "".join(tag)
                    if closing_tag:
                        # Try to complete tag by removing a match from the stack
                        if len(tags) == 0:
                            logger.error("Tried to match closing xml tag '<%s>' with empty stack.", joined_tag)
                            return []
                        last_tag = tags[len(tags) - 1]
                        if last_tag != joined_tag:
                            logger.error(
                                "Failed to match closing xml tag with top of stack: <%s> from %s", joined_tag, tags
                            )
                            return []

                        # Compare tag against extract targets
                        joined_tags = ".".join(tags).strip()
                        if joined_tags in target:
                            joined_content = "".join(content).strip()
                            logger.info("Found match: %s, content: %s", joined_tag, joined_content)
                            results.append(joined_content)
                            matches = matches + 1
                            if matches == len(target):
                                return results
                        tags.pop()

                        # End closing tag
                        closing_tag = False
                        content = []
                    else:
                        # Push the completed opening tag onto the stack
                        if not joined_tag.startswith("?"):
                            tags.append("".join(tag))
                    # End tag
                    tag = []
                    brackets_open = False
                    tag_had_space = False
            case " ":
                if brackets_open:
                    tag_had_space = True
                else:
                    content.append(char)
            case _:
                if brackets_open:
                    if not tag_had_space:
                        tag.append(char)
                else:
                    content.append(char)

    # End of parsing
    return results
