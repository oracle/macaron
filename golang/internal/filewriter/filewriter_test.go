/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package filewriter

import (
	"os"
	"testing"
)

func Test_store_to_dir(t *testing.T) {
	dir_name := "./mock_dir"
	err := StoreBytesToFile([]byte("Some JSON content"), dir_name)
	if err == nil {
		t.Errorf("Expect errors when trying to write to a directory, got none.")
	}
}

func Test_store_to_file(t *testing.T) {
	out_path := "./mock_dir/result.json"
	store_content := "Some JSON content"
	err := StoreBytesToFile([]byte("Some JSON content"), out_path)
	if err != nil {
		t.Errorf("Cannot write to a file.")
	}

	read_content, err := os.ReadFile(out_path)
	if err != nil {
		t.Errorf("Error when trying to store to %s.", out_path)
		t.Errorf(err.Error())
	} else {
		if string(read_content) != store_content {
			t.Errorf("The store content is not correct")
			t.Errorf("Expect: %s", store_content)
			t.Errorf("Got: %s", read_content)
		}
	}
}
