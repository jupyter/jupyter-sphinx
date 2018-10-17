"""Simple sphinx extension that executes code in jupyter and inserts output."""

import os
from itertools import groupby, count
from operator import itemgetter

from sphinx.util import logging
from sphinx.transforms import SphinxTransform
from sphinx.errors import ExtensionError
from sphinx.addnodes import download_reference
from sphinx.ext.mathbase import displaymath

import docutils
from IPython.lib.lexers import IPythonTracebackLexer, IPython3Lexer
from docutils.parsers.rst.directives import flag, unchanged
from docutils.parsers.rst import Directive

import nbconvert
from nbconvert.preprocessors.execute import executenb
from nbconvert.preprocessors import ExtractOutputPreprocessor
from nbconvert.writers import FilesWriter

from jupyter_client.kernelspec import get_kernel_spec, NoSuchKernel

import nbformat


from ._version import __version__

logger = logging.getLogger(__name__)


def blank_nb(kernel_name):
    try:
        spec = get_kernel_spec(kernel_name)
    except NoSuchKernel as e:
        raise ExtensionError('Unable to find kernel', orig_exc=e)
    return nbformat.v4.new_notebook(metadata={
        'kernelspec': {
            'display_name': spec.display_name,
            'language': spec.language,
            'name': kernel_name,
        }
    })


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


class Cell(docutils.nodes.container):
    """Container for input/output from Jupyter kernel"""
    pass


def visit_container(self, node):
    self.visit_container(node)


def depart_container(self, node):
    self.depart_container(node)


class JupyterCell(Directive):

    required_arguments = 0
    final_argument_whitespace = True
    has_content = True

    option_spec = {
        'hide-code': flag,
        'hide-output': flag,
        'code-below': flag,
        'new-notebook': unchanged,
        'kernel': unchanged,
    }

    def run(self):
        self.assert_has_content()
        if 'kernel' in self.options and 'new-notebook' not in self.options:
            raise ExtensionError(
                "In code execution cells, the 'kernel' option may only be "
                "specified with the 'new-notebook' option."
            )
        # Cell only contains the input for now; we will execute the cell
        # and insert the output when the whole document has been parsed.
        return [Cell('',
            docutils.nodes.literal_block(
                text='\n'.join(self.content),
                language='ipython'
            ),
            hide_code=('hide-code' in self.options),
            hide_output=('hide-output' in self.options),
            code_below=('code-below' in self.options),
            kernel_name=self.options.get('kernel', '').strip(),
            new_notebook=('new-notebook' in self.options),
            notebook_name=self.options.get('new-notebook', '').strip(),
        )]


def jupyter_download_role(name, rawtext, text, lineno, inliner):
    _, filetype = name.split(':')
    assert filetype in ('notebook', 'script')
    ext = '.ipynb' if filetype == 'notebook' else '.py'
    output_dir = sphinx_abs_dir(inliner.document.settings.env)
    download_file = text + ext
    node = download_reference(
        download_file, download_file,
        reftarget=os.path.join(output_dir, download_file)
    )
    return [node], []


def cell_output_to_nodes(cell, data_priority, dir):
    """Convert a jupyter cell with outputs and filenames to doctree nodes.

    Parameters
    ==========
    cell : jupyter cell
    data_priority : list of mime types
        Which media types to prioritize.
    dir : string
        Sphinx "absolute path" to the output folder, so it is a relative path
        to the source folder prefixed with ``/``.
    """
    to_add = []
    for index, output in enumerate(cell.get('outputs', [])):
        output_type = output['output_type']
        if (
            output_type == 'stream'
            and output['name'] == 'stdout'
        ):
            to_add.append(docutils.nodes.literal_block(
                text=output['text'],
                rawsource=output['text'],
                language='ipython',
            ))
        elif (
            output_type == 'error'
        ):
            traceback = '\n'.join(output['traceback'])
            text = nbconvert.filters.strip_ansi(traceback)
            to_add.append(docutils.nodes.literal_block(
                text=text,
                rawsource=text,
                language='ipythontb',
            ))
        elif (
            output_type in ('display_data', 'execute_result')
        ):
            try:
                # First mime_type by priority that occurs in output.
                mime_type = next(
                    x for x in data_priority if x in output['data']
                )
            except StopIteration:
                continue

            data = output['data'][mime_type]
            if mime_type.startswith('image'):
                # Sphinx treats absolute paths as being rooted at the source
                # directory, so make a relative path, which Sphinx treats
                # as being relative to the current working directory.
                filename = os.path.basename(
                    output.metadata['filenames'][mime_type]
                )
                uri = os.path.join(dir, filename)
                to_add.append(docutils.nodes.image(uri=uri))
            elif mime_type == 'text/html':
                to_add.append(docutils.nodes.raw(
                    text=data,
                    format='html'
                ))
            elif mime_type == 'text/latex':
                to_add.append(displaymath(
                    latex=data,
                    nowrap=False,
                    number=None,
                 ))
            elif mime_type == 'text/plain':
                to_add.append(docutils.nodes.literal_block(
                    text=data,
                    rawsource=data,
                    language='ipython',
                ))

    return to_add


def attach_outputs(output_nodes, node):
    if node.attributes['hide_code']:
        node.children = []
    if not node.attributes['hide_output']:
        if node.attributes['code_below']:
            node.children = output_nodes + node.children
        else:
            node.children = node.children + output_nodes


