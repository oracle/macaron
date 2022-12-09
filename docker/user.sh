#!/bin/bash

# Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

groupmod -o -g $USER_GID macaron
usermod -o -g $USER_GID -u $USER_UID macaron

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
    cp $HOME/resources/settings.xml $HOME/.m2/
    chown -R macaron:macaron $HOME/.m2
fi

COMMAND="cd /home/macaron && python3 -m macaron $@"
su macaron -m -c "$COMMAND"
