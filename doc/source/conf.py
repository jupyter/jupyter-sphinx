"""
Configuration file for the Sphinx documentation builder.

For a full list see the documentation: http://www.sphinx-doc.org/en/master/config
"""

# -- Path setup ----------------------------------------------------------------
import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

import jupyter_sphinx  # noqa: E402

# -- Project information -------------------------------------------------------
project = "Jupyter Sphinx"
copyright = "2019, Jupyter Development Team"
author = "Jupyter Development Team"
release = jupyter_sphinx.__version__

# -- General configuration -----------------------------------------------------
extensions = ["sphinx.ext.mathjax", "jupyter_sphinx"]

# -- Options for HTML output ---------------------------------------------------
html_theme = "sphinx_book_theme"

# -- Options for LaTeX output --------------------------------------------------
latex_engine = "xelatex"

# -- Jupyter Sphinx options ----------------------------------------------------
jupyter_sphinx_thebelab_config = {"binderOptions": {"repo": "jupyter/jupyter-sphinx"}}
