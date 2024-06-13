/* Copyright (c) 2022 - 2024, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// Package bashparser parses the bash scripts and provides parsed objects in JSON.
package bashparser

import (
	"bytes"
	"encoding/json"
	"regexp"
	"strings"

	"mvdan.cc/sh/v3/syntax"
	"mvdan.cc/sh/v3/syntax/typedjson"
)

// CMDResult is used to export the bash command results in JSON.
type CMDResult struct {
	Commands [][]string `json:"commands"`
}

// ParseCommands parses the bash script to find bash commands.
// It returns the parsed commands in JSON format.
func ParseCommands(data string) (string, error) {
	// Replace GitHub Actions's expressions with ``$MACARON_UNKNOWN``` variable because the bash parser
	// doesn't recognize such expressions. For example: ``${{ foo }}`` will be replaced by ``$MACARON_UNKNOWN``.
	// Note that we don't use greedy matching, so if we have `${{ ${{ foo }} }}`, it will not be replaced by
	// `$MACARON_UNKNOWN`.
	// See: https://docs.github.com/en/actions/learn-github-actions/expressions.
	var re, reg_error = regexp.Compile(`\$\{\{.*?\}\}`)
	if reg_error != nil {
		return "", reg_error
	}

	// We replace the GH Actions variables with "$MACARON_UNKNOWN".
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

func ParseRaw(data string) (string, error) {
	// Replace GitHub Actions's expressions with ``$MACARON_UNKNOWN``` variable because the bash parser
	// doesn't recognize such expressions. For example: ``${{ foo }}`` will be replaced by ``$MACARON_UNKNOWN``.
	// Note that we don't use greedy matching, so if we have `${{ ${{ foo }} }}`, it will not be replaced by
	// `$MACARON_UNKNOWN`.
	// See: https://docs.github.com/en/actions/learn-github-actions/expressions.
	var re, reg_error = regexp.Compile(`\$\{\{.*?\}\}`)
	if reg_error != nil {
		return "", reg_error
	}

	// We replace the GH Actions variables with "$MACARON_UNKNOWN".
	data = string(re.ReplaceAll([]byte(data), []byte("$$MACARON_UNKNOWN")))
	data_str := strings.NewReader(data)
	data_parsed, parse_err := syntax.NewParser().Parse(data_str, "")
	if parse_err != nil {
		return "", parse_err
	}

	b := new(strings.Builder)
	encode_err := typedjson.Encode(b, data_parsed)
	if encode_err != nil {
		return "", encode_err
	}

	return b.String(), nil
}

func Parse(data string, raw bool) (string, error) {
	if raw {
		return ParseRaw(data)
	} else {
		return ParseCommands(data)
	}
}
