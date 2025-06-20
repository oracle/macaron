#!/bin/bash
# Copyright (c) 2024 - 2025, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.
result=$(sqlite3 --json output/macaron.db "SELECT detect_malicious_metadata_check.result
	FROM detect_malicious_metadata_check JOIN check_facts on detect_malicious_metadata_check.id = check_facts.id
	JOIN check_result on check_facts.check_result_id = check_result.id JOIN component
	ON component.id = check_result.component_id WHERE check_result.check_id = 'mcn_detect_malicious_metadata_1'
	AND component.name = 'django' AND component.version = '5.0.6';" | jq -r ".[0].result | fromjson | .suspicious_patterns")

if [ "$result" != "PASS" ]; then
	echo "ERROR: suspicious_patterns heuristic result $result is not PASS" >&2
	exit 1
fi
exit 0
