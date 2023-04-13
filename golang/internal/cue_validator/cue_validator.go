/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// CUE Validator runs CUE and validates a provenance against a policy.
// See: https://cuelang.org/docs/about/

package main

import (
	"C"
	"strings"

	"cuelang.org/go/cue"
	"cuelang.org/go/cue/cuecontext"
	"cuelang.org/go/encoding/json"
)

// target returns the analysis target repo for the provided policy content.
// Returns target string value if successful and nil if error has occurred.
//
//export target
func target(policy *C.char) *C.char {
	ctx := cuecontext.New()
	_policy := C.GoString(policy)
	value := ctx.CompileString(_policy)
	policy_err := value.Err()
	if policy_err != nil {
		return nil
	}

	target_value := value.LookupPath(cue.ParsePath("target"))
	target_err := target_value.Err()
	if target_err != nil {
		return nil
	}
	target_path, str_err := target_value.String()
	if str_err != nil {
		return nil
	}

	// We need to be careful about memory leaks on the Python side.
	// The documentation at https://pkg.go.dev/cmd/cgo says:
	// The C string is allocated in the C heap using malloc.
	// It is the caller's responsibility to arrange for it to be
	// freed.
	return C.CString(strings.TrimSpace(target_path))
}

// validate validates the provenance against a CUE policy.
// Returns 1 if policy conforms with the provenance, 0 if
// provenance is invalid, and -1 if CUE returns a validation error.
//
//export validate
func validate(policy *C.char, provenance *C.char) int32 {
	_policy := C.GoString(policy)
	_provenance := C.GoString(provenance)

	ctx := cuecontext.New()
	value := ctx.CompileString(_policy)

	resolved_value := ctx.CompileString(_provenance, cue.Scope(value))
	res_err := resolved_value.Err()
	if res_err != nil {
		// Unable to process the provenance.
		return -1
	}

	validate_err := json.Validate([]byte(_provenance), value)
	if validate_err != nil {
		// Validation failed.
		return 0
	}

	// The provenance conforms with the policy.
	return 1
}

func main() {

}
