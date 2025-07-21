# Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

"""This script checks grammar formatting in Python source files."""
import glob
import os.path
import re
import sys
import tempfile


def main(source_locations: list[str] = None) -> int:
    """Check the grammar formatting of Python source files passed directly, or in directories.

    If the passed list is empty, fallback to system arguments.
    If source locations include files and directories, this script will only check files within the passed directories.
    Otherwise, all files, or files within directories, will be checked.
    Macaron's integration test directories are always excluded.
    """
    if not source_locations and len(sys.argv) >= 2:
        source_locations = []
        for arg in sys.argv[1:]:
            source_locations.append(arg)

    if not source_locations or not isinstance(source_locations, list):
        return 0

    restrictive_mode = False
    source_directories = []
    source_files = []
    for source_location in source_locations:
        if os.path.isfile(source_location):
            source_files.append(source_location)
        elif os.path.isdir(source_location):
            source_directories.append(source_location)
    if source_files and source_directories:
        restrictive_mode = True

    checker = FormatChecker()
    target_files = []

    if restrictive_mode:
        for source_file in source_files:
            for source_directory in source_directories:
                if os.path.commonpath([source_file, source_directory]):
                    target_files.append(source_file)
                    break
    else:
        for source_directory in source_directories:
            target_files = target_files + glob.glob(f"{source_directory}/**/*.py", recursive=True)
        for source_file in source_files:
            target_files.append(source_file)

    changed_files = 0
    for target_file in target_files:
        if os.path.join("integration", "cases") in target_file:
            # Exclude integration test directories.
            continue
        with open(target_file, "r", encoding="utf-8") as file:
            lines = file.readlines()
        changed_files = changed_files + checker.check_file(target_file, lines)

    return 1 if changed_files else 0


