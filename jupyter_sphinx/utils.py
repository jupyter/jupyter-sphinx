"""Utility functions and helpers."""
import os
from itertools import groupby, count
from sphinx.errors import ExtensionError
import nbformat
from jupyter_client.kernelspec import get_kernel_spec, NoSuchKernel


def blank_nb(kernel_name):
    try:
        spec = get_kernel_spec(kernel_name)
    except NoSuchKernel as e:
        raise ExtensionError("Unable to find kernel", orig_exc=e)
    return nbformat.v4.new_notebook(
        metadata={
            "kernelspec": {
                "display_name": spec.display_name,
                "language": spec.language,
                "name": kernel_name,
            }
        }
    )


def split_on(pred, it):
    """Split an iterator wherever a predicate is True."""

    counter = 0

    def count(x):
        nonlocal counter
        if pred(x):
            counter += 1
        return counter

    # Return iterable of lists to ensure that we don't lose our
    # place in the iterator
    return (list(x) for _, x in groupby(it, count))


def strip_latex_delimiters(source):
    """Remove LaTeX math delimiters that would be rendered by the math block.

    These are: ``\(…\)``, ``\[…\]``, ``$…$``, and ``$$…$$``.
    This is necessary because sphinx does not have a dedicated role for
    generic LaTeX, while Jupyter only defines generic LaTeX output, see
    https://github.com/jupyter/jupyter-sphinx/issues/90 for discussion.
    """
    source = source.strip()
    delimiter_pairs = (pair.split() for pair in r"\( \),\[ \],$$ $$,$ $".split(","))
    for start, end in delimiter_pairs:
        if source.startswith(start) and source.endswith(end):
            return source[len(start) : -len(end)]

    return source


def default_notebook_names(basename):
    """Return an interator yielding notebook names based off 'basename'"""
    yield basename
    for i in count(1):
        yield "_".join((basename, str(i)))


def language_info(executor):
    # Can only run this function inside 'setup_preprocessor'
    assert hasattr(executor, "kc")
    info_msg = executor._wait_for_reply(executor.kc.kernel_info())
    return info_msg["content"]["language_info"]


def sphinx_abs_dir(env, *paths):
    # We write the output files into
    # output_directory / jupyter_execute / path relative to source directory
    # Sphinx expects download links relative to source file or relative to
    # source dir and prepended with '/'. We use the latter option.
    return "/" + os.path.relpath(
        os.path.abspath(
            os.path.join(output_directory(env), os.path.dirname(env.docname), *paths)
        ),
        os.path.abspath(env.app.srcdir),
    )


def output_directory(env):
    # Put output images inside the sphinx build directory to avoid
    # polluting the current working directory. We don't use a
    # temporary directory, as sphinx may cache the doctree with
    # references to the images that we write

    # Note: we are using an implicit fact that sphinx output directories are
    # direct subfolders of the build directory.
    return os.path.abspath(
        os.path.join(env.app.outdir, os.path.pardir, "jupyter_execute")
    )
