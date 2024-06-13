/* Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/oracle/macaron/golang/internal/bashparser"
	"github.com/oracle/macaron/golang/internal/filewriter"
)

// Parse the bash script and provide parsed objects in JSON format to stdout or a file.
// Params:
//
//	-file <FILE_PATH>: the path to the bash script file
//	-input <SCRIPT_CONTENT>: the bash script content in string
//	-output <OUTPUT_FILE>: the output file path to store the JSON content
//
// Return code:
//
//	0 - Parse successfully, return the JSON as string to stdout. If -output is set, store the json content to the file.
//		If there is any errors storing to file, the result is still printed to stdout, but the errors are put to stderr instead.
//	1 - Error: Missing bash script or output file paths.
//	2 - Error: Could not parse the bash script file. Parse errors will be printed to stderr.
func main() {
	file_path := flag.String("file", "", "The path of the bash script file.")
	input := flag.String("input", "", "The bash script content to be parsed. Input is prioritized over file option.")
	out_path := flag.String("output", "", "The output file path to store the JSON content.")
	raw := flag.Bool("raw", false, "Return raw parse-tree")
	flag.Parse()

	var json_content string
	var parse_err error
	if len(*input) > 0 {
		// Read the bash script from command line argument.
		json_content, parse_err = bashparser.Parse(*input, *raw)
	} else if len(*file_path) <= 0 {
		fmt.Fprintln(os.Stderr, "Missing bash script input or file path.")
		flag.PrintDefaults()
		os.Exit(1)
	} else {
		// Read the bash script from file.
		data, read_err := os.ReadFile(*file_path)
		if read_err != nil {
			fmt.Fprintln(os.Stderr, read_err.Error())
			os.Exit(1)
		}
		json_content, parse_err = bashparser.Parse(string(data), *raw)
	}

	if parse_err != nil {
		fmt.Fprintln(os.Stderr, parse_err.Error())
		os.Exit(2)
	}

	fmt.Fprintln(os.Stdout, json_content)

	if len(*out_path) > 0 {
		err := filewriter.StoreBytesToFile([]byte(json_content), *out_path)
		if err != nil {
			fmt.Fprintln(os.Stderr, err.Error())
			os.Exit(1)
		}
	}

	os.Exit(0)
}
