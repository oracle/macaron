# Macaron documentation
This directory contains the Sphinx documentation for Macaron.

## Generating the HTML documentation from source
**Note**: We only include the API documentation at the moment. Other sections in the documentation will be migrated in the future.

First, make sure you have all the dependencies required to build the documentation (Assume we run the following commands in the root directory of this repo).

**TODO**: Add docs dependencies to `pyproject.toml`.

```
python -m pip install --editable .
```

To generate documentation in html form:

```
sphinx-build -b html docs/source docs/build -E
```

Or within the [docs](./) folder, run:
```
make html
```

To view the html documentation on localhost:

```
python3 -m http.server -d docs/build/html
```

## For developers: Generating the API docs.
The Sphinx API docs for Macaron can be generated using the [sphinx-apidoc](https://www.sphinx-doc.org/en/master/man/sphinx-apidoc.html) tool that comes with `sphinx`.

From within the root directory of Macaron, run:
```
sphinx-apidoc --no-toc --module-first --force --maxdepth 1 --output-dir docs/source/pages/apidoc/ src/
```

The output RST files will be generated into [pages/apidoc/](./source/pages/apidoc/) where it will be picked up when we build the documentation.
