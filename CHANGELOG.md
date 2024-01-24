## v0.7.0 (2024-01-18)

### Feat

- support tox to publish artifacts to PyPI (#599)
- generate Verification Summary Attestation (#592)
- map artifacts to commits via repo tags (#508)
- find SLSA provenance v0.2 published on npm registry (#551)

## v0.6.0 (2023-11-03)

### Feat

- add download timeout config (#483)
- support gzipped provenance files (#504)
- support running the analysis with SBOM and the main software component with no repository (#165)
- add support for Go, npm and Yarn build tools (#451)
- enable repo finder to support more languages via Open Source Insights (#388)

### Fix

- resolve podman compatibility issues (#512)
- do not use git set-branches if the target branch is not currently available in the repository (#491)
- fix bash syntax error when running `run_macaron.sh` on macOS (#528)

### Refactor

- refactor interface of base check (#513)
- allow the branch name in the schema of a repository to be null (#532)

### Perf

- use partial clone to reduce clone time (#389)

## v0.5.0 (2023-09-14)

### Feat

- add a new check to map artifacts to pipelines (#471)
- add docker build detection (#409)

### Fix

- **policy-engine**: use component_id instead of repo_id in policy to find the check result (#473)
- check if repository is available in provenance available check (#467)
- encode PURL qualifiers as a normalized string (#466)
- fix `run_macaron.sh` script to handle action arguments correctly (#461)

## v0.4.0 (2023-09-01)

### Feat

- support trusted SLSA L3 builders for Maven, Gradle, Node.js, and containers (#445)
- add purl as a CLI option (#401)

### Fix

- add timeout to Gradle Group ID detection (#446)
- rename `domain` to `hostname` in Git service configuration (#453)
- always pull latest docker image in run_macaron.sh (#448)
- by default, always pull latest version of docker image, but allow this behaviour to be overidden by setting the DOCKER_PULL env var

Signed-off-by: Nicholas Allen <nicholas.allen@oracle.com>
- **proxy**: use the host proxy settings for Maven and Gradle (#434)
- update justifications to be complete for multi build tool projects (#432)

## v0.3.0 (2023-08-22)

### Feat

- add support for JFrog Artifactory and witness provenances produced on GitLab CI (#349)
- introduce a new data model and software components based on PURL (#305)

### Fix

- **orm**: use the host’s timezone when persisting datetime objects without a timezone, instead of forcing them to UTC (#397)
- handle cloning issues when repo is in an unexpected state (#395)
- **orm**: serialize datetime object’s timezone instead of always coercing to UTC when persisting to the SQLite db (#381)

## v0.2.0 (2023-07-17)

### Feat

- resolve Maven properties in found POMs (#271)
- add support for cloning GitLab repositories (#316)
- multi build tool detection (#179)

### Fix

- check paths in an archive file before extracting (#366)
- fix CycloneDx Gradle automatic dependency resolver bug (#315)

## v0.1.1 (2023-06-14)

### Fix

- fix links as part of transition to oracle/macaron (#307)
- fixes the result summary for UNKNOWN check results (#299)

### Refactor

- separate provenance expectation from Datalog policies (#297)

## v0.1.0 (2023-06-05)

### Feat

- **release**: generate SLSA provenance for the Docker image (#265)
- add command-line flag for version (#262)
- add additional repo finding via parent POMs (#217)
- add repo finding via scm metadata in artefact poms (#155)
- run cue validator per analysis target  (#90)
- add python as a supported build tool (#67)
- support an existing SBOM as input (#105)
- add check output to database and implement souffle policy engine (#46)
- add dependency analyzer for Gradle (#57)

### Fix

- **release**: disable SLSA provenance for now (#277)
- do not skip rootProject in Gradle dependency resolution (#252)
- create the bin directory for syft (#245)
- add 'packages: read' permission to release workflow (#241)
- do not overwrite an existing check relationship when a check has no parent in the Registry (#238)
- upgrade requests to 2.31.0 to fix CVE-2023-32681 (#236)
- restore the runner if an uncaught exception happens in a check (#216)
- return error when defaults.ini provided by user does not exist (#208)
- fix undefined local variable in build_as_code check (#136)
- resolve the full name for a repo whose remote origin is a local path (#153)
- do not pull the latest when analyzing a target with local repo path (#125)
- do not use download script for Syft (#164)
- remove the topLevel packages permission (#160)
- initialize all DependencyInfo attributes (#139)
- check if build dir contains a valid build (#135)
- read configuration for recursion through bom file (#130)
- allow BOM component version and group be empty (#104)
- do not log check_module object to avoid info leakage (#96)

### Refactor

- run policy engine using macaron entrypoint (#192)
