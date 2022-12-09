/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/oracle-samples/macaron/golang/internal/actionparser"
	"github.com/oracle-samples/macaron/golang/internal/filewriter"
)

// Parse the content of a GitHub Action yaml file and
// print the JSON format for it to stdout. It can also store the JSON content to a file.
// Params:
//
//	-file <FILE_PATH>: the path to the GitHub Actions file
//	-output <OUTPUT_FILE>: the output file path to store the JSON content.
//
// Return code:
//
//	0 - Parse successfully, return the JSON as string to stdout. If -output is set, store the json content to the file.
//		If there is any error storing to file, the result is still put to stdout, but the errors are put to stderr instead.
//	1 - Error: Missing workflow file path.
//	2 - Error: Could not parse the GitHub Action workflow files. Parse errors will be printed to stderr.
func main() {
	file_path := flag.String("file", "", "The path of the GitHub Actions workflow file.")
	out_path := flag.String("output", "", "The output file path to store the JSON content.")
	flag.Parse()

	if len(*file_path) <= 0 {
		fmt.Fprintln(os.Stderr, "Missing workflow file path.")
		flag.PrintDefaults()
		os.Exit(1)
	}

	json_content, err := actionparser.ParseActionFromFile(*file_path)
	if err == nil {
		fmt.Fprintln(os.Stdout, json_content)
		if len(*out_path) > 0 {
			err := filewriter.StoreBytesToFile([]byte(json_content), *out_path)
			if err != nil {
				fmt.Fprintln(os.Stderr, err.Error())
			}
		}
		os.Exit(0)
	} else {
		fmt.Fprintln(os.Stderr, err.Error())
		os.Exit(2)
	}
}
