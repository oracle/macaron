/* Copyright (c) 2025 - 2025, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/oracle/macaron/golang/internal/cuevalidator"
)

// Utility function to handle file reading and errors.
func readFile(path string) ([]byte, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("failed to read file '%s': %w", path, err)
	}
	return content, nil
}

// Handle validation errors.
func handleError(message string, code int) {
	fmt.Fprintln(os.Stderr, message)
	os.Exit(code)
}

// Main entry point for the CUE Validator tool.
// This function processes command-line flags to execute one of the following commands:
// - Extract a target from a CUE policy (using -target-policy flag).
// - Validate provenance against a CUE policy (using -validate-policy and -validate-provenance flags).
//
// Params:
//
//	-target-policy <CUE_POLICY>: the CUE policy to extract the target from.
//	-validate-policy <CUE_POLICY>: the CUE policy to validate the provenance against.
//	-validate-provenance <PROVENANCE_DATA>: the provenance data to validate.
//
// Return code:
//
//	0 - If the target is successfully extracted or the provenance validation finishes with no errors.
//	1 - If there is a missing required argument or invalid command usage.
//	2 - If an error occurs during validation (e.g., invalid provenance or policy).
//
// Usage:
//
//  1. To extract the target from a policy:
//     go run cuevalidator.go -target-policy <CUE_POLICY>
//     Output: The extracted target will be printed to stdout.
//
//  2. To validate provenance against a policy:
//     go run cuevalidator.go -validate-policy <CUE_POLICY> -validate-provenance <PROVENANCE_DATA>
//     Output: A success or failure message will be printed based on the validation result.
func main() {
	// Define flags for the target command.
	targetPolicy := flag.String("target-policy", "", "Path to CUE policy to extract the target from.")

	// Define flags for the validate command
	validatePolicy := flag.String("validate-policy", "", "Path to CUE policy to validate against.")
	validateProvenance := flag.String("validate-provenance", "", "Path to provenance data to validate.")

	// Parse flags
	flag.Parse()

	// Handle 'target-policy' command.
	if *targetPolicy != "" {
		policyContent, err := readFile(*targetPolicy)
		if err != nil {
			handleError(err.Error(), 2)
		}

		result := cuevalidator.Target(string(policyContent))
		if result == "" {
			handleError("Error: Unable to extract target from policy.", 2)
		}

		fmt.Print(result)
		return
	}

	// Handle 'validate' command.
	if *validatePolicy != "" && *validateProvenance != "" {
		policyContent, err := readFile(*validatePolicy)
		if err != nil {
			handleError(err.Error(), 2)
		}

		provenanceContent, err := readFile(*validateProvenance)
		if err != nil {
			handleError(err.Error(), 2)
		}

		result := cuevalidator.Validate(string(policyContent), string(provenanceContent))
		switch result {
		case 1:
			fmt.Print("True")
			os.Exit(0)
		case 0:
			fmt.Print("False")
			os.Exit(0)
		default:
			handleError("Error: Validation encountered an issue.", 2)
		}
		return
	}

	// If no valid command was given, print usage message
	handleError("Error: Missing required arguments for target or validate command.", 1)
}
