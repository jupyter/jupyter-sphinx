from setuptools import setup

setup(
    name = 'jupyter_sphinx',
    version = '0.0.1',
    author = 'Jupyter Development Team',
    author_email = 'jupyter@googlegroups.com',
    description = 'Jupyter Sphinx Extensions',
    license = 'BSD',
    packages = ['jupyter_sphinx'],
    install_requires = ['Sphinx>=0.6', 'ipywidgets>=6.0.0b5'],
)
