---
name: Bug Report
about: Report a bug or unexpected behavior in Macaron.
title: "[Bug] - [Describe Issue]"
labels: bug, triage
assignees: ''
---

### Description
Please provide a clear and concise description of the issue you're experiencing with Macaron. Be as detailed as possible about the problem.

### Steps to Reproduce
Please list the steps required to reproduce the issue:

1. **Step 1**: [Describe the first step]
2. **Step 2**: [Describe the second step]
3. **Step 3**: [Describe the third step]
4. [Continue adding steps if necessary]

### Expected Behavior
What were you expecting to happen?

### Actual Behavior
What actually happened? Please include any error messages, logs, or unexpected behavior you observed.

### Debug Information
Please run the command again with the `--verbose` [option](https://oracle.github.io/macaron/pages/cli_usage/index.html#cmdoption-v) to provide debug information. This will help us diagnose the issue more effectively. You can add this option to the command like this:

```shell
./run_macaron.sh --verbose [other options]
```

Attach the debug output here if possible.

### Environment Information
To assist with troubleshooting, please provide the following information about your environment:

Operating System: (e.g., Ubuntu 20.04, macOS 11.2)

CPU architecture information (e.g., x86-64 (AMD64))

Bash Version: (Run bash --version to get the version)

Docker or Podman Version: (Run docker --version to get the version)

If you are using Macaron as a Python package, please indicate that in your environment details and specify the Python version you are using.

Macaron version or commit hash where the issue occurs.

Additional Information: (Any other relevant details, such as hardware or network environment, such as proxies)

### Screenshots or Logs
If applicable, please provide screenshots or logs that illustrate the bug.

### Additional Information
Any other information that might be useful to identify or fix the bug. For example:

Any steps that worked around the issue

Specific configurations or files that may be relevant
