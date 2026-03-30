/* Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package bashparser

import (
	"encoding/json"
	"os"
	"strings"
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
		t.Errorf("Cannot unmarshal the returned JSON content from parsing %s: %v.", json_content, err)
	}
}

func Test_parse_raw_with_gha_expr_map(t *testing.T) {
	input := `echo "${{ github.head_ref }}" && echo "${{ needs.prepare.outputs.fullVersion }}"`
	json_content, parse_err := ParseRawWithGitHubExprMap(input)
	if parse_err != nil || json_content == "" {
		t.Fatalf("expected successful parse with mapping, got error: %v", parse_err)
	}

	var result map[string]any
	if err := json.Unmarshal([]byte(json_content), &result); err != nil {
		t.Fatalf("cannot unmarshal parser output: %v", err)
	}

	ast, astOK := result["ast"]
	if !astOK || ast == nil {
		t.Fatalf("expected non-empty ast field")
	}

	mapRaw, mapOK := result["gha_expr_map"]
	if !mapOK {
		t.Fatalf("expected gha_expr_map field")
	}
	ghaMap, ok := mapRaw.(map[string]any)
	if !ok {
		t.Fatalf("expected gha_expr_map to be an object")
	}
	if len(ghaMap) != 2 {
		t.Fatalf("expected 2 mapped expressions, got %d", len(ghaMap))
	}
}

func Test_preprocess_github_actions_expr_with_map_replaces_with_single_dollar_var(t *testing.T) {
	input := `echo "${{ github.head_ref }}"`
	processed, ghaMap, err := preprocessGitHubActionsExprWithMap(input)
	if err != nil {
		t.Fatalf("unexpected preprocess error: %v", err)
	}
	if strings.Contains(processed, "$$MACARON_GHA_") {
		t.Fatalf("expected single-dollar placeholder, got %q", processed)
	}
	if !strings.Contains(processed, "$MACARON_GHA_0001") {
		t.Fatalf("expected placeholder var in processed script, got %q", processed)
	}
	if ghaMap["MACARON_GHA_0001"] != "github.head_ref" {
		t.Fatalf("unexpected gha mapping: %#v", ghaMap)
	}
}
