# CUE Validator

This Go module validates CUE provenance against a policy and extracts analysis targets using [CUE](https://cuelang.org/).

### Run the CUE Validator directly

To run the validator, from the root directory of this repository:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -h
```


#### Commands:

- `-target-policy <policy_string>`: The CUE policy from which to extract the target.
- `-validate-policy <policy_string>`: The CUE policy to validate the provenance against.
- `-validate-provenance <provenance_string>`: The provenance data to validate.

### Examples:

1. **Extract Target from Policy**  
   To extract the target from a CUE policy, use the following command:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -target-policy '{"target": "https://github.com/my-repo"}'
```

Output:

```bash
Target: https://github.com/my-repo
```

2. **Validate Provenance Against Policy**  
To validate provenance against a policy, use the following command:

```bash
go run ./golang/cmd/cuevalidator/cuevalidator.go -validate-policy '{"target": "https://github.com/my-repo"}' -validate-provenance '{"commit": "abc123"}'
```

### Error Handling:

- If required arguments are missing or invalid, the program will print an error message to `stderr` and exit with a non-zero status code.
- If the validation fails, an error message will be printed, and the program will exit with an appropriate error code.