class FormatChecker:

    TOOL_EXCEPTIONS = {"noqa:", "pylint:", "type:", "nosec", "nosec:", "flake8:", "pragma:", "pyarmor:", ":meta"}
    LOWER_CASE_EXCEPTIONS = {"npm", "http:", "https:", "git@", "jdk"}
    END_PUNCTUATION = {".", "!", "?"}
    OTHER_PUNCTUATION = {",", ":", ";"}
    SPECIAL_EXCEPTIONS = {"e.g.", "i.e.", "n.b."}
    DISABLE_KEYWORD = ["grammar:", "off"]
    WRAPPERS = ["'", '"', ")"]

    def check_file(self, source_file: str, lines: list[str]) -> int:
        """Check and fix the contents of the passed file."""
        grouped_comment_lines = []
        current_group = []
        inline_comment_lines = []
        start_indices = {}
        for index, line in enumerate(lines):
            if index < 2:
                # Copyright headers are checked elsewhere.
                continue
            if "#" not in line:
                continue
            line = line.rstrip()

            line_split = re.split("(\s+)", line)
            start_index = -1
            for part_index, part in enumerate(line_split):
                if part in {"#", "#:", "##"}:
                    start_index = part_index
                    break
            if start_index == -1 or line_split[start_index] == "##":
                # TODO discuss this per-line disable feature.
                continue

            # Check for disable keywords of other tools.
            if start_index + 2 >= len(line_split):
                continue
            first_part = line_split[start_index + 2]
            if first_part in self.TOOL_EXCEPTIONS:
                continue

            # Check for this disabler.
            if start_index + 4 < len(line_split):
                second_part = line_split[start_index + 4]
                if first_part == self.DISABLE_KEYWORD[0] and second_part == self.DISABLE_KEYWORD[1]:
                    return 0

            # Separate in-line and regular comments.
            start_indices[index] = start_index
            if start_index > 3:
                # In-line comment.
                inline_comment_lines.append(index)
            else:
                # Regular comments.
                if not current_group:
                    current_group.append(index)
                    grouped_comment_lines.append(current_group)
                else:
                    if index - current_group[-1] > 1:
                        current_group = []
                        grouped_comment_lines.append(current_group)
                    current_group.append(index)

        # TODO create class for handling lines and offsets.
        change_count = 0
        for index in inline_comment_lines:
            line = lines[index].rstrip()
            line_split = re.split("(\s+)", line)
            start_index = -1
            for part_index, part in enumerate(line_split):
                if part in {"#", "#:", "##"}:
                    start_index = part_index
                    break
            if start_index == -1:
                continue
            changed_line, changed = self.check_line(line_split, None, None, start_index + 2)
            if changed:
                change_count += 1
                lines[index] = "".join(changed_line) + os.linesep

        split_lines = {}
        for group in grouped_comment_lines:
            for index in group:
                split_lines[index] = re.split("(\s+)", lines[index].rstrip())

        for index, group in enumerate(grouped_comment_lines):
            group_changed = False
            for group_index, line_index in enumerate(group):
                current_line = split_lines[line_index]
                prev_line = None
                if group_index > 0:
                    prev_line = split_lines[line_index - 1][-1]
                next_line = None
                if group_index < len(group) - 1:
                    next_line = split_lines[line_index + 1][start_indices[line_index + 1] + 2]
                current_line, changed = self.check_line(
                    current_line, prev_line, next_line, start_indices[line_index] + 2
                )
                if changed:
                    lines[line_index] = "".join(current_line) + os.linesep
                group_changed = group_changed | changed
            if group_changed:
                change_count += 1

        if change_count:
            # Save changes.
            target_dir = os.path.dirname(source_file)
            file_mode = os.stat(source_file).st_mode
            print(f"*** Adjusting file: {source_file}")
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target_dir, delete=False) as file:
                file.writelines(lines)
                os.replace(file.name, source_file)
                os.chmod(source_file, file_mode)

        return 1 if change_count else 0

    def check_line(
        self, current_line: list[str], prev_line: str | None, next_line: str | None, start_index: int = 0
    ) -> tuple[list[str], bool]:
        """Check the current line for formatting issues."""
        if current_line[start_index] == "-":
            # Ignore bullet point style lines.
            return current_line, False

        has_changed = False
        if (
            (prev_line and self.has_sentence_end(prev_line) or not prev_line)
            and not self.has_sentence_start(current_line[start_index])
            and re.match("[a-z]", current_line[start_index][0])
        ):
            current_line[start_index] = current_line[start_index][0].upper() + current_line[start_index][1:]
            has_changed = True
        if (
            next_line
            and re.match("^[A-Z][^A-Z]*$", next_line)
            and current_line[start_index][-1] not in self.END_PUNCTUATION
        ):
            current_line, line_changed = self.fix_sentence_end(current_line)
            has_changed = has_changed | line_changed

        for index, current_word in enumerate(current_line):
            if index <= start_index:
                continue
            if not current_word:
                continue
            prev_word = current_line[index - 2]
            if not self.has_sentence_end(prev_word):
                continue
            if (
                prev_word.lower() in self.SPECIAL_EXCEPTIONS
                or prev_word.startswith("(")
                and prev_word[1:].lower() in self.SPECIAL_EXCEPTIONS
            ):
                continue
            if self.has_sentence_start(current_word):
                continue
            if re.match("[a-z]", current_word[0]):
                continue
            current_line[index] = current_word[0].upper() + current_word[1:]
            has_changed = True

        if not next_line:
            current_line, line_changed = self.fix_sentence_end(current_line)
            has_changed = has_changed | line_changed

        return current_line, has_changed

    def fix_sentence_end(self, line: list[str]) -> tuple[list[str], bool]:
        """Fix the end of a sentence by adding a period when appropriate."""
        if line[-1].endswith('"""') or line[-1].endswith(":"):
            return line, False
        if line[-1].startswith("https://") or line[-1].startswith("http://") or line[-1].startswith("git@"):
            # Allow URLs to end sentences without a period.
            return line, False
        if (
            line[-1][-1] not in self.END_PUNCTUATION
            and line[-1][-1] not in self.OTHER_PUNCTUATION
            and not (line[-1][-1] in self.WRAPPERS and line[-1][-2] == ".")
            and re.search("[a-zA-Z0-9]", line[-1])
        ):
            # Add a period if line does not end with one, or another acceptable punctuation.
            # Also check for periods within wrappers, e.g. parenthesis.
            # Only add a period if the final word contains at least one alphanumeric character.
            line[-1] += "."
            return line, True

        return line, False

    def has_sentence_start(self, word: str) -> bool:
        """Check if the passed line starts with a capital letter, etc."""
        # TODO refactor this method to distinguish between when a sentence has a capital letter start, versus when it
        #  is only exempt from needing one.
        if re.search("[_@$+:]", word):
            # Ignore non-standard words such as variable references and URLs.
            return True
        if word in self.LOWER_CASE_EXCEPTIONS:
            return True
        if len(word) >= 2 and re.match("^[A-Z][0-9A-Z]+$", word):
            # Ignore words that are entirely in capitals.
            return True
        if re.match("^[A-Z]", word):
            return True
        return False

    def has_sentence_end(self, line: str | list[str]) -> bool:
        """Check if the passed line ends with a punctuation mark."""
        end_word = line[-1] if isinstance(line, list) else line
        if end_word.lower() in self.SPECIAL_EXCEPTIONS:
            return False
        return end_word[-1] in self.END_PUNCTUATION


if __name__ == "__main__":
    raise SystemExit(main())
