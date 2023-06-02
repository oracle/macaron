# Macaron documentation
This directory contains the source for the documentation of Macaron hosted [here](https://oracle-samples.github.io/macaron/).

## Build the documentation

To build the documentation, please follow these steps:
1. Setup the dev environment for Macaron using the instructions [here](../README.md#getting-started).
2. Build the documentation by running this command from the root directory of Macaron:
```
make docs
```

This command will build and generate the documentation into `docs/_build/html`. To view it locally, run (with the dev environment activated):

```
python3 -m http.server -d docs/_build/html
```

## Extend the API reference.

If you add a new module, make sure that it is added to the API reference. The API reference is generated using the [sphinx-apidoc](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html) tool.

From within the root directory of Macaron, run (with the dev environment activated):
```
sphinx-apidoc --no-toc --module-first --force --maxdepth 1 --output-dir docs/source/pages/apidoc/ src/
```

This command will  generate the API reference RST files into `docs/source/pages/apidoc/`. Make sure to check in the changed source files to the repository.
