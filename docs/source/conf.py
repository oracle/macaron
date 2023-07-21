# Copyright (c) 2022 - 2023, Oracle and/or its affiliates. All rights reserved.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl/.

# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import datetime
import os
import sys

import pkg_resources

# Path to source.
sys.path.insert(0, os.path.abspath("../../src"))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

year = datetime.datetime.now().year

project = "Macaron"
copyright = f"{year}, Oracle and/or its affiliates. " + "All rights reserved"  # noqa: A001
version = pkg_resources.get_distribution("macaron").version
html_logo = "assets/macaron.svg"
author = "Macaron"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.napoleon",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosectionlabel",
    "sphinx_autodoc_typehints",
    "numpydoc",
]
autosectionlabel_prefix_document = True
autosectionlabel_maxdepth = 2
autodoc_member_order = "bysource"
numpydoc_show_class_members = False

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", ".venv"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "sphinx_rtd_theme"
html_theme_options = {
    # This option completely hides toctree set with ``:hidden:`` from the sidebar.
    # This is needed to hide the doc pages for checks from the sidebar. Otherwise,
    # at the moment there is no easy way to sort these doc pages in the sidebar
    # by their index.
    "includehidden": False,
}
html_static_path = ["_static"]


# We add the docstrings for class constructors in the `__init__` methods.
def skip(app, what, name, obj, would_skip, options):
    if name == "__init__":
        return False
    return would_skip


def setup(app):
    app.connect("autodoc-skip-member", skip)
