[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-yellow?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit) [![conventional-commits](https://img.shields.io/badge/conventional%20commits-1.0.0-yellow)](https://www.conventionalcommits.org/en/v1.0.0/) [![black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black) [![mypy](https://img.shields.io/badge/mypy-checked-brightgreen)](http://mypy-lang.org/) [![pylint](https://img.shields.io/badge/pylint-required%2010.0-brightgreen)](http://pylint.org/) [![pytest](https://img.shields.io/badge/pytest-enabled-brightgreen)](https://github.com/pytest-dev/pytest) [![hypothesis](https://img.shields.io/badge/hypothesis-tested-brightgreen.svg)](https://hypothesis.readthedocs.io/) [![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/oracle/macaron/badge)](https://github.com/ossf/scorecard)

# Macaron

![Macaron](./docs/source/assets/macaron.svg)

Macaron is a supply chain security analysis tool from [Oracle Labs](https://labs.oracle.com/pls/apex/r/labs/labs/intro), which focuses on the build integrity of an artifact and the artifact dependencies. It is based on the [Supply chain Levels for Software Artifacts (SLSA)](https://slsa.dev/) specification, which aims at preventing some of the software supply chain attacks as the systems get more complex, especially with respect to the use of open-source third-party code in applications. Attacks include stealing credentials, injecting malicious code etc., and it is critical to have security assurance on the third-party code to guarantee that the integrity of the code has not been compromised.

Macaron uses [SLSA requirements specifications v0.1](https://slsa.dev/spec/v0.1/requirements) to define concrete rules for protecting software integrity that can be checked for compliance requirements automatically. Macaron provides a customizable checker platform that makes it easy to define checks that depend on each other. This is particularly useful for implementing checks for SLSA levels. In addition, Macaron also checks a user-specified policy for the repository to detect unexpected behavior in the build process. Macaron is a work-in-progress project and currently supports Maven and Gradle Java build systems. Support has also been added for Python projects that use Pip or Poetry as their package managers, minus dependency analysis. We plan to support build systems for other languages in future.

## Table of Contents

* [Getting started](#getting-started)
* [How to Contribute](#how-to-contribute)
* [Defining new checks](#defining-new-checks)
* [Security issue reports](#security-issue-reports)
* [License](#license)

## Getting started

To learn how to download and run Macaron, see our documentation [here](https://oracle.github.io/macaron/).

## Contributing

This project welcomes contributions from the community. Before submitting a pull request, please [review our contribution guide](./CONTRIBUTING.md).

## Defining new checks

After cloning a repository, Macaron parses the CI configuration files and bash scripts that are triggered by the CI, creates call graphs and other intermediate representations as abstractions. Using such abstractions, Macaron implements concrete checks to gather facts and metadata based on a security specification.

To learn how to define your own checks, see the steps in the [checks documentation](/src/macaron/slsa_analyzer/checks/README.md).

## Generating SLSA provenances for Macaron itself

We have integrated [SLSA provenance generation](https://github.com/slsa-framework/slsa-github-generator) for our Docker image and release artifacts. However, due to a strict policy regarding the use of third-party GitHub Actions, we cannot generate the provenances in this repository yet until [this issue](https://github.com/slsa-framework/slsa-github-generator/issues/2204) is resolved.

## Security

Please consult the [security guide](./SECURITY.md) for our responsible security vulnerability disclosure process.

## License

Copyright (c) 2022, 2023 Oracle and/or its affiliates.
Macaron is licensed under the [Universal Permissive License (UPL), Version 1.0](./LICENSE.txt).
