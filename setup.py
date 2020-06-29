from setuptools import setup
import os

here = os.path.abspath(os.path.dirname(__file__))
name = "jupyter_sphinx"

version_ns = {}
with open(os.path.join(here, name, "_version.py")) as f:
    exec(f.read(), {}, version_ns)

with open(os.path.join(here, "README.md")) as f:
    description = f.read()

setup(
    name=name,
    version=version_ns["__version__"],
    author="Jupyter Development Team",
    author_email="jupyter@googlegroups.com",
    description="Jupyter Sphinx Extensions",
    long_description=description,
    long_description_content_type='text/markdown',
    url="https://github.com/jupyter/jupyter-sphinx/",
    project_urls={
        "Bug Tracker": "https://github.com/jupyter/jupyter-sphinx/issues/",
        "Documentation": "https://jupyter-sphinx.readthedocs.io",
        "Source Code": "https://github.com/jupyter/jupyter-sphinx/",
    },
    license="BSD",
    packages=["jupyter_sphinx"],
    install_requires=[
        "Sphinx>=2",
        "ipywidgets>=7.0.0",
        "IPython",
        "nbconvert>=5.5",
        "nbformat",
    ],
    python_requires=">= 3.5",
    package_data={"jupyter_sphinx": ["thebelab/*", "css/*"]},
)
