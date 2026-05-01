# Macaron BuildSpec Schema Notes

This file documents the semantics of `macaron_buildspec_schema.json`. It is kept next to the JSON Schema because JSON does not support comments.

The BuildSpec is Macaron's common build description. It records the package identity, source repository, detected build environment, and one or more candidate build commands. The implementation that defines the shared field contract lives primarily in `src/macaron/build_spec_generator/common_spec/base_spec.py`; the ecosystem-specific implementations under the same package populate and refine those fields.

The integration cases in `tests/integration/cases/pypi_toga/test.yaml` and `tests/integration/cases/org_apache_hugegraph/computer-k8s/test.yaml` compare generated BuildSpecs against `expected_default.buildspec` and validate those outputs with `macaron_buildspec_schema.json`. Those fixtures are useful examples of the schema in practice.

## Top-Level Fields

| Field | Required by schema | Meaning |
| --- | --- | --- |
| `ecosystem` | Yes | Package ecosystem, such as `maven` or `pypi`. This is derived from the PURL type and selects the ecosystem-specific BuildSpec resolver. |
| `purl` | Yes | Package URL for the target component. |
| `language` | Yes | Main implementation language inferred for the ecosystem, for example `java` for Maven or `python` for PyPI. |
| `build_tools` | Yes | Build tools or package managers detected for the repository. For generated specs, Macaron currently recognizes tools such as `maven`, `gradle`, `pip`, `poetry`, `uv`, `flit`, `hatch`, and `conda`, though not every tool has an ecosystem-specific default command. |
| `macaron_version` | Yes | Version of Macaron that generated the spec. |
| `group_id` | No | Ecosystem-specific group or namespace. For Maven this is the Maven group ID. For PyPI this is usually `null`. |
| `artifact_id` | Yes | Package or artifact name. |
| `version` | Yes | Package or artifact version. |
| `git_repo` | No | Remote repository URL or path that Macaron associated with the package. |
| `git_tag` | No | Source revision used for rebuilds. Despite the field name, this may be a commit SHA rather than a tag. |
| `newline` | No | Expected line ending style, such as `lf` or `crlf`. |
| `language_version` | Yes | Runtime or language version constraints. Examples include a normalized JDK major version for Maven builds or Python version constraints for PyPI builds. Multiple values may appear when Macaron infers constraints from more than one source, such as package metadata and build dependencies. |
| `dependencies` | No | Runtime or release dependencies, when known. |
| `build_dependencies` | No | Build-time dependencies, including dependencies needed for tests, when known. |
| `build_commands` | No | Candidate commands and their metadata. See the detailed section below. |
| `test_commands` | No | Test commands, represented as tokenized command arrays. |
| `environment` | No | Environment variables needed by the build or test steps. Values are strings. |
| `artifact_path` | No | Expected output artifact path or location, if known. |
| `entry_point` | No | Script, class, binary, or other entry point for running the project, if known. |
| `build_requires` | No | Build environment requirements as a mapping from package name to version specifier. This is currently most useful for PyPI, where values are inferred from wheel metadata, `pyproject.toml`, source distributions, and fallback heuristics. A value may be an empty string when a package is required but no concrete version constraint is known. |
| `build_backends` | No | Build backends used by a frontend build tool. For PyPI, this can include values such as `setuptools.build_meta`; these correspond to the backend that tools such as `pip` or `python -m build` call to create a wheel. |
| `has_binaries` | No | Whether the package artifact includes non-pure binaries. |
| `upstream_artifacts` | No | Upstream artifacts analyzed while generating the spec, grouped by artifact kind. For example, PyPI may record wheel and sdist URLs; downstream rebuild formats can use the wheel URL to compare the rebuilt artifact with the published artifact. |

## `build_commands`

`build_commands` is an array of build command entries. Each entry combines a command with the build tool detection that justifies using it.

The entries are not only shell snippets. They also carry supporting context about the configuration file, detected tool version, and confidence score. This lets downstream generators decide whether a command is appropriate for another format, such as a Dockerfile or Reproducible Central buildspec.

### Entry Fields

| Field | Required by schema | Meaning |
| --- | --- | --- |
| `build_tool` | Yes | The build tool the entry applies to, for example `maven`, `gradle`, `pip`, `poetry`, `uv`, `flit`, or `hatch`. It should match one of the values in the top-level `build_tools` list. |
| `build_tool_version` | No | Detected build tool version, when Macaron can infer one. The schema allows this to be `null`, but generated specs omit the field when the version is unknown. |
| `build_config_path` | Yes | Path to the build configuration file associated with this command, relative to the repository root. Examples: `pom.xml`, `submodule/pom.xml`, `build.gradle`, `pyproject.toml`. |
| `root_build_config_path` | No | Optional path to a root or entry build configuration for multi-module builds, relative to the repository root. Maven and Gradle detection can use this when the artifact-specific config is in a module but the build should be launched from a higher-level config. |
| `command` | Yes | The build command as a tokenized argument list, not as one shell string. For example, use `["mvn", "clean", "package"]`, not `["mvn clean package"]`. An empty list is meaningful during generation and means Macaron detected the tool/configuration but did not find a concrete command before ecosystem defaults were applied. |
| `confidence_score` | Yes | Confidence in the build tool/configuration detection. Detection code treats this as a value in the range `[0, 1]`, with `1.0` being highest confidence. When multiple configs are found for the same tool, the generator keeps the highest-confidence detection for that tool. |

### Command Semantics

