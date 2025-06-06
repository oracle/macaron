/* Copyright (c) 2023 - 2025, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// CUE Validator runs CUE and validates a provenance against a policy.
// See: https://cuelang.org/docs/about/

package cuevalidator

import (
	"strings"

	"cuelang.org/go/cue"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/encoding/json"
)

// Target extracts the target from a given CUE policy string.
// It returns the extracted target if successful, or an empty string if an error occurs.
func Target(policy string) string {
	ctx := cuecontext.New()
	value := ctx.CompileString(policy)
	policyErr := value.Err()
	if policyErr != nil {
		return ""
	}

	targetValue := value.LookupPath(cue.ParsePath("target"))
	targetErr := targetValue.Err()
	if targetErr != nil {
		return ""
	}
	targetPath, strErr := targetValue.String()
	if strErr != nil {
		return ""
	}

	return strings.TrimSpace(targetPath)
}

// Validate validates the provenance against the given CUE policy.
// It returns 1 if the provenance conforms to the policy, 0 if it does not, and -1 if there is an unexpected error.
func Validate(policy string, provenance string) int32 {
	ctx := cuecontext.New()
	value := ctx.CompileString(policy)

	resolvedValue := ctx.CompileString(provenance, cue.Scope(value))
	resErr := resolvedValue.Err()
	if resErr != nil {
		// Unable to process the provenance.
		return -1
	}

	validateErr := json.Validate([]byte(provenance), value)
	if validateErr != nil {
		// Validation failed.
		return 0
	}

	// The provenance conforms with the policy.
	return 1
}
