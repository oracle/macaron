# Macaron documentation
This directory contains the source for the documentation of Macaron hosted [here](https://oracle.github.io/macaron/).

## Build the documentation

To build the documentation, please follow these steps:
1. Setup the dev environment for Macaron using the instructions [here](../CONTRIBUTING.md).
2. Build the documentation by running this command from the root directory of Macaron:
```
make docs
```

This command will build and generate the documentation into `docs/_build/html`. To view it locally, run (with the dev environment activated):

```
python -m http.server -d docs/_build/html
```

## Extend the API reference

We use the [sphinx-apidoc](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html) tool to generate API reference automatically from Python docstrings. See the [Docstring section in the Macaron Style Guide](https://oracle.github.io/pages/developers_guide/style_guide.html#docstrings) for how to write docstrings in Macaron.

If you make a code change, make sure to regenerate the API reference by running (with the dev environment activated):

```
make docs-api
```

This command uses [sphinx-apidoc](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html) to generate the API reference RST files into `docs/source/pages/developers_guide/apidoc/`. Make sure to check in these API reference RST files to the repository.

You can then rebuild the whole HTML documentation with:

```
make docs
```

In addition, instead of running `make docs-api` and `make docs` separately, you can combine the two commands by running:

```
make docs-full
```
