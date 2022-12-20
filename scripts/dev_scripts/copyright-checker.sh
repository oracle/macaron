#!/usr/bin/env bash

# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

#
# Checks if copyright header is valid
#

files=$(git diff --cached --name-only)
currentyear=$(date +"%Y")
missing_copyright_files=()


for f in $files; do
    if [ ! -f "$f" ]; then
        continue
    fi
    startyear=$(git log --format=%ad --date=format:%Y "$f" | tail -1)
    if [[ -z "${startyear// }" ]]; then
        startyear=$currentyear
    fi
    if ! grep -i -e "Copyright (c) $startyear - $currentyear, Oracle and/or its affiliates. All rights reserved." "$f" 1>/dev/null;then
        if [[ $f =~ .*\.(js$|py$|java$|tf$|go$|sh$|dl$|yaml$) ]] || [[ "${f##*/}" = "Dockerfile" ]];then
          missing_copyright_files+=("$f")
        fi
    fi
done

if [ ${#missing_copyright_files[@]} -ne 0 ]; then
    for f in "${missing_copyright_files[@]}"; do
        startyear=$(git log --format=%ad --date=format:%Y "$f" | tail -1)
        if [[ -z "${startyear// }" ]]; then
            startyear=$currentyear
        fi
        if [[ $f =~ .*\.(js$|java$|go$|dl$) ]]; then
            expected="\/\* Copyright \(c\) $startyear - $currentyear, Oracle and\/or its affiliates\. All rights reserved\. \*\/"
            expected="$expected\n\/\* Licensed under the Universal Permissive License v 1.0 as shown at https:\/\/oss\.oracle\.com\/licenses\/upl\/\. \*\/"
        elif [[ $f =~ .*\.(py$|tf$|sh$|yaml$) ]] || [[ "${f##*/}" = "Dockerfile" ]]; then
            expected="# Copyright \(c\) $startyear - $currentyear, Oracle and\/or its affiliates\. All rights reserved\."
            expected="$expected\n# Licensed under the Universal Permissive License v 1.0 as shown at https:\/\/oss\.oracle\.com\/licenses\/upl\/\."

        fi

        if ! grep -i -e "Copyright (c) .* Oracle and/or its affiliates. All rights reserved" "$f" 1>/dev/null;then
            echo "Copyright header missing for $f"
            sed -i "1s/^/$expected\n\n/" "$f"
        else
            echo "Copyright header needs update for $f"
            sed -i "1s/^.*/$expected/" "$f"
        fi
    done
    echo "Copyright headers have been automatically added/updated. Please review and stage the changes before running git commit again."
    exit 1
fi
