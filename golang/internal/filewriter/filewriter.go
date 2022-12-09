/* Copyright (c) 2022 - 2022, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package filewriter

import (
	"os"
)

// This method will overwrite any content if the file already
// exists.
func StoreBytesToFile(content []byte, file_name string) error {
	file, err := os.Create(file_name)
	if err != nil {
		return err
	}
	defer file.Close()

	// Write err will be nil if there is no errors
	_, write_err := file.Write(content)
	return write_err
}
