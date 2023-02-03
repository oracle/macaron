/* Copyright (c) 2023 - 2023, Oracle and/or its affiliates. All rights reserved. */
/* Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/. */

package main

// #cgo LDFLAGS: -shared
import "C"
import "fmt"
import "cuelang.org/go/cue/cuecontext"
import "cuelang.org/go/cue"
import "cuelang.org/go/encoding/json"

//export validate_json
func validate_json(_policy *C.char, _document *C.char) int32 {

	policy := C.GoString(_policy)
	document := C.GoString(_document)

	ctx := cuecontext.New()
	value := ctx.CompileString(policy)

	resolved_value := ctx.CompileString(document, cue.Scope(value))
	err2 := resolved_value.Err()
	if err2 != nil {
		fmt.Println("CUE: ", err2)
		return 0
	}

	res2 := json.Validate([]byte(document), value)
	if res2 != nil {
		fmt.Println("CUE: ", res2)
		return 0
	}

	return 1
}

func main() {
}
