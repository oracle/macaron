/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"testing"
)

func Test_Target(t *testing.T) {
	tests := []struct {
		name     string
		path     string
		expected string
	}{
		{
			name:     "get target from invalid policy",
			path:     "invalid_policy.cue",
			expected: GetGoString(nil),
		},
		{
			name:     "get target from valid policy",
			path:     "valid_policy.cue",
			expected: "urllib3/urllib3",
		},
	}
	for _, test := range tests {
		test := test // Re-initialize the test.
		t.Run(test.name, func(t *testing.T) {
			policy := LoadResource(t, test.path)
			value := target(policy)

			// GoLang doesn’t provide any built-in support for assert.
			if GetGoString(value) != test.expected {
				t.Errorf("Expected %s but got %s.", test.expected, GetGoString(value))
			}
		})
	}
}

func Test_ValidatePolicy(t *testing.T) {
	tests := []struct {
		name            string
		policy_path     string
		provenance_path string
		expected        int32
	}{
		{
			name:            "validate policy with invalid provenance",
			policy_path:     "valid_policy.cue",
			provenance_path: "invalid_provenance.json",
			expected:        -1,
		},
		{
			name:            "validate invalid policy with invalid provenance",
			policy_path:     "invalid_policy.cue",
			provenance_path: "invalid_provenance.json",
			expected:        -1,
		},
		{
			name:            "validate invalid policy with valid provenance",
			policy_path:     "invalid_policy.cue",
			provenance_path: "valid_provenance.json",
			expected:        0,
		},
		{
			name:            "validate valid policy with valid provenance that conform",
			policy_path:     "valid_policy.cue",
			provenance_path: "valid_provenance.json",
			expected:        1,
		},
		{
			name:            "validate valid policy with valid provenance that do not conform",
			policy_path:     "valid_policy.cue",
			provenance_path: "valid_provenance2.json",
			expected:        0,
		},
	}

	for _, test := range tests {
		test := test // Re-initialize the test.
		t.Run(test.name, func(t *testing.T) {
			policy := LoadResource(t, test.policy_path)
			provenance := LoadResource(t, test.provenance_path)
			result := validate(policy, provenance)
			if result != test.expected {
				t.Errorf("Expected %d but got %d.", test.expected, result)
			}
		})
	}
}
