# Macaron

![Macaron](./docs/source/assets/macaron.svg)

Macaron is a supply chain security analysis tool from [Oracle Labs](https://labs.oracle.com/pls/apex/r/labs/labs/intro), which focuses on the build integrity of an artifact and the artifact dependencies. It is based on the [Supply chain Levels for Software Artifacts (SLSA)](https://slsa.dev/) specification, which aims at preventing some of the software supply chain attacks as the systems get more complex, especially with respect to the use of open-source third-party code in applications. Attacks include stealing credentials, injecting malicious code etc., and it is critical to have security assurance on the third-party code to guarantee that the integrity of the code has not been compromised.

Macaron uses [SLSA requirements specifications v0.1](https://slsa.dev/spec/v0.1/requirements) to define concrete rules for protecting software integrity that can be checked for compliance requirements automatically. Macaron provides a customizable checker platform that makes it easy to define checks that depend on each other. This is particularly useful for implementing checks for SLSA levels. In addition, Macaron also checks a user-specified policy for the repository to detect unexpected behavior in the build process. Macaron is a work-in-progress project and currently supports Maven and Gradle Java build systems only. We plan to support build systems for other languages, such as Python in future.

## Table of Contents

* [Getting started](#getting-started)
* [Running Macaron](#running-macaron)
* [How to Contribute](#how-to-contribute)
* [Security issue reports](#security-issue-reports)
* [License](#license)


## Getting started

**Prerequisites**
- Python 3.10.5
- Go 1.18
- JDK 11

**Prepare the environment**

```bash
python -m venv .venv
. .venv/bin/activate
```

Clone the project and install Macaron.

```bash
python -m pip install --editable .
```

Build Macaron's Go modules:

```bash
go build -o ./bin/ ./golang/cmd/...
```

Download and build [slsa-verifer](https://github.com/slsa-framework/slsa-verifier):

```bash
MACARON_PATH=$(pwd)
git clone --depth 1 https://github.com/slsa-framework/slsa-verifier.git -b <version>
cd slsa-verifier/cli/slsa-verifier && go build -o $MACARON_PATH/bin/
cd $MACARON_PATH && rm -rf slsa-verifier
```

Download and install Maven wrapper:

```bash
cd resources \
  && wget https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper-distribution/3.1.1/maven-wrapper-distribution-3.1.1-bin.zip \
  && unzip maven-wrapper-distribution-3.1.1-bin.zip \
  && rm -r maven-wrapper-distribution-3.1.1-bin.zip \
  && echo -e "distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.8.6/apache-maven-3.8.6-bin.zip\nwrapperUrl=https://repo.maven.apache.org/maven2/org/apache/maven/wrapper/maven-wrapper/3.1.1/maven-wrapper-3.1.1.jar" > .mvn/wrapper/maven-wrapper.properties \
  && cd ..
```

## Running Macaron

```bash
usage: macaron [-h] [-v] [-o OUTPUT_DIR] -t PERSONAL_ACCESS_TOKEN {analyze,dump_defaults,verify} ...
```

The main parameters for Macaron are:
- `[-v]`: Run Macaron with more debug outputs.
- `[-o OUTPUT_DIR]`: The directory to store the results. The default value will be the Macaron repo path.
- `-t PERSONAL_ACCESS_TOKEN`: The GitHub access token. It's mandatory to have one for using any feature of Macaron. A valid token will provide increased ***request rate***, ***request limit*** and access to resources (e.g. GitHub Actions workflow data). Macaron is tested for valid GitHub access tokens only. The method to obtain a GitHub personal access token is described in the next section.

Apart from the main parameters listed above, you should choose the command to run, which requires other parameters. At the moment, Macaron has three commands.
- `analyze`: analyze the SLSA level of a single repository.
- `dump_defaults`: dump the default values in the output directory.
- `verify`: verify a provenance against a policy.


### Obtaining the GitHub personal access token
Create your own Github access token (please refer to the instructions [here](https://docs.github.com/en/github/authenticating-to-github/keeping-your-account-and-data-secure/creating-a-personal-access-token)). When creating this token, make sure to assign **at least** `repo` permissions.

The GitHub token should be stored in an environment variable and supplied to Macaron via command line parameters.

### Analyzing SLSA levels of a repository
*This section describes the `analyze` command of Macaron.*

Run this command to determine the SLSA level of a repository:

```bash
python -m macaron [-v] analyze -rp <path_to_target_repo> [-b <branch_name>] [-d <digest>] -c <config_path>
```

The main input parameters of the `analyze` command:
- `-rp <path_to_target_repo>` specifies the path to the repository to analyze. This path can be both a local path (e.g. `/path/to/repo`) or a remote path (e.g. `git@github.com:organization/repo_name.git` or `https://github.com/organization/repo_name.git`).
- `[-b <branch_name>]`: The name of the branch to analyze. If not specified, Macaron will checkout the default branch (if a remote path is supplied) or use the current branch that HEAD is on (if a local path is supplied).
- `[-d <digest>]`: The hash of the commit to checkout in the current branch. This hash must be in full form. If not specified, Macaron will checkout the latest commit of the current branch.
- `-c <config_path>`: The path to the configuration yaml file. This option cannot be used together with the `-rp` option.

Example I: Analyzing the GitHub repository [apache/maven](https://github.com/apache/maven) on **the latest commit of the default branch** without using a config file:

```bash
python -m macaron -t $GH_TOKEN -o output analyze -rp https://github.com/apache/maven.git
```

Example II: Doing the same thing as Example I, but using a config file:

```bash
python -m macaron -t $GH_TOKEN -o output analyze -c <path-to-maven_config.yaml>
```

```yaml
target:
  id: "apache/maven"
  branch: ""
  digest: ""
  path: "https://github.com/apache/maven.git"
```

The results of the examples above will be stored in ``output/reports/github_com/apache/maven/`` in HTML and JSON formats.

**Notes:**
- Macaron automatically detects and analyzes direct dependencies for Java Maven projects. This process might take a while during the first run but will be faster during the subsequent runs. To skip analyzing the dependencies you can pass ``--skip-deps`` option.
- If you supply a remote path, the repository is cloned to `git_repos/` before the analysis starts. If the repository has already been cloned to `git_repos/`, Macaron will not clone the repository and proceed to analyze the local repo instead.
- The `branch` and `digest` in the config file or `-b` and `-d` in the CLI are all optional and can be omitted.

### Verifying a policy

Macaron, currently, provides a PoC policy engine that checks a verified SLSA provenance against compliance requirements expressed as a policy. The result is reported in the JSON and HTML reports as a check called `mcn_policy_check_1`.

```bash
python -m macaron -t $GH_TOKEN -po <path-to-policy.yaml> analyze -rp https://github.com/apache/maven.git
```

The policy is a YAML file that contains expected values of predicates in SLSA provenance v0.2. Here is an example policy file:

```yaml
metadata:
  id: MACARON_1
  description: "Micronaut policy - SLSA provenance v0.2."

definition:
  _type: https://in-toto.io/Statement/v0.1
  predicateType: https://slsa.dev/provenance/v0.2

  predicate:
    builder:
      id: https://github.com/slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml@refs/tags/v1.2.1
    buildType: https://github.com/slsa-framework/slsa-github-generator/generic@v1

    invocation:
      configSource:
        uri: git+https://github.com/micronaut-projects/micronaut-security@refs/tags/v3.8.3
        entryPoint: .github/workflows/release.yml
```

You can also run the policy verifier directly like below:

```bash
python -m macaron -po <path_to_policy.yaml> verify -pr <path_to_prov_file>
```

**Note.** The policy engine is under active development and will support more complex policies soon. Stay tuned.


## How to Contribute

We welcome contributions! See our [contribution guidelines](./CONTRIBUTING.md).

## Security issue reports

Security issue reports should follow our [reporting guidelines](./SECURITY.md).

## License

Macaron is licensed under the [Universal Permissive License (UPL), Version 1.0](./LICENSE.txt).