The `command` field is a list of command-line tokens. The first token is normally the executable or wrapper, and later tokens are its arguments. This representation avoids ambiguity around quoting and lets Macaron patch or adapt commands before emitting a downstream format.

Examples:

```json
["mvn", "clean", "package"]
```

```json
["./gradlew", "clean", "assemble", "publishToMavenLocal"]
```

```json
["python", "-m", "build", "--wheel", "-n"]
```

Do not store a whole command line as a single string unless the intended executable name itself contains spaces. Downstream code expects tokenized commands and may join tokens with spaces when producing a shell-oriented format.

### Empty Commands and Defaults

During generation, Macaron first tries to recover concrete build commands from analysis results in the database. If it cannot find a command, it still creates `build_commands` entries for the detected build tools with `command: []`. Ecosystem-specific resolvers then fill in defaults when they know a safe default for the tool.

Current defaults include:

| Ecosystem | Tool | Default command |
| --- | --- | --- |
| Maven | `maven` | `["mvn", "clean", "package"]` |
| Maven | `gradle` | `["./gradlew", "clean", "assemble", "publishToMavenLocal"]` |
| PyPI | `pip` | `["python", "-m", "build", "--wheel", "-n"]` |
| PyPI | `poetry` | `["poetry", "build"]` |
| PyPI | `uv` | `["uv", "build"]` |
| PyPI | `flit` | `["flit", "build"]` |
| PyPI | `hatch` | `["hatch", "build"]` |

For PyPI packages with non-pure binary artifacts, the PyPI resolver currently sets `build_commands` to an empty array instead of emitting a rebuild command.

In the `pypi_toga` integration fixture, Macaron detects `pip` through `pyproject.toml` with confidence `1.0` and emits this default command:

```json
["python", "-m", "build", "--wheel", "-n"]
```

The command means "build only a wheel and do not install build dependencies in an isolated environment." The companion `build_requires` field records the build dependencies Macaron inferred separately, and the Dockerfile generator installs those dependencies before running the command.

### Maven and Gradle Command Patching

For Maven ecosystem specs, Macaron patches detected Maven and Gradle commands after defaults have been applied. This normalization is intended to make rebuild commands more reproducible and less dependent on CI-only settings.

Examples of Maven normalization include preferring `clean package`, removing some CI-oriented flags, skipping tests and documentation-related work, and dropping secret-bearing properties such as a GPG passphrase. Examples of Gradle normalization include preferring `clean assemble`, using a plain console, excluding tests, and setting signing-related skip properties.

If a command cannot be parsed as a supported Maven or Gradle command, Macaron leaves it as the original token list.

### Multiple Build Commands

`build_commands` may contain more than one entry. This can happen when analysis finds multiple concrete build commands or when multiple build tools are detected. Downstream formats may combine commands. For example, the Reproducible Central adapter converts tokenized commands into shell strings and joins multiple non-empty commands with `&&`.

Ordering should therefore be treated as significant: earlier commands are the commands Macaron selected first from its analysis results.

## Example

This abbreviated example follows the same shape as the validated `pypi_toga` integration BuildSpec:

```json
{
  "ecosystem": "pypi",
  "purl": "pkg:pypi/toga@0.5.1",
  "language": "python",
  "build_tools": ["pip"],
  "macaron_version": "0.22.0",
  "group_id": null,
  "artifact_id": "toga",
  "version": "0.5.1",
  "git_repo": "https://github.com/beeware/toga",
  "git_tag": "ef1912b0a1b5c07793f9aa372409f5b9d36f2604",
  "newline": "lf",
  "language_version": [">=3.8", ">=3.9"],
  "build_commands": [
    {
      "build_tool": "pip",
      "build_config_path": "pyproject.toml",
      "command": ["python", "-m", "build", "--wheel", "-n"],
      "confidence_score": 1.0
    }
  ],
  "has_binaries": false,
  "build_requires": {
    "setuptools": "==80.3.1",
    "setuptools_scm": "==8.3.1",
    "setuptools_dynamic_dependencies": "==1.0.0"
  },
  "build_backends": ["setuptools.build_meta"],
  "upstream_artifacts": {
    "wheels": ["https://files.pythonhosted.org/.../toga-0.5.1-py3-none-any.whl"],
    "sdist": ["https://files.pythonhosted.org/.../toga-0.5.1.tar.gz"]
  }
}
```

This Maven example follows the validated `org_apache_hugegraph/computer-k8s` integration BuildSpec and illustrates an artifact-specific module config with a root build config:

```json
{
  "ecosystem": "maven",
  "purl": "pkg:maven/org.apache.hugegraph/computer-k8s@1.0.0",
  "language": "java",
  "build_tools": ["maven"],
  "macaron_version": "0.22.0",
  "group_id": "org.apache.hugegraph",
  "artifact_id": "computer-k8s",
  "version": "1.0.0",
  "git_repo": "https://github.com/apache/hugegraph-computer",
  "git_tag": "d2b95262091d6572cc12dcda57d89f9cd44ac88b",
  "newline": "lf",
  "language_version": ["11"],
  "build_commands": [
    {
      "build_tool": "maven",
      "build_config_path": "computer-k8s/pom.xml",
      "root_build_config_path": "pom.xml",
      "command": [
        "mvn",
        "-DskipTests=true",
        "-Dmaven.site.skip=true",
        "-Drat.skip=true",
        "-Dmaven.javadoc.skip=true",
        "clean",
        "package"
      ],
      "confidence_score": 1.0
    }
  ]
}
```
