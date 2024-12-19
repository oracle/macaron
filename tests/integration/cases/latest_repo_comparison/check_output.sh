#!/bin/bash
# Copyright (c) 2024 - 2024, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

[[ "$(jq -r '.commit' output/reports/maven/io_avaje/avaje-prisms/avaje-prisms.source.json)" = "1f6f953df0b58f0c35b5e136f62f63ba7a22bc03" ]] &&
[[ "$(jq -r '.repo' output/reports/maven/io_avaje/avaje-prisms/avaje-prisms.source.json)" = "https://github.com/avaje/avaje-prisms" ]]
