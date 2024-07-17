# Macaron Integration Tests


## Integration Test Utility

We have an integration test utility script, [`./tests/integration/run.py`](./run.py), for running integration tests. The script should be called within the dev virtual environment and from the root directory of the repository.

```bash
$ python ./tests/integration/run.py -h
usage: ./tests/integration/run.py [-h] {check,vet,run,update} ...

positional arguments:
  {check,vet,run,update}
                        The command to run.
    check               Schema-validate test case config files in the test data directory.
    vet                 Validate test case directories.
    run                 Run test cases in the test data directory.
    update              Run test cases, but update expected output files instead of
                        comparing them with expected output.

options:
  -h, --help            show this help message and exit
```

The utility offers 4 different commands, as shown in the help message above. Some example usages for these commands will be introduced later in the [Example Usages section](#example-usages). You can also have a look at the help message of each command by providing `<command> -h` to the script.

```bash
# Show help message for the check command.
$ python ./tests/integration/run.py check -h
```


## Test Case Configuration

The utility interacts with integration test cases. Each test case locates in a single directory containing a test config file `test.yaml`, alongside other files required for the test case (e.g. config files, policy files, provenance expectation files).

Here is an example. The test case directory looks like this. Alongside the `test.yaml` file, there is a file named `analysis_report.json` storing the expected output of an analysis report.

```
./tests/integration/cases/apache_maven/
├── analysis_report.json
└── test.yaml
```

Here is the content of the `test.yaml` file.

```yaml
description: >
  Analyze with PURL and repository path without dependency resolution.

steps:
- name: Run macaron analyze
  kind: analyze
  options:
    command_args:
    - --package-url
    - pkg:maven/apache/maven
    - --repo-path
    - https://github.com/apache/maven
    - -b
    - master
    - -d
    - 3fc399318edef0d5ba593723a24fff64291d6f9b
    - --skip-deps
- name: Compare analysis report
  kind: compare
  options:
    kind: analysis_report
    result: output/reports/maven/apache/maven/maven.json
    expected: analysis_report.json
```

Each test config file has a description at the top telling what the test case is about, and a sequence of steps to be executed. The execution of a test case stops whenever a step fails (i.e. exits with non-zero code, by default). In the example above, there are 2 steps: (1) run the `macaron analyze` command, and (2) compare a JSON analysis report with the corresponding expected result file. Note that all steps are executed with the test case directory being the current working directory. Therefore, all filepaths in the test config file are relative to the test case directory.


## Example Usages

### Create a new test case

You create a new test case by creating a new directory, then a `test.yaml` within it. To schema-validate the `test.yaml` file, you can use the `check` command and point to the test case directory:

```bash
# Schema-validate the ./test/case/directory/test.yaml file.
$ python ./tests/integration/run.py check ./test/case/directory
```

At this point, some expected result files do not exist yet, since you normally want to run `macaron` once, inspect the result files, then turn them into expected result files if they look good enough. To do this, you can run in **interactive** mode. In this mode, the utility stops at each step and asks if you want to run or skip a step. For `compare` steps, the utility also asks if you want to "update" the expected result file instead of compare.

```bash
# Run a test case in interactive mode.
$ python ./tests/integration/run.py run -i ./test/case/directory
```

After you have finished running the test case, you can rerun the test case to make sure everything works as expected.

```bash
# Run a test case end-to-end.
$ python ./tests/integration/run.py run ./test/case/directory
```

### Inspect test cases

Besides the interactive mode, the `run` command also has another special mode called dry-run mode, enabled with the flag `-d/--dry`. In this mode, the utility only shows what commands will be run during the execution of the test cases without actually running any of them. This is especially useful for debugging purposes.

```bash
# Run a test case in dry-run mode.
$ python ./tests/integration/run.py run -d ./test/case/directory
```

### Validate test cases before pushing commits to remote or running in CI

Integration test cases take some reasonable amount of time to run. The `vet` command not only does schema validation on test config files, but also carries out additional validations for each test case to prevent as many unintentional errors as possible and save us time waiting just to see CI failing eventually.

The `vet` command is meant to be used in CI before running integration test. It is also a useful static check in general. Hence, it has been added as a hook to `pre-commit`.

### Bulk-process multiple test cases

All commands (`check`, `vet`, `run`, and `update`) can process multiple test cases, one after another. You can specify more than one directory as positional arguments of these commands.

```bash
# Run two test cases one after another.
$ python ./tests/integration/run.py run ./test_case_a/directory ./test_case_b/directory
```

You can also use the `...` path wildcard to allow for discovering test case directories recursively under a root directory.

```bash
# Run all test cases discovered recursively under a directory.
$ python ./tests/integration/run.py run ./all/cases/...
```

### Select a subset of test cases to run

In certain cases, we can utilize the feature of tags to select a subset of test cases to run with the `run` command.

Each test case can be attached with one or more tags in the yaml configuration. For example, you may find some of our test cases having the tags as follows.

```yaml
description: ...
tags:
- macaron-python-package
- macaron-docker-image
steps:
- ...
```

We typically have test cases that are shared for the container image and the Macaron Python package. We can mark the test cases shared for both purposes with `macaron-python-package` and `macaron-docker-image` tags.
When we do integration testing for the container image, we can add the argument `--include-tag macaron-docker-image` to filter test cases that are tagged with `macaron-docker-image`.

```bash
# Test the container image with test cases having the `macaron-docker-image` tag.
$ python ./tests/integration/run.py run --include-tag macaron-docker-image ./all/cases/...
```

We can do the same with `macaron-python-package` when we do integration tests for the Macaron Python package.

The `--include-tag` flag can be specified multiple times. A selected test case must be tagged with at least a tag specified with any of the `--include-tag` flags.

```bash
# Test the container image with test cases having EITHER `tag-a` for `tag-b` tag.
$ python ./tests/integration/run.py run --include-tag tag-a --include-tag tag-b ./all/cases/...
```

There is also the `--exclude-tag` flag. A selected test case must also not contain any tag specified with the `--exclude-tag` flag.

```bash
# Only run test cases not tagged with `npm-registry-testcase`.
$ python ./tests/integration/run.py run --exclude-tag npm-registry-testcase ./all/cases/...
```

You can simply think of each `--include-tag`/`--exclude-tag` argument as adding an additional constraint that a selected test case must satisfy.

Instructions on how to tag a test case for our CI/CD pipeline:
- If you want a test case to **only** run for the container image, use **only** `macaron-docker-image`.
- If you want a test case to **only** run with the Macaron Python package, use **only** `macaron-python-package`.
- To skip a test case, use `skip`. `skip` still has the same effect if it's used with other tags.
- If you want to run a test case for both the Macaron Python package and the docker container, use `macaron-python-package` and `macaron-docker-image` tags.
- If you want to run test cases that must contain all of a given set of tags (e.g. `['tag-a', 'tag-b']`), please create an additional tag for those test cases (e.g `tag-a-b`) and use it within `--include-tag`.
- Test cases marked with `npm-registry-testcase` are not run if the environment variable `NO_NPM` is set to `TRUE`. This only applies when you run the integration tests with:
```bash
$ make integration-test
```

### Debug utility script

In case you want to debug the utility script itself, there is the verbose mode for all commands which can be enabled with the `-v/--verbose` flag.


## Test Config Reference

### Test case Schema

* `description` (`string`, required): The description of the test case.
* `tags` (`array[string]`, optional, default is `[]`): The tags of the test case. When the `--include-tag <tag>` and/or `--exclude-tag <tag>` arguments are passed with the `run` command, only run test cases having all `--include-tag` tags and no `--exclude-tag` tags. You can think of it as each `--include-tag`/`--exclude-tag` adds another constraint that a test needs to satisfy for it to be included in a run. These arguments are typically used in combination with test case discovery using the `...` wildcard.
* `steps` (`array[Step]`, required; see the Step Schema below): The list of steps in a test case. Steps in a test case are executed sequentially. A test case stops execution and fails if any command fails.

### Step Schema

* `name` (`string`, required): The name of the step.
* `kind` (`"analyze" | "verify" | "compare" | "shell"`, required): The kind of the step. There are 4 kinds of steps:
  * `"analyze"`: runs the `macaron analyze` command.
  * `"verify"`: runs the `macaron verify-policy` command.
  * `"compare"`: compares an output file with an expected output file.
  * `"shell"`: runs an arbitrary shell command.
* `options`: Configuration options for the step. These options are specific to the step kind. See their schema below.
* `env` (`dict[string, string | null]`, optional): Key value pairs of environment variables being modified during the step after inheriting the environment in which the utility is executed within. Each value can be a string if you want to set a value to the environment variable, or null if you want to "unset" the variable.
* `expect_fail` (`bool`, optional, default is `false`): If `true`, assert that the step must exit with non-zero code. This should be used for cases where we expect a command to fail.

### Analyze step options Schema

* `main_args` (`array[string]`, optional): main arguments for `macaron`, i.e. those specified before the `analyze` command, e.g. `--verbose`.
* `command_args` (`array[string]`, optional): arguments for the `analyze` command.
* `ini` (`string`, optional): The `.ini` configuration file (a relative path from test case directory). This enables additional validations and is recommended over passing `--defaults-path` and the config file through `main_args`.
* `expectation` (`string`, optional): The provenance expectation file in CUE) (a relative path from test case directory). This enables additional validations and is recommended over passing `--provenance-expectation` and the expectation file through `command_args`.
* `provenance`: (`string`, optional): The provenance file (a relative path from test case directory). This enables additional validations and is recommended over passing `--provenance-file` and the provenance file through `command_args`.
* `sbom`: (`string`, optional): The SBOM file (a relative path from test case directory). This enables additional validations and is recommended over passing `--sbom-file` and the SBOM file through `command_args`.

### Verify step options Schema

* `main_args` (`array[string]`, optional): main arguments for `macaron`, i.e. those specified before the `verify-command` command, e.g. `--verbose`.
* `command_args` (`array[string]`, optional): arguments for the `verify-policy` command.
* `policy` (`string`, optional): The `policy.dl` file. This enables additional validations and is recommended over passing `--file` and the policy file through `command_args`.
* `database` (`string`, optional, default is `./output/macaron.db`): The database file. This is recommended over passing `--database` and the database file through `command_args`.
* `show_prelude` (`bool`, optional, default is `false`): Run the command in `--show-prelude` mode.

### Compare step options Schema

* `kind` (`"analysis_report" | "policy_report" | "deps_report" | "vsa"`, required): The kind of JSON report to compare.
* `result` (`string`, required): The output file (a relative path from test case directory).
* `expected` (`string`, required): The expected output file (a relative path from test case directory).

### Shell step options Schema

* `cmd` (`string`, required): The shell command to run.
