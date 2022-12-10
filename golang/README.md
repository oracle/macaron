# Go module documentation
## Quick start
Prerequisites
- Go (tested on `go1.17.8 linux/amd64`). Installation instructions [here](https://go.dev/doc/install).

- Prepare the required libraries by running this command from the root dir of this repository:
```
go mod download
```
This command will download all packages as defined in [go.mod](../../../go.mod) and [go.sum](../../../go.sum).

### Project layout
This go module follows the Golang project layout as specified in [golang-standards/project-layout](https://github.com/golang-standards/project-layout).

```
macaron
├── golang
│   ├── cmd
│   │   └── actionparser
│   ├── internal
│   │   ├── actionparser
│   │   └── filewriter
│   ├── pkg
│   └── README.md
├── go.mod
├── go.sum
└── <other files in the root repository ...>
```

- `golang` is the directory where all Go source files and tests are located. This is to separate it from `python` where the code for Macaron sit.
- The `cmd` dir contains the main applications of the module. The applications usually don't have a lot of code. These applications will import and use code from `internal` or `pkg`.
- The `internal` dir contains the internal code that we don't want others importing. This is also enforced by Go itself - check [here](https://go.dev/doc/go1.4#internalpackages) for more information.
- The `pkg` dir contains code that we want to share with anyone who use our go module. They can import those libraries so we should expect code in this directory to work properly. This dir is empty at the moment.
- `go.mod` and `go.sum` contain the metadata (checksum, semantic versions, etc.) of required libraries, the name of the Go module and the Go version.

### Run the application code directly using Go
To run an application (in the `cmd` dir), from the root dir of this repository:
```
go run ./golang/cmd/<app_name>/<app_name>.go [ARGS]
```

For example, to run the [actionparser](./cmd/actionparser/README.md) application:
```
go run ./golang/cmd/actionparser/actionparser.go -file ./golang/internal/actionparser/resources/valid.yaml
```
### Run the Go tests

To run all the tests, from the root dir of this repository:
```
go test ./golang/...
```

To run the tests and record the code coverage, from the root dir of this repository:
```
go test -cover ./golang/...
```

### Build the executable
To build an executable of an application in this module:
```
go build ./golang/cmd/<app_name>/<app_name>.go
```
This will generate an executable `app_name` in the current directory. We can also change the path of the output executable by using:
```
go build -o <output_path> ./golang/cmd/<app_name>/<app_name>.go
```

For example, to build and run an executable for the actionparser application in the current directory:
```
go build -o ./actionparser ./golang/cmd/actionparser/actionparser.go

./actionparser -file ./golang/internal/actionparser/resources/valid.yaml
```
