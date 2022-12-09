# Action Parser

This go module handles parsing the GitHub Action workflows and return the content as JSON string. This module uses the [actionlint](https://github.com/rhysd/actionlint) library.

### Run the action parser directly
To run the parser, from the root dir of this repository:
```
go run ./golang/cmd/actionparser/actionparser.go -file <workflow_file_path> [-output <output_json_file>]
```
- `-file <workflow_file_path>`: The path to the GitHub Actions workflow file we want to parse.
- `-output <output_json_file>`: The path to the output json file.

If the GitHub Actions file is valid, the output JSON string is put to stdout and the application return a zero code. When there are errors, the error messages are put to stderr and the module will exit with non-zero code.

When there are errors while storing the JSON content to a file, the JSON string is still put to stdout, but those errors will be put to stderr.

### Example:
```
# Parse a valid GitHub Actions yaml file
go run ./golang/cmd/actionparser/actionparser.go -file ./golang/internal/actionparser/resources/valid.yaml -output ./result.json
```

When there are errors, the error messages are put to stderr and the module will exit with non-zero code.
```
# Parse an invalid GitHub Actions yaml file
go run ./golang/cmd/actionparser/actionparser.go -file ./golang/internal/actionparser/resources/invalid.yaml

# Error messages
# --------
# ./golang/internal/actionparser/resources/invalid.yaml:5:1: unexpected key "build" for "workflow" section. expected one of "concurrency", "defaults", "env", "jobs", "name", "on", "permissions" [syntax-check]
# ./golang/internal/actionparser/resources/invalid.yaml:7:1: unexpected key "integration-test" for "workflow" section. expected one of "concurrency", "defaults", "env", "jobs", "name", "on", "permissions" [syntax-check]
# ./golang/internal/actionparser/resources/invalid.yaml:1:1: "jobs" section is missing in workflow [syntax-check]
parse: errors while parsing the gitHub actions yaml file
# exit status 2
```
