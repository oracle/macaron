## v0.18.0 (2025-10-10)

### Feat

- **heuristics**: add whitespace check to detect excessive spacing and invisible characters for malware check (#1086)
- add reproducible central buildspec generation (#1115)
- **heuristics**: improve differentiation between stub packages and dependency confusion attacks (#1174)
- **heuristics**: add two analyzers to detect dependency confusion and distinguish from stub packages (#1117)

### Fix

- gen-build-spec SQL query to look up build-as-code check build command joins on incorrect column (#1207)
- handle all tarfile extract errors (#1206)
- ensure Python 3.11.13 is used to address GHSA-4xh5-x5gv-qwph (#1197)
- **docs**: path of script download example (#1193)
- improve build tool detection (#1169)

### Refactor

- improve logging in console for macaron commands (#1160)

## v0.17.0 (2025-08-27)

### Feat

- **heuristics**: add SimilarProjectAnalyzer to detect structural similarity across packages from same maintainer (#1089)
- **heuristics**: add Fake Email analyzer to validate maintainer email domain (#1106)
- add GitHub attestation discovery (#1020)
- **security**: add package name typosquatting detection (#1059)
- add pypi attestation discovery (#1067)

### Fix

- catch defusedxml security errors (#1138)
- accept from-provenance repos as scm authentic (#1131)
- **pypi**: update get_maintainers_of_package to avoid request blocking (#1097)
- include inspector links with information on if they are reachable. (#1102)

### Refactor

- remove the automatic sbom generation feature for Java (#1145)
- run source code analysis by default (#1107)
- improve experimental source code pattern analysis of pypi packages (#965)

## v0.16.0 (2025-04-24)

### Feat

- detect vulnerable GitHub Actions (#1021)
- check PyPI registry when deps.dev fails to find a source repository (#982)
- add callgraph and build cmd detection for Jenkins (#977)

### Fix

- fix incorrect skip result evaluation causing false positives in PyPI malware reporting (#1031)
- use 'isDefault' version from deps dev api (#1019)

### Refactor

- log the SLSA summary in verbose mode only (#1063)
- log relative paths for file (#1032)
- use problog for suspicious combinations (#997)

## v0.15.0 (2025-03-10)

### Feat

- add Repo Finder and Commit Finder outcomes to database (#892)
- add in new metadata-based heuristic to pypi malware analyzer (#944)
- find repo from latest artifact when provided artifact has none (#931)
- obtain Java and Python artifacts from .m2 or Python virtual environment from input (#864)
- include inspector package urls as part of the malicious metadata facts for pypi packages (#935)
- add a new setup.py related heuristic in the pypi malware analyzer (#932)

### Fix

- update already present repositories (#949)
- report known malware even when not labeled (#956)

### Refactor

- replace unreachable project links heuristic with source code repo heuristic (#983)
- remove the deprecated --skip-deps command-line option. (#943)

## v0.14.0 (2024-11-26)

### Feat

- report known malware for all ecosystems (#922)
- add command to run repo and commit finder without analysis (#827)
- add a new check to report the build tool (#914)
- verify whether the reported repository can be linked back to the artifact (#873)
- allow specifying the dependency depth resolution through CLI and make dependency resolution off by default (#840)

### Fix

- block terminal prompts in find source (#918)
- fix a bug in GitHub Actions matrix variable resolution (#896)
- prevent endless loop on 403 GitHub response (#866)

### Refactor

- accept provenance data in artifact pipeline check (#872)
- remove --config-path from CLI (#844)

## v0.13.0 (2024-09-16)

### Feat

- add a script to check VSA (#858)

### Fix

- use gnu-sed on mac instead of the built-in sed command (#853)

## v0.12.0 (2024-08-16)

### Feat

- verify npm SLSA provenance against signed npm provenance (#747)
- add a check to analyze malicious Python packages (#750)
- add support for SLSA v1 provenance with OCI build type (#778)

### Fix

- accept provenances that are not inferred in the provenance checks (#802)
- use artifact filenames as keys for verifying jfrog assets in provenance_witness_l1_check (#796)

## v0.11.0 (2024-06-18)

### Feat

- add dependency resolution for Python (#748)
- add checks to determine if repo and commit came from provenance (#704)
- add support for GitHub provenances passed as input (#732)

### Fix

- modify verify-policy to exits succesfully if a passed policy exists and allow components having no repository to pass policies (#766)
- force docker to use linux/amd64 platform (#768)
- do not fetch from origin/HEAD for local repo targets (#734)

## v0.10.0 (2024-04-29)

### Feat

- allow provenance files to be files containing a URL pointing to the actual provenance file which will be transparently downloaded (#710)
- allow defining a git service from defaults.ini   (#694)
- improve VSA generation with digest for each subject (#685)

### Fix

- improve run_macaron.sh bash and docker version compatibility (#717)
- store language in build as code check for non-GitHub CI services (#716)
- extract digest from provenance when repo path is provided but digest is not provided from the user (#711)
- fix a compatibility issue in run_macaron.sh for macOS (#701)
- make build script check fail when no repo is found (#699)

## v0.9.0 (2024-04-05)

### Feat

- extend static analysis and compute confidence scores for deploy commands (#673)
- use provenance to find commits for supported PURL types. (#653)

### Fix

- preserve the order of elements of lists extracted from defaults.ini (#660)

## v0.8.0 (2024-03-05)

### Feat

- discover slsa v1 provenances for npm packages (#639)
- add exclude and include check in ini config (#254)
- introduce confidence scores for check facts (#620)
- follow indirect repository URLs (#629)
- use repository url provided as input for finding a commit (#622)

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
