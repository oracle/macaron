/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package bashparser

import (
	"encoding/json"
	"os"
	"testing"
)

func Test_parse_invalid_bash_script(t *testing.T) {
	invalid_bash := "{ invalid: invalid }"
	_, err := ParseCommands(invalid_bash)
	if err == nil {
		t.Errorf("Expecting parse errors but got no errors.")
	}
}

func Test_parse_valid_bash_script(t *testing.T) {
	valid_bash, read_err := os.ReadFile("resources/valid.sh")
	if read_err != nil {
		t.Errorf("Could not read test file: \n %s", read_err)
	}
	json_content, parse_err := ParseCommands(string(valid_bash))
	if (parse_err != nil) || (json_content == "") {
		t.Errorf("Expect successful parsing, got error: %s and result JSON: \n %s", parse_err, json_content)
	}
	var result map[string]interface{}
	err := json.Unmarshal([]byte(json_content), &result)
	if err != nil {
		t.Errorf(string(err.Error()))
		t.Errorf("Cannot unmarshal the returned JSON content from parsing %s.", json_content)
	}
}
