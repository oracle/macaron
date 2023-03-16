/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/oracle-samples/macaron/golang/internal/cue_validator"
)

// file.
// Params:
//
//	-file <FILE_PATH>: the path to the cue policy file
//	-input <SCRIPT_CONTENT>: the cue policy content in string
//
// Return code:
//
//	0 - Executed successfully.
//		If there is any errors storing to file, the result is still printed to stdout, but the errors are put to stderr.
//	1 - Error ocurred during execution.
func main() {
	policy_path := flag.String("policy", "", "The path to the cue policy file.")
	predicate_path := flag.String("provenance", "", "The SLSA provenance predicate.")
	validate := flag.Bool("validate", false, "Validate the cue policy against the provenance.")
	get_target := flag.Bool("get-target", false, "Get the target analysis for the input policy.")
	flag.Parse()

	var policy, predicate []byte

	if len(*policy_path) > 0 {
		// Read the policy file from file.
		var read_err error
		policy, read_err = os.ReadFile(*policy_path)
		if read_err != nil {
			fmt.Fprintln(os.Stderr, read_err.Error())
			os.Exit(1)
		}
	}

	if len(*predicate_path) > 0 {
		// Read the provenance predicate from file.
		var read_err error
		predicate, read_err = os.ReadFile(*predicate_path)
		if read_err != nil {
			fmt.Fprintln(os.Stderr, read_err.Error())
			os.Exit(1)
		}
	}

	if *validate {
		if policy != nil && predicate != nil {
			result, validate_err := cue_validator.ValidateJson(string(policy), string(predicate))
			if validate_err != nil {
				fmt.Fprintln(os.Stderr, validate_err.Error())
				os.Exit(1)
			}
			if result {
				fmt.Fprintln(os.Stdout, "Policy passed.")
				os.Exit(0)
			} else {
				fmt.Fprintln(os.Stdout, "Policy failed.")
				os.Exit(1)
			}
		} else {
			fmt.Fprintln(os.Stderr, "Usage: cue_validator -validate -policy <policy.cue> -predicate <predicate.json> ")
			os.Exit(1)
		}
	} else if *get_target {
		if policy != nil {
			result, target_err := cue_validator.GetTarget(string(policy))
			if target_err != nil {
				fmt.Fprintln(os.Stderr, target_err.Error())
				os.Exit(1)
			}
			fmt.Fprint(os.Stdout, result)
			os.Exit(0)
		} else {
			fmt.Fprintln(os.Stderr, "Usage: cue_validator -get-target -policy <policy.cue>")
			os.Exit(1)
		}
	} else {
		flag.PrintDefaults()
		os.Exit(1)
	}

	os.Exit(0)
}
