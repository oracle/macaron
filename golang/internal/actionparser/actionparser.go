/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// Package actionparser parses GitHub Actions and provides the parsed object in JSON.
package actionparser

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/rhysd/actionlint"
)

// printParseErrs prints the parse errors from actionlint to w.
func printParseErrs(w io.Writer, file_path string, errs []*actionlint.Error) {
	for _, err := range errs {
		err.Filepath = file_path
		fmt.Fprintln(w, err.Error())
	}
}

// ParseActionFromFile parses the content of the given yaml file.
// It returns the parsed object in JSON format.
func ParseActionFromFile(file string) (string, error) {
	data, read_err := os.ReadFile(file)
	if read_err != nil {
		return "", read_err
	}

	workflow, parse_err := actionlint.Parse(data)
	if parse_err != nil {
		printParseErrs(os.Stderr, file, parse_err)
		return "", errors.New("parse: errors while parsing the gitHub actions yaml file")
	}

	result, json_err := json.MarshalIndent(workflow, "", "  ")
	if json_err != nil {
		return "", json_err
	}

	return string(result), nil
}
