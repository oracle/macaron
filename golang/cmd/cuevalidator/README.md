# CUE Validator

This Go module validates CUE provenance against a policy and extracts analysis targets using [CUE](https://cuelang.org/).

### Run the CUE Validator directly

To run the validator, from the root directory of this repository:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -h
```


#### Commands:

- `-target-policy <cue-policy-path>`: The CUE policy path from which to extract the target.
- `-validate-policy <cue-policy-path>`: The CUE policy path to validate the provenance against.
- `-validate-provenance <provenance-path>`: The provenance payload path to validate.

### Examples:

1. **Extract Target from Policy**  
   To extract the target from a CUE policy, use the following command:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -target-policy <path-to-cue-policy>
```

Output:

```bash
pkg:maven/io.micronaut/micronaut-core
```

2. **Validate Provenance Against Policy**  
To validate provenance against a policy, use the following command:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -validate-policy <path-to-cue-policy> -validate-provenance <path-to-provenance-payload>
```

### Error Handling:

- If required arguments are missing or invalid, the program will print an error message to `stderr` and exit with a non-zero status code.
- If the validation fails, an error message will be printed, and the program will exit with an appropriate error code.
