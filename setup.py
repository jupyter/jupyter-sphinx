from setuptools import setup
import os

here = os.path.abspath(os.path.dirname(__file__))
name = 'jupyter_sphinx'

version_ns = {}
with open(os.path.join(here, name, '_version.py')) as f:
    exec(f.read(), {}, version_ns)

setup(
    name = name,
    version = version_ns['__version__'],
    author = 'Jupyter Development Team',
    author_email = 'jupyter@googlegroups.com',
    description = 'Jupyter Sphinx Extensions',
    license = 'BSD',
    packages = ['jupyter_sphinx'],
    install_requires = [
        'Sphinx>=0.6',
        'ipywidgets>=7.0.0',
        'IPython',
        'nbconvert>=5.5',
        'nbformat',
    ],
    python_requires = '>= 3.5',
)
