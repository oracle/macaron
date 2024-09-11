#!/usr/bin/env bash

# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

#
# Checks if copyright header is valid.
#


# Get the existing start year of a file, by checking if there is already a copyright
# notice line and capturing the start year.
#
# Arguments:
#   $1: The file to get the start year.
# Outputs:
#   STDOUT: The start year if it exists; empty string otherwise.
get_existing_start_year() {
  file="$1"
  copyright_line=$(grep -i -e "Copyright (c) [0-9]* - [0-9]*, Oracle and/or its affiliates. All rights reserved." "$file")

  # Use bash regex matching to get the start year with a capture group.
  # Grep is not used since it does not have support for capture groups.
  # Reference: https://stackoverflow.com/questions/1891797/capturing-groups-from-a-grep-regex
  capture_pattern="Copyright \(c\) ([0-9]*) - [0-9]*, Oracle and/or its affiliates. All rights reserved."

  if [[ $copyright_line =~ $capture_pattern ]]
  then
      year="${BASH_REMATCH[1]}"
      echo "$year"
  else
      echo ""
  fi
}


files=$(git diff --cached --name-only)
currentyear=$(date +"%Y")
missing_copyright_files=()
license_note="Licensed under the Universal Permissive License v 1.0 as shown at https:\/\/oss\.oracle\.com\/licenses\/upl\/\."


for f in $files; do
    if [ ! -f "$f" ]; then
        continue
    fi
    if ! grep -i -e "Copyright (c) [0-9]* - $currentyear, Oracle and/or its affiliates. All rights reserved." "$f" 1>/dev/null;then
        if [[ $f =~ .*\.(js$|py$|java$|tf$|go$|sh$|dl$|yaml$|yml$|gradle$|kts$|ini$|toml$) ]] || [[ "${f##*/}" = "Dockerfile" ]] \
            || [[ "${f##*/}" = "Makefile" ]] || [[ "${f##*/}" = "Jenkinsfile" ]];then
          missing_copyright_files+=("$f")
        fi
    fi
done

SED="sed"
# Use gnu-sed (gsed) on mac.
if [[ "$(uname)" == "Darwin" ]]; then
    SED="gsed"
fi

if [ ${#missing_copyright_files[@]} -ne 0 ]; then
    for f in "${missing_copyright_files[@]}"; do

        # Don't allow this script to run on itself.
        if [[ $0 == "$f" ]];then
            echo "Cannot run the $0 on itself. Please fix the headers in this file manually."
            exit 1
        fi
        missing_license_note=$(grep -i "$license_note" "$f")
        startyear=$(get_existing_start_year "$f")
        if [[ -z "${startyear// }" ]]; then
            startyear=$currentyear
        fi
        if [[ $f =~ .*\.(js$|java$|go$|dl$|gradle$|kts$) ]] || [[ "${f##*/}" = "Jenkinsfile" ]]; then
            expected="\/\* Copyright \(c\) $startyear - $currentyear, Oracle and\/or its affiliates\. All rights reserved\. \*\/"
            if [ ${#missing_license_note} -eq 0 ]; then
                expected="$expected\n\/\* $license_note \*\/"
            fi
        elif [[ $f =~ .*\.(py$|tf$|sh$|yaml$|yml$|ini$|toml$) ]] || [[ "${f##*/}" = "Dockerfile" ]] || [[ "${f##*/}" = "Makefile" ]]; then
            expected="# Copyright \(c\) $startyear - $currentyear, Oracle and\/or its affiliates\. All rights reserved\."
            if [ ${#missing_license_note} -eq 0 ]; then
                expected="$expected\n# $license_note"
            fi
        fi

        # Find the first matching copyright line.
        line_number=$(grep -m 1 -n -i -e "Copyright (c) .* Oracle and/or its affiliates. All rights reserved" "$f" | cut -d : -f 1)
        if [[ -z "$line_number" ]]; then
            echo "Copyright header missing for $f."

            # Check for executable scripts and don't replace the first line starting with shebang.
            shebang_line=$(grep -m 1 -n "#!" "$f")
            if [[ -z "$shebang_line" ]];then
                # If there is no shebang, insert at the first line.
                $SED -i "1s/^/$expected\n\n/" "$f"
            else
                # If there is a shebang, append to the end of the line.
                $SED -i "$(echo "$shebang_line" | cut -d : -f 1)""s/$/\n\n$expected/" "$f"
            fi
        else
            echo "Copyright header needs update for $f."
            $SED -i "$line_number""s/^.*/$expected/" "$f"
        fi
    done
    echo "Copyright headers have been automatically added/updated. Please review and stage the changes before running git commit again."
    exit 1
fi
