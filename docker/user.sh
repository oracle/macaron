#!/bin/bash

# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# We update the GID and UID of the existing macaron user in the container
# with the GID and UID of the current user in the host machine.
# This will make the files created during the runtime of the container would have
# the current user of the host machine as the owner.
if [[ ! -z "$USER_GID" ]] && [[ ! -z "$USER_UID" ]];
then
    groupmod -o -g $USER_GID macaron
    usermod -o -g $USER_GID -u $USER_UID macaron
else
    echo "Cannot find the GID and UID of the host machine's user. The output files generated could not be modifiable from the host machine."
    echo "Consider providing the GID and UID via the env variables USER_GID and USER_UID respectively."
fi

# Prepare settings.xml because
# We mount .m2 dir to the host machine
# We cannot copy those files while building the image
# because they will be bypassed.
if [[ ! -f "$HOME/.m2/settings.xml" ]];
then
    if [[ ! -d "$HOME/.m2" ]];
    then
        mkdir -p $HOME/.m2
    fi
    cp $PACKAGE_PATH/resources/settings.xml $HOME/.m2/
fi

# Prepare the output directory. The output directory will be already existed
# if we mount from the host machine.
if [[ ! -d "$HOME/output" ]];
then
    mkdir -p $HOME/output
fi

# The directory that could be mounted to the host machine file systems should
# have the owner as the current user in the host machine.
chown -R macaron:macaron $HOME/.m2
chown -R macaron:macaron $HOME/output

# Run the provided Macaron command with the user macaron.
COMMAND="cd /home/macaron && . .venv/bin/activate && macaron $@"
su macaron -m -c "$COMMAND"
