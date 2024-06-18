#!/bin/bash

# Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# We update the GID and UID of the existing macaron user in the container
# with the GID and UID of the current user in the host machine.
# This will make the files created during the runtime of the container would have
# the current user of the host machine as the owner.
if [[ -n "$USER_GID" ]] && [[ -n "$USER_UID" ]];
then
    groupmod --non-unique --gid "$USER_GID" macaron
    usermod --non-unique --gid "$USER_GID" --uid "$USER_UID" macaron
else
    echo "Cannot find the GID and UID of the host machine's user. The output files generated could not be modifiable from the host machine."
    echo "Consider providing the GID and UID via the env variables USER_GID and USER_UID respectively."
fi

# Prepare settings.xml because
# We mount .m2 dir to the host machine
# We cannot copy those files while building the image
# because they will be bypassed.
if [[ ! -f "$HOME/.m2/settings.xml" ]] && [[ -n "$PACKAGE_PATH" ]];
then
    if [[ ! -d "$HOME/.m2" ]];
    then
        mkdir --parents "$HOME"/.m2
    fi
    cp "$PACKAGE_PATH"/resources/settings.xml "$HOME"/.m2/
fi

# Overwrite $HOME/.m2/settings.xml if the global settings.xml file is mounted from the host machine.
if [[ -f "$HOME/settings.xml" ]];
then
    cp "$HOME/settings.xml" "$HOME/.m2/settings.xml"
fi

# Create $HOME/.gradle/gradle.properties if the global gradle.properties file is mounted from the host machine.
if [[ ! -d "$HOME/.gradle" ]];
then
    mkdir --parents "$HOME"/.gradle
fi
if [[ -f "$HOME/gradle.properties" ]];
then
    cp "$HOME"/gradle.properties "$HOME/.gradle/gradle.properties"
fi

# Prepare the output directory. The output directory will be already existed
# if we mount from the host machine.
if [[ ! -d "$HOME/output" ]];
then
    mkdir --parents "$HOME"/output
fi

# Prepare the python virtual environment for the target software component if provided as input.
# We copy the mounted directory if it exists to `analyze_python_venv_editable` to fix the symbolic
# links to the Python interpreter in the container without affecting the files on host.
# That's because cylonedx-py needs to access Python in the virtual environment where it generates
# the SBOM from and the original files will be symbolic links to Python on the host system that
# are not reachable from the container.
if [[ -d "$HOME/analyze_python_venv_readonly" ]];
then
    cp -r "$HOME/analyze_python_venv_readonly" "$HOME/analyze_python_venv_editable"
fi

if [[ -d "$HOME/analyze_python_venv_editable/bin" ]];
then
    python_binaries=(
        "python"
        "python3"
        "python3.11"
    )
    for p in "${python_binaries[@]}"; do
        if [[ -f "$HOME/.venv/bin/${p}" ]];
        then
            ln -sf "$HOME/.venv/bin/${p}" "$HOME/analyze_python_venv_editable/bin/${p}"
        fi
    done
fi

# The directory that could be mounted to the host machine file systems should
# have the owner as the current user in the host machine.
chown --recursive macaron:macaron "$HOME"/.m2
chown --recursive macaron:macaron "$HOME"/.gradle
chown --recursive macaron:macaron "$HOME"/output

# Run the provided Macaron command with the user macaron.
MACARON_PARAMS=( "$@" )
COMMAND="cd /home/macaron && . .venv/bin/activate && ${MACARON_PARAMS[*]}"
su macaron --preserve-environment --command "$COMMAND"
