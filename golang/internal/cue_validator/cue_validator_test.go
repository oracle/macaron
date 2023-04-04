/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"testing"
)

func Test_target(t *testing.T) {
	// Test an invalid policy.
	invalid_policy := LoadResource(t, "invalid_policy.cue")
	value := target(invalid_policy)
	if value != nil {
		t.Errorf("Expected errors but got none.")
	}

	// Test getting the target from a valid policy.
	valid_policy := LoadResource(t, "valid_policy.cue")

	value = target(valid_policy)
	if value == nil {
		t.Errorf("Unexpected error.")
	}
	// GoLang doesn’t provide any built-in support for assert.
	expected_target := "urllib3/urllib3"
	if GetGoString(value) != expected_target {
		t.Errorf("%s does not match expected value %s.", GetGoString(value), expected_target)
	}
}

func Test_validatePolicy(t *testing.T) {
	// Load resources.
	invalid_policy := LoadResource(t, "invalid_policy.cue")
	valid_policy := LoadResource(t, "valid_policy.cue")
	invalid_prov := LoadResource(t, "invalid_provenance.json")
	valid_prov := LoadResource(t, "valid_provenance.json")
	valid_prov2 := LoadResource(t, "valid_provenance2.json")

	var result int32
	var expected int32

	// Test valid policy and invalid provenance.
	result = validate(valid_policy, invalid_prov)
	expected = -1
	if result != expected {
		t.Errorf("%d does not match expected value %d.", result, expected)
	}

	// Test invalid policy and invalid provenance.
	result = validate(invalid_policy, invalid_prov)
	expected = -1
	if result != expected {
		t.Errorf("%d does not match expected value %d.", result, expected)
	}

	// Test invalid policy and valid provenance.
	result = validate(invalid_policy, valid_prov)
	expected = 0
	if result != expected {
		t.Errorf("%d does not match expected value %d.", result, expected)
	}

	// Test valid policy and valid provenance.
	result = validate(valid_policy, valid_prov)
	expected = 1
	if result != expected {
		t.Errorf("%d does not match expected value %d.", result, expected)
	}

	// Test a valid policy and valid provenance that do not conform.
	result = validate(valid_policy, valid_prov2)
	expected = 0
	if result != expected {
		t.Errorf("%d does not match expected value %d.", result, expected)
	}
}
