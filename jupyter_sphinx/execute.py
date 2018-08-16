"""Simple sphinx extension that executes code in jupyter and inserts output."""

import os
from itertools import takewhile

from sphinx.util import logging
from sphinx.transforms import SphinxTransform
from sphinx.errors import ExtensionError
from sphinx.ext.mathbase import displaymath

from docutils import nodes
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


class Cell(nodes.container):
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
        'new-kernel': unchanged
    }

    def run(self):
        self.assert_has_content()
        # Cell only contains the input for now; we will execute the cell
        # and insert the output when the whole document has been parsed.

        return [Cell('',
            nodes.literal_block(
                text='\n'.join(self.content),
                language='ipython'
            ),
            hide_code=('hide-code' in self.options),
            hide_output=('hide-output' in self.options),
            code_below=('code-below' in self.options),
            new_kernel=('new-kernel' in self.options),
            kernel_name=self.options.get('new-kernel', '').strip()
        )]


def cell_output_to_nodes(cell, data_priority):
    to_add = []
    for index, output in enumerate(cell.get('outputs', [])):
        output_type = output['output_type']
        if (
            output_type == 'stream'
            and output['name'] == 'stdout'
        ):
            to_add.append(nodes.literal_block(
                text=output['text'],
                rawsource=output['text'],
                language='ipython',
            ))
        elif (
            output_type == 'error'
        ):
            traceback = '\n'.join(output['traceback'])
            text = nbconvert.filters.strip_ansi(traceback)
            to_add.append(nodes.literal_block(
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
                filename = output.metadata['filenames'][mime_type]
                to_add.append(nodes.image(uri='file://' + filename))
            elif mime_type == 'text/html':
                to_add.append(nodes.raw(
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
                to_add.append(nodes.literal_block(
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


class ExecuteJupyterCells(SphinxTransform):
    default_priority = 180  # An early transform, idk

    def apply(self):
        doctree = self.document
        docname = self.env.docname
        default_kernel = self.config.jupyter_execute_default_kernel
        logger.info('executing {}'.format(docname))
        # Put output images inside the sphinx build directory to avoid
        # polluting the current working directory. We don't use a
        # temporary directory, as sphinx may cache the doctree with
        # references to the images that we write
        output_dir = os.path.abspath(os.path.join(
            self.env.app.outdir, os.path.pardir, 'jupyter_execute'))

        cells = doctree.traverse(Cell)

        with_outputs = []

        nb_number = 0
        while cells:
            kernel = cells[0]['kernel_name'] or default_kernel
            notebook = blank_nb(kernel)

            nb_name = docname
            if nb_number:
                nb_name += '_{}'.format(nb_number)
            resources = dict(
                unique_key=os.path.join(output_dir, nb_name),
                outputs={}
            )
            # Select all cells to run in the same notebook.
            to_execute = [cells[0]] + list(
                takewhile((lambda cell: not cell['new_kernel']), cells[1:])
            )
            cells = cells[len(to_execute):]

            # Populate notebook
            notebook.cells = [
                nbformat.v4.new_code_cell(
                    node.children[0].children[0].astext()
                )
                for node in to_execute
            ]

            # Execute notebook and write some (i.e. image) outputs to files
            # Modifies 'notebook' and 'resources' in-place.
            try:
                executenb(notebook, **self.config.jupyter_execute_kwargs)
            except Exception as e:
                raise ExtensionError('Notebook execution failed', orig_exc=e)

            ExtractOutputPreprocessor().preprocess(notebook, resources)
            FilesWriter(build_directory=output_dir).write(
                nbformat.writes(notebook), resources,
                os.path.join(output_dir, nb_name + '.ipynb')
            )

            with_outputs.extend(notebook.cells)

            nb_number += 1

        # Add doctree nodes for the cell output; images use references to the
        # filenames we just wrote to; sphinx copies these when writing outputs
        for node, cell in zip(doctree.traverse(Cell), with_outputs):
            output_nodes = cell_output_to_nodes(
                cell, self.config.jupyter_execute_data_priority
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

    app.add_node(Cell, html=(visit_container, depart_container))

    app.add_directive('execute', JupyterCell)
    app.add_transform(ExecuteJupyterCells)

    # For syntax highlighting
    app.add_lexer('ipythontb', IPythonTracebackLexer())
    app.add_lexer('ipython', IPython3Lexer())

    return {'version': __version__}
