/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package cue_validator

import (
	"errors"
	"strings"

	"cuelang.org/go/cue"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/encoding/json"
)

// Get the target analysis for the provided policy.
func GetTarget(policy string) (string, error) {
	ctx := cuecontext.New()
	value := ctx.CompileString(policy)
	policy_err := value.Err()
	if policy_err != nil {
		return "", policy_err
	}

	target_value := value.LookupPath(cue.ParsePath("target"))
	target_err := target_value.Err()
	if target_err != nil {
		return "", target_err
	}
	target_path, str_err := target_value.String()
	if str_err != nil {
		return "", str_err
	}
	return strings.TrimSpace(target_path), nil
}

// Validate if the policy conforms with the provenance document.
func ValidateJson(policy string, document string) (bool, error) {

	ctx := cuecontext.New()
	value := ctx.CompileString(policy)
	policy_err := value.Err()
	if policy_err != nil {
		return false, policy_err
	}

	if value.LookupPath(cue.ParsePath("predicate")).Err() != nil {
		return false, errors.New("policy: predicate attribute is missing")
	}

	resolved_value := ctx.CompileString(document, cue.Scope(value))
	value_err := resolved_value.Err()
	if value_err != nil {
		return false, value_err
	}

	if resolved_value.LookupPath(cue.ParsePath("predicate")).Err() != nil {
		return false, errors.New("provenance: predicate attribute is missing")
	}

	validation_error := json.Validate([]byte(document), value)
	if validation_error != nil {
		return false, validation_error
	}

	return true, nil
}

func main() {
}
