/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// Package bashparser parses the bash scripts and provides parsed objects in JSON.
package bashparser

import (
	"bytes"
	"encoding/json"
	"regexp"
	"strings"

	"mvdan.cc/sh/v3/syntax"
)

// CMDResult is used to export the bash command results in JSON.
type CMDResult struct {
	Commands [][]string `json:"commands"`
}

// ParseCommands parses the bash script to find bash commands.
// It returns the parsed commands in JSON format.
func ParseCommands(data string) (string, error) {
	// Remove GitHub Actions's expressions because the bash parser doesn't recognize it.
	// We use greedy matching, so if we have `${{ $ {{ foo }} }}`, it will be matched
	// to `$MACARON_UNKNOWN`, even though it's not a valid GitHub expression.
	// See: https://docs.github.com/en/actions/learn-github-actions/expressions.
	var re, reg_error = regexp.Compile(`\$\{\{.*\}\}`)
	if reg_error != nil {
		return "", reg_error
	}

	// We replace the GH Actions variables with "UNKNOWN" for now.
	data = string(re.ReplaceAll([]byte(data), []byte("$$MACARON_UNKNOWN")))
	data_str := strings.NewReader(data)
	data_parsed, parse_err := syntax.NewParser().Parse(data_str, "")
	if parse_err != nil {
		return "", parse_err
	}

	// Use the parser's printer module for serializing the nodes.
	printer := syntax.NewPrinter()

	// Walk the AST to find the bash command nodes.
	var commands [][]string
	syntax.Walk(data_parsed, func(node syntax.Node) bool {
		switch x := node.(type) {
		case *syntax.CallExpr:
			args := x.Args
			var cmd []string
			for _, word := range args {
				var buffer bytes.Buffer
				printer.Print(&buffer, word)
				cmd = append(cmd, buffer.String())
			}
			if cmd != nil {
				commands = append(commands, cmd)
			}
		}
		return true
	})
	cmd_result := CMDResult{Commands: commands}
	result_bytes, json_err := json.MarshalIndent(cmd_result, "", "  ")
	if json_err != nil {
		return "", json_err
	}
	return string(result_bytes), nil

}
