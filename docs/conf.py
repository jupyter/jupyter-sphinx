"""
Configuration file for the Sphinx documentation builder.

For a full list see the documentation: http://www.sphinx-doc.org/en/master/config
"""

# -- Path setup ----------------------------------------------------------------
import os
import sys

sys.path.insert(0, os.path.abspath("../.."))

import jupyter_sphinx

# -- Project information -------------------------------------------------------
project = "Jupyter Sphinx"
copyright = "2019, Jupyter Development Team"
author = "Jupyter Development Team"
release = jupyter_sphinx.__version__

# -- General configuration -----------------------------------------------------
extensions = ["sphinx.ext.mathjax", "jupyter_sphinx", "sphinx_design"]

# -- Options for HTML output ---------------------------------------------------
html_theme = "pydata_sphinx_theme"
html_title = "jupyter-sphinx"
html_static_path = ["_static"]
html_favicon = "_static/jupyter.svg"
html_logo = "_static/jupyter.svg"
html_css_files = ["custom.css"]
html_theme_options = {
    "logo": {"text": "jupyter-sphinx"},
    "repository_url": "https://github.com/jupyter/jupyter-sphinx",
    "use_repository_button": True,
    "repository_branch": "main",
    "use_issues_button": True,
    "use_fullscreen_button": False,
    "search_as_you_type": True,
}
html_sidebars = {"**": []}

# -- Options for LaTeX output --------------------------------------------------
latex_engine = "xelatex"

# -- Jupyter Sphinx options ----------------------------------------------------
jupyter_sphinx_thebelab_config = {"binderOptions": {"repo": "jupyter/jupyter-sphinx"}}
