/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

// This module provides CGO helper functions for testing.
package main

import (
	"C"
	"os"
	"path"
	"runtime"
	"testing"
)

// Get the path to the resources directory.
func GetResourcesPath(t *testing.T) string {
	_, filename, _, ok := runtime.Caller(1)
	if !ok {
		t.Errorf("Unable to locate resources.")
	}
	return path.Join(path.Dir(filename), "resources")
}

// Load resource file.
func LoadResource(t *testing.T, name string) *C.char {
	path := path.Join(GetResourcesPath(t), name)
	content, err := os.ReadFile(path)
	if err != nil {
		t.Errorf("Unable to load the policy content from %s.", path)
	}
	return C.CString(string(content))
}

func GetGoString(value *C.char) string {
	return C.GoString(value)
}
