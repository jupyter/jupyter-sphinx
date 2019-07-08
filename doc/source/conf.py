# -*- coding: utf-8 -*-
#
# Configuration file for the Sphinx documentation builder.
#
# This file does only contain a selection of the most common options. For a
# full list see the documentation:
# http://www.sphinx-doc.org/en/master/config

import os
import sys

sys.path.insert(0, os.path.abspath('../..'))

import jupyter_sphinx

project = 'Jupyter Sphinx'
copyright = '2019, Jupyter Development Team'
author = 'Jupyter Development Team'

# The full version, including alpha/beta/rc tags
release = jupyter_sphinx.__version__
# The short X.Y version
version = release[:len(release) - len(release.lstrip('0123456789.'))].rstrip('.')

extensions = [
    'sphinx.ext.mathjax',
    'jupyter_sphinx.execute',
]

html_theme = 'alabaster'

jupyter_sphinx_thebelab_config = {
    "binderOptions": {
        "repo": "jupyter-widgets/jupyter-sphinx",
    },
}