def default_notebook_names(basename):
    """Return an interator yielding notebook names based off 'basename'"""
    yield basename
    for i in count(1):
        yield '_'.join((basename, str(i)))


def execute_cells(kernel_name, cells, execute_kwargs):
    """Execute Jupyter cells in the specified kernel and return the notebook."""
    notebook = blank_nb(kernel_name)
    notebook.cells = cells
    # Modifies 'notebook' in-place
    try:
        executenb(notebook, **execute_kwargs)
    except Exception as e:
        raise ExtensionError('Notebook execution failed', orig_exc=e)

    return notebook


def write_notebook_output(notebook, output_dir, notebook_name):
    """Extract output from notebook cells and write to files in output_dir.

    This also modifies 'notebook' in-place, adding metadata to each cell that
    maps output mime-types to the filenames the output was saved under.
    """
    resources = dict(
        unique_key=os.path.join(output_dir, notebook_name),
        outputs={}
    )

    # Modifies 'resources' in-place
    ExtractOutputPreprocessor().preprocess(notebook, resources)
    # Write the cell outputs to files where we can (images and PDFs),
    # as well as the notebook file.
    FilesWriter(build_directory=output_dir).write(
        nbformat.writes(notebook), resources,
        os.path.join(output_dir, notebook_name + '.ipynb')
    )
    # Write a Python script too.
    contents = '\n\n'.join(cell.source for cell in notebook.cells)
    with open(os.path.join(output_dir, notebook_name + '.py'), 'w') as f:
        f.write(contents)


def output_directory(env):
    # Put output images inside the sphinx build directory to avoid
    # polluting the current working directory. We don't use a
    # temporary directory, as sphinx may cache the doctree with
    # references to the images that we write

    # Note: we are using an implicit fact that sphinx output directories are
    # direct subfolders of the build directory.
    return os.path.abspath(os.path.join(
        env.app.outdir, os.path.pardir, 'jupyter_execute'
    ))


def sphinx_abs_dir(env):
    # We write the output files into
    # output_directory / jupyter_execute / path relative to source directory
    # Sphinx expects download links relative to source file or relative to
    # source dir and prepended with '/'. We use the latter option.
    return '/' + os.path.relpath(
        os.path.abspath(os.path.join(
            output_directory(env),
            os.path.dirname(env.docname),
        )),
        os.path.abspath(env.app.srcdir)
    )


class ExecuteJupyterCells(SphinxTransform):
    default_priority = 180  # An early transform, idk

    def apply(self):
        doctree = self.document
        doc_relpath = os.path.dirname(self.env.docname)  # relative to src dir
        docname = os.path.basename(self.env.docname)
        default_kernel = self.config.jupyter_execute_default_kernel
        default_names = default_notebook_names(docname)

        # Check if we have anything to execute.
        if not doctree.traverse(Cell):
            return

        logger.info('executing {}'.format(docname))
        output_dir = os.path.join(output_directory(self.env), doc_relpath)

        # Start new notebook whenever a cell has 'new_notebook' specified
        nodes_by_notebook = split_on(
            itemgetter('new_notebook'),
            doctree.traverse(Cell)
        )

        for nodes in nodes_by_notebook:
            kernel_name = nodes[0]['kernel_name'] or default_kernel
            notebook_name = nodes[0]['notebook_name'] or next(default_names)

            notebook = execute_cells(
                kernel_name,
                [nbformat.v4.new_code_cell(node.astext()) for node in nodes],
                self.config.jupyter_execute_kwargs,
            )
            # Modifies 'notebook' in-place, adding metadata specifying the
            # filenames of the saved outputs.
            write_notebook_output(notebook, output_dir, notebook_name)
            # Add doctree nodes for cell output; images reference the filenames
            # we just wrote to; sphinx copies these when writing outputs.
            for node, cell in zip(nodes, notebook.cells):
                output_nodes = cell_output_to_nodes(
                    cell,
                    self.config.jupyter_execute_data_priority,
                    sphinx_abs_dir(self.env)
                )
                attach_outputs(output_nodes, node)


def setup(app):
    # Configuration
    app.add_config_value(
        'jupyter_execute_kwargs',
        dict(timeout=-1, allow_errors=True),
        'env'
    )
    app.add_config_value(
        'jupyter_execute_default_kernel',
        'python3',
        'env'
    )
    app.add_config_value(
        'jupyter_execute_data_priority',
        [
            'text/html',
            'image/svg+xml',
            'image/png',
            'image/jpeg',
            'text/latex',
            'text/plain'
        ],
        'env',
    )

    app.add_node(
        Cell,
        html=(visit_container, depart_container),
        latex=(visit_container, depart_container),
        textinfo=(visit_container, depart_container),
        text=(visit_container, depart_container),
        man=(visit_container, depart_container),
    )

    app.add_directive('execute', JupyterCell)
    app.add_role('jupyter-download:notebook', jupyter_download_role)
    app.add_role('jupyter-download:script', jupyter_download_role)
    app.add_transform(ExecuteJupyterCells)

    # For syntax highlighting
    app.add_lexer('ipythontb', IPythonTracebackLexer())
    app.add_lexer('ipython', IPython3Lexer())

    return {'version': __version__}
