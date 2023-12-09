# General Jupyter contributor guidelines

If you're reading this section, you're probably interested in
contributing to Jupyter. Welcome and thanks for your interest in
contributing!

Please take a look at the Contributor documentation, familiarize
yourself with using the Jupyter Server, and introduce yourself on the
mailing list and share what area of the project you are interested in
working on.

For general documentation about contributing to Jupyter projects, see
the [Project Jupyter Contributor
Documentation](https://jupyter.readthedocs.io/en/latest/contributing/content-contributor.html).

# Setting Up a Development Environment

## Installing the Jupyter Server

The development version of the server requires
[node](https://nodejs.org/en/download/) and
[pip](https://pip.pypa.io/en/stable/installing/).

Once you have installed the dependencies mentioned above, use the
following steps:

```
pip install --upgrade pip
git clone https://github.com/jupyter/jupyter-sphinx
cd jupyter-server
pip install -e ".[test]"
```

## Code Styling and Quality Checks

`jupyter-sphinx` has adopted automatic code formatting so you shouldn't
need to worry too much about your code style. As long as your code is
valid, the pre-commit hook should take care of how it should look.
`pre-commit` and its associated hooks will automatically be installed
when you run `pip install -e ".[test]"`

To install `pre-commit` hook manually, run the following:

```
pre-commit install
```

You can invoke the pre-commit hook by hand at any time with:

```
pre-commit run
```

which should run any autoformatting on your code and tell you about any
errors it couldn't fix automatically. You may also install [black
integration](https://github.com/psf/black#editor-integration) into your
text editor to format code automatically.

If you have already committed files before setting up the pre-commit
hook with `pre-commit install`, you can fix everything up using
`pre-commit run --all-files`. You need to make the fixing commit
yourself after that.

Some of the hooks only run on CI by default, but you can invoke them by
running with the `--hook-stage manual` argument.

There are three hatch scripts that can be run locally as well:
`hatch run lint:build` will enforce styling.

# Running Tests

Install dependencies:

```
pip install -e .[test]
```

To run the Python tests, use:

```
pytest
```

You can also run the tests using `hatch` without installing test
dependencies in your local environment:

```
pip install hatch
hatch run test:test
```

The command takes any argument that you can give to `pytest`, e.g.:

```
hatch run test:test -k name_of_method_to_test
```

You can also drop into a shell in the test environment by running:

```
hatch -e test shell
```

# Building the Docs

Install the docs requirements using `pip`:

```
pip install .[doc]
```

Once you have installed the required packages, you can build the docs
with:

```
cd docs
make html
```

You can also run the tests using `hatch` without installing test
dependencies in your local environment.

```bash
pip install hatch
hatch run docs:build
```

You can also drop into a shell in the docs environment by running:

```
hatch -e docs shell
```

After that, the generated HTML files will be available at
`build/html/index.html`. You may view the docs in your browser.

You should also have a look at the [Project Jupyter Documentation
Guide](https://jupyter.readthedocs.io/en/latest/contributing/content-contributor.html).
