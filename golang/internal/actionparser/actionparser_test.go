/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package actionparser

import (
	"encoding/json"
	"testing"
)

func Test_parse_invalid_workflow_files(t *testing.T) {
	invalid_yaml := "resources/invalid.yaml"
	_, err := ParseActionFromFile(invalid_yaml)
	if err == nil {
		t.Errorf("Expecting parse errors for %s, got no errors.", invalid_yaml)
	}
}

func Test_parse_valid_workflow_files(t *testing.T) {
	valid_yaml := "resources/valid.yaml"
	data, err := ParseActionFromFile(valid_yaml)
	if (err != nil) || (data == "") {
		t.Errorf("Expect successful parsing, got error: %s and result JSON: \n %s", err, data)
	}
}

func Test_with_file_not_found(t *testing.T) {
	not_found_yaml := "resources/file_not_found.yaml"
	_, err := ParseActionFromFile(not_found_yaml)
	if err == nil {
		t.Errorf("Expect error when trying to read a file not found, got no error.")
	}
}

func Test_the_return_JSON_content(t *testing.T) {
	valid_yaml := "resources/valid.yaml"
	json_content, _ := ParseActionFromFile(valid_yaml)
	var result map[string]interface{}
	err := json.Unmarshal([]byte(json_content), &result)
	if err != nil {
		t.Errorf(string(err.Error()))
		t.Errorf("Cannot unmarshal the returned JSON content from parsing %s.", valid_yaml)
	}
}
