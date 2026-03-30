/* Copyright (c) 2022 - 2026, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// Package bashparser parses the bash scripts and provides parsed objects in JSON.
package bashparser

import (
	"bytes"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"mvdan.cc/sh/v3/syntax"
	"mvdan.cc/sh/v3/syntax/typedjson"
)

// CMDResult is used to export the bash command results in JSON.
type CMDResult struct {
	Commands [][]string `json:"commands"`
}

// RawWithGHAMapResult is used to export the raw bash AST with a GitHub-expression mapping.
type RawWithGHAMapResult struct {
	AST        any               `json:"ast"`
	GHAExprMap map[string]string `json:"gha_expr_map"`
}

func preprocessGitHubActionsExpr(data string) (string, error) {
	// Replace GitHub Actions's expressions with ``$MACARON_UNKNOWN``` variable because the bash parser
	// doesn't recognize such expressions. For example: ``${{ foo }}`` will be replaced by ``$MACARON_UNKNOWN``.
	// Note that we don't use greedy matching, so if we have `${{ ${{ foo }} }}`, it will not be replaced by
	// `$MACARON_UNKNOWN`.
	// See: https://docs.github.com/en/actions/learn-github-actions/expressions.
	re, reg_error := regexp.Compile(`\$\{\{.*?\}\}`)
	if reg_error != nil {
		return "", reg_error
	}
	// We replace the GH Actions variables with "$MACARON_UNKNOWN".
	return string(re.ReplaceAll([]byte(data), []byte("$$MACARON_UNKNOWN"))), nil
}

func preprocessGitHubActionsExprWithMap(data string) (string, map[string]string, error) {
	// Replace GitHub Actions expressions with unique bash-safe placeholders and return
	// a mapping from placeholder variable names to the original expression body.
	//
	// Example:
	//   input:  echo "${{ github.head_ref }}"
	//   output: echo "$MACARON_GHA_0001", {"MACARON_GHA_0001": "github.head_ref"}
	//
	// This preserves expression identity for downstream analysis while keeping the
	// transformed script parseable by the bash parser.
	re, reg_error := regexp.Compile(`\$\{\{.*?\}\}`)
	if reg_error != nil {
		return "", nil, reg_error
	}

	index := 0
	ghaMap := make(map[string]string)
	processed := re.ReplaceAllStringFunc(data, func(match string) string {
		index += 1
		key := fmt.Sprintf("MACARON_GHA_%04d", index)
		expr := strings.TrimSpace(strings.TrimSuffix(strings.TrimPrefix(match, "${{"), "}}"))
		ghaMap[key] = expr
		return "$" + key
	})

	return processed, ghaMap, nil
}

// ParseCommands parses the bash script to find bash commands.
// It returns the parsed commands in JSON format.
func ParseCommands(data string) (string, error) {
	processed, preprocessErr := preprocessGitHubActionsExpr(data)
	if preprocessErr != nil {
		return "", preprocessErr
	}

	data_str := strings.NewReader(processed)
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
	processed, preprocessErr := preprocessGitHubActionsExpr(data)
	if preprocessErr != nil {
		return "", preprocessErr
	}

	data_str := strings.NewReader(processed)
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

// ParseRawWithGitHubExprMap parses raw bash AST and returns it with a GitHub-expression placeholder mapping.
func ParseRawWithGitHubExprMap(data string) (string, error) {
	processed, ghaMap, preprocessErr := preprocessGitHubActionsExprWithMap(data)
	if preprocessErr != nil {
		return "", preprocessErr
	}

	data_str := strings.NewReader(processed)
	data_parsed, parse_err := syntax.NewParser().Parse(data_str, "")
	if parse_err != nil {
		return "", parse_err
	}

	b := new(strings.Builder)
	encode_err := typedjson.Encode(b, data_parsed)
	if encode_err != nil {
		return "", encode_err
	}

	var astObj any
	if unmarshalErr := json.Unmarshal([]byte(b.String()), &astObj); unmarshalErr != nil {
		return "", unmarshalErr
	}

	result := RawWithGHAMapResult{
		AST:        astObj,
		GHAExprMap: ghaMap,
	}
	resultBytes, marshalErr := json.MarshalIndent(result, "", "  ")
	if marshalErr != nil {
		return "", marshalErr
	}
	return string(resultBytes), nil
}

func Parse(data string, raw bool) (string, error) {
	if raw {
		return ParseRaw(data)
	} else {
		return ParseCommands(data)
	}
}

func ParseExpr(data string) (string, error) {
	data_str := strings.NewReader(data)
	result_str := "["
	first := true
	for word_parsed, parse_err := range syntax.NewParser().WordsSeq(data_str) {
		if parse_err != nil {
			return "", parse_err
		}
		b := new(strings.Builder)
		encode_err := typedjson.Encode(b, word_parsed)
		if encode_err != nil {
			return "", encode_err
		}
		if first {
			result_str = result_str + b.String()
			first = false
		} else {
			result_str = result_str + ", " + b.String()
		}
	}
	result_str = result_str + "]"
	return result_str, nil
}
