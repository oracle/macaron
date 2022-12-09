# Bash Parser

This go module parses bash scripts using the [sh](https://github.com/mvdan/sh) library.

### Run the bash parser directly
To run the parser, from the root dir of this repository:
```
go run ./golang/cmd/bashparser/bashparser.go -h
```
- `-file <bash_file_path>`: The path of the bash script file.
- `-input <string>`: The bash script content to be parsed. Input is prioritized over file option.
- `-output <output_json_file>`: The path to the output json file.

If the bash file is valid, the output JSON string is put to stdout and the application return a zero code. When there are errors, the error messages are put to stderr and the module will exit with non-zero code.

When there are errors while storing the JSON content to a file, the JSON string is still put to stdout, but those errors will be put to stderr.
