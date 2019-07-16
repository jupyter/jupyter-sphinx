"""Simple sphinx extension that executes code in jupyter and inserts output."""

import os
from itertools import groupby, count
from operator import itemgetter
import json

import sphinx
from sphinx.util import logging
from sphinx.util.fileutil import copy_asset
from sphinx.transforms import SphinxTransform
from sphinx.errors import ExtensionError
from sphinx.addnodes import download_reference
from sphinx.ext.mathbase import displaymath

import docutils
from IPython.lib.lexers import IPythonTracebackLexer, IPython3Lexer
from docutils.parsers.rst import Directive, directives

import nbconvert
from nbconvert.preprocessors.execute import executenb
from nbconvert.preprocessors import ExtractOutputPreprocessor
from nbconvert.writers import FilesWriter

from jupyter_client.kernelspec import get_kernel_spec, NoSuchKernel

import nbformat

from ipywidgets import Widget
import ipywidgets.embed

from ._version import __version__


logger = logging.getLogger(__name__)

WIDGET_VIEW_MIMETYPE = 'application/vnd.jupyter.widget-view+json'
WIDGET_STATE_MIMETYPE = 'application/vnd.jupyter.widget-state+json'
REQUIRE_URL_DEFAULT = 'https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.4/require.min.js'
THEBELAB_URL_DEFAULT = 'https://unpkg.com/thebelab@^0.4.0'


def builder_inited(app):
    """
    2 cases
    case 1: ipywidgets 7, with require
    case 2: ipywidgets 7, no require
    """
    require_url = app.config.jupyter_sphinx_require_url
    if require_url:
        app.add_js_file(require_url)
        embed_url = app.config.jupyter_sphinx_embed_url or ipywidgets.embed.DEFAULT_EMBED_REQUIREJS_URL
    else:
        embed_url = app.config.jupyter_sphinx_embed_url or ipywidgets.embed.DEFAULT_EMBED_SCRIPT_URL
    if embed_url:
        app.add_js_file(embed_url)

    # Check if a thebelab config was specified
    if app.config.jupyter_sphinx_thebelab_config:
        app.add_js_file('thebelab-helper.js')
        app.add_css_file('thebelab.css')

### Directives and their associated doctree nodes

class JupyterKernel(Directive):
    """Specify a new Jupyter Kernel.

    Arguments
    ---------
    kernel_name : str (optional)
        The name of the kernel in which to execute future Jupyter cells, as
        reported by executing 'jupyter kernelspec list' on the command line.

    Options
    -------
    id : str
        An identifier for *this kernel instance*. Used to name any output
        files generated when executing the Jupyter cells (e.g. images
        produced by cells, or a script containing the cell inputs).

    Content
    -------
    None
    """

    optional_arguments = 1
    final_argument_whitespace = False
    has_content = False

    option_spec = {
        'id': directives.unchanged,
    }

    def run(self):
        return [JupyterKernelNode(
            '',
            kernel_name=self.arguments[0].strip() if self.arguments else '',
            kernel_id=self.options.get('id', '').strip(),
        )]


class JupyterKernelNode(docutils.nodes.Element):
    """Inserted into doctree whenever a JupyterKernel directive is encountered.

    Used as a marker to signal that the following JupyterCellNodes (until the
    next, if any, JupyterKernelNode) should be executed in a separate kernel.
    """


def csv_option(s):
    return [p.strip() for p in s.split(',')] if s else []


class JupyterCell(Directive):
    """Define a code cell to be later executed in a Jupyter kernel.

    The content of the directive is the code to execute. Code is not
    executed when the directive is parsed, but later during a doctree
    transformation.

    Arguments
    ---------
    filename : str (optional)
        If provided, a path to a file containing code.

    Options
    -------
    hide-code : bool
        If provided, the code will not be displayed in the output.
    hide-output : bool
        If provided, the cell output will not be displayed in the output.
    code-below : bool
        If provided, the code will be shown below the cell output.
    raises : comma separated list of exception types
        If provided, a comma-separated list of exception type names that
        the cell may raise. If one of the listed execption types is raised
        then the traceback is printed in place of the cell output. If an
        exception of another type is raised then we raise a RuntimeError
        when executing.

    Content
    -------
    code : str
        A code cell.
    """

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True

    option_spec = {
        'hide-code': directives.flag,
        'hide-output': directives.flag,
        'code-below': directives.flag,
        'raises': csv_option,
        'stderr': directives.flag,
    }

    def run(self):
        if self.arguments:
            # As per 'sphinx.directives.code.LiteralInclude'
            env = self.state.document.settings.env
            rel_filename, filename = env.relfn2path(self.arguments[0])
            env.note_dependency(rel_filename)
            if self.content:
                logger.warning(
                    'Ignoring inline code in Jupyter cell included from "{}"'
                    .format(rel_filename)
                )
            try:
                with open(filename) as f:
                    content = [line.rstrip() for line in f.readlines()]
            except (IOError, OSError):
                raise IOError(
                    'File {} not found or reading it failed'.format(filename)
                )
        else:
            self.assert_has_content()
            content = self.content

        return [JupyterCellNode(
            '',
            docutils.nodes.literal_block(
                text='\n'.join(content),
            ),
            hide_code=('hide-code' in self.options),
            hide_output=('hide-output' in self.options),
            code_below=('code-below' in self.options),
            raises=self.options.get('raises'),
            stderr=('stderr' in self.options),
        )]


class ThebeButton(Directive):
    """Specify a button to activate thebelab on the page

    Arguments
    ---------
    text : str (optional)
        If provided, the button text to display

    Content
    -------
    None
    """

    optional_arguments = 1
    final_argument_whitespace = True
    has_content = False

    def run(self):
        kwargs = {'text': self.arguments[0]} if self.arguments else {}
        return [ThebeButtonNode(**kwargs)]


class JupyterCellNode(docutils.nodes.container):
    """Inserted into doctree whever a JupyterCell directive is encountered.

    Contains code that will be executed in a Jupyter kernel at a later
    doctree-transformation step.
    """


class JupyterWidgetViewNode(docutils.nodes.Element):
    """Inserted into doctree whenever a Jupyter cell produces a widget as output.

    Contains a unique ID for this widget; enough information for the widget
    embedding javascript to render it, given the widget state. For non-HTML
    outputs this doctree node is rendered generically.
    """

    def __init__(self, rawsource='', *children, **attributes):
        super().__init__('', view_spec=attributes['view_spec'])

    def html(self):
        return ipywidgets.embed.widget_view_template.format(
            view_spec=json.dumps(self['view_spec']))


class JupyterWidgetStateNode(docutils.nodes.Element):
    """Appended to doctree if any Jupyter cell produced a widget as output.

    Contains the state needed to render a collection of Jupyter widgets.

    Per doctree there is 1 JupyterWidgetStateNode per kernel that produced
    Jupyter widgets when running. This is fine as (presently) the
    'html-manager' Javascript library, which embeds widgets, loads the state
    from all script tags on the page of the correct mimetype.
    """

    def __init__(self, rawsource='', *children, **attributes):
        super().__init__('', state=attributes['state'])

    def html(self):
        # TODO: render into a separate file if 'html-manager' starts fully
        #       parsing script tags, and not just grabbing their innerHTML
        # https://github.com/jupyter-widgets/ipywidgets/blob/master/packages/html-manager/src/libembed.ts#L36
        return ipywidgets.embed.snippet_template.format(
            load='', widget_views='', json_data=json.dumps(self['state']))


class ThebeSourceNode(docutils.nodes.container):
    """Container that holds the cell source when thebelab is enabled"""

    def __init__(self, rawsource='', *children, **attributes):
        super().__init__('', **attributes)

    def visit_html(self):
        code_class = 'thebelab-code'
        if self['hide_code']:
            code_class += ' thebelab-hidden'
        if self['code_below']:
            code_class += ' thebelab-below'
        language = self['language']
        return '<div class="{}" data-executable="true" data-language="{}">'\
               .format(code_class, language)

    def depart_html(self):
        return '</div>'


class ThebeOutputNode(docutils.nodes.container):
    """Container that holds all the output nodes when thebelab is enabled"""

    def visit_html(self):
        return '<div class="thebelab-output" data-output="true">'

    def depart_html(self):
        return '</div>'


class ThebeButtonNode(docutils.nodes.Element):
    """Appended to the doctree by the ThebeButton directive

    Renders as a button to enable thebelab on the page.

    If no ThebeButton directive is found in the document but thebelab
    is enabled, the node is added at the bottom of the document.
    """
    def __init__(self, rawsource='', *children, text='Make live', **attributes):
        super().__init__('', text=text)

    def html(self):
        text = self['text']
        return ('<button title="Make live" class="thebelab-button" id="thebelab-activate-button" ' +
                'onclick="initThebelab()">{}</button>'.format(text))

### Doctree transformations

class ExecuteJupyterCells(SphinxTransform):
    """Execute code cells in Jupyter kernels.

   Traverses the doctree to find JupyterKernel and JupyterCell nodes,
   then executes the code in the JupyterCell nodes in sequence, starting
   a new kernel every time a JupyterKernel node is encountered. The output
   from each code cell is inserted into the doctree.
   """
    default_priority = 180  # An early transform, idk

    def apply(self):
        doctree = self.document
        doc_relpath = os.path.dirname(self.env.docname)  # relative to src dir
        docname = os.path.basename(self.env.docname)
        default_kernel = self.config.jupyter_execute_default_kernel
        default_names = default_notebook_names(docname)
        thebe_config = self.config.jupyter_sphinx_thebelab_config

        # Check if we have anything to execute.
        if not doctree.traverse(JupyterCellNode):
            return

        if thebe_config:
            # Add the button at the bottom if it is not present
            if not doctree.traverse(ThebeButtonNode):
                doctree.append(ThebeButtonNode())

            add_thebelab_library(doctree, self.env)

        logger.info('executing {}'.format(docname))
        output_dir = os.path.join(output_directory(self.env), doc_relpath)

        # Start new notebook whenever a JupyterKernelNode is encountered
        jupyter_nodes = (JupyterCellNode, JupyterKernelNode)
        nodes_by_notebook = split_on(
            lambda n: isinstance(n, JupyterKernelNode),
            doctree.traverse(lambda n: isinstance(n, jupyter_nodes))
        )

        for first, *nodes in nodes_by_notebook:
            if isinstance(first, JupyterKernelNode):
                kernel_name = first['kernel_name'] or default_kernel
                file_name = first['kernel_id'] or next(default_names)
            else:
                nodes = (first, *nodes)
                kernel_name = default_kernel
                file_name = next(default_names)

            notebook = execute_cells(
                kernel_name,
                [nbformat.v4.new_code_cell(node.astext()) for node in nodes],
                self.config.jupyter_execute_kwargs,
            )

            # Raise error if cells raised exceptions and were not marked as doing so
            for node, cell in zip(nodes, notebook.cells):
                errors = [output for output in cell.outputs if output['output_type'] == 'error']
                allowed_errors = node.attributes.get('raises') or []
                raises_provided = node.attributes['raises'] is not None
                if raises_provided and not allowed_errors: # empty 'raises': supress all errors
                    pass
                elif errors and not any(e['ename'] in allowed_errors for e in errors):
                    raise ExtensionError('Cell raised uncaught exception:\n{}'
                                         .format('\n'.join(errors[0]['traceback'])))

            # Raise error if cells print to stderr
            for node, cell in zip(nodes, notebook.cells):
                stderr = [output for output in cell.outputs
                          if output['output_type'] == 'stream'
                             and output['name'] == 'stderr']
                if stderr and not node.attributes['stderr']:
                    raise ExtensionError('Cell printed to stderr:\n{}'
                                         .format(stderr[0]['text']))

            try:
                lexer = notebook.metadata.language_info.pygments_lexer
            except AttributeError:
                lexer = notebook.metadata.kernelspec.language

            # Highlight the code cells now that we know what language they are
            for node in nodes:
                source = node.children[0]
                source.attributes['language'] = lexer

            # Write certain cell outputs (e.g. images) to separate files, and
            # modify the metadata of the associated cells in 'notebook' to
            # include the path to the output file.
            write_notebook_output(notebook, output_dir, file_name)

            try:
                cm_language = notebook.metadata.language_info.codemirror_mode.name
            except AttributeError:
                cm_language = notebook.metadata.kernelspec.language

            # Add doctree nodes for cell outputs.
            for node, cell in zip(nodes, notebook.cells):
                output_nodes = cell_output_to_nodes(
                    cell,
                    self.config.jupyter_execute_data_priority,
                    sphinx_abs_dir(self.env),
                    thebe_config
                )
                attach_outputs(output_nodes, node, thebe_config, cm_language)

            if contains_widgets(notebook):
                doctree.append(JupyterWidgetStateNode(state=get_widgets(notebook)))


### Roles

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


### Utilities

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


def cell_output_to_nodes(cell, data_priority, dir, thebe_config):
    """Convert a jupyter cell with outputs and filenames to doctree nodes.

    Parameters
    ----------
    cell : jupyter cell
    data_priority : list of mime types
        Which media types to prioritize.
    dir : string
        Sphinx "absolute path" to the output folder, so it is a relative path
        to the source folder prefixed with ``/``.
    thebe_config: dict
        Thebelab configuration object or None
    """
    to_add = []
    for index, output in enumerate(cell.get('outputs', [])):
        output_type = output['output_type']
        if (
            output_type == 'stream'
        ):
            to_add.append(docutils.nodes.literal_block(
                text=output['text'],
                rawsource=output['text'],
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
                ))
            elif mime_type == 'application/javascript':
                to_add.append(docutils.nodes.raw(
                    text='<script type="{mime_type}">{data}</script>'
                         .format(mime_type=mime_type, data=data),
                    format='html',
                ))
            elif mime_type == WIDGET_VIEW_MIMETYPE:
                to_add.append(JupyterWidgetViewNode(view_spec=data))

    return to_add


def attach_outputs(output_nodes, node, thebe_config, cm_language):
    if thebe_config:
        source = node.children[0]

        thebe_source = ThebeSourceNode(hide_code=node.attributes['hide_code'],
                                       code_below=node.attributes['code_below'],
                                       language=cm_language)
        thebe_source.children = [source]

        node.children = [thebe_source]

        if not node.attributes['hide_output']:
            thebe_output = ThebeOutputNode()
            thebe_output.children = output_nodes
            if node.attributes['code_below']:
                node.children = [thebe_output] + node.children
            else:
                node.children = node.children + [thebe_output]
    else:
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


def get_widgets(notebook):
    try:
        return notebook.metadata.widgets[WIDGET_STATE_MIMETYPE]
    except AttributeError:
        # Don't catch KeyError, as it's a bug if 'widgets' does
        # not contain 'WIDGET_STATE_MIMETYPE'
        return None


def contains_widgets(notebook):
    widgets = get_widgets(notebook)
    return widgets and widgets['state']


def language_info(executor):
    # Can only run this function inside 'setup_preprocessor'
    assert hasattr(executor, 'kc')
    info_msg = executor._wait_for_reply(executor.kc.kernel_info())
    return info_msg['content']['language_info']


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
    # Write a script too.
    ext = notebook.metadata.language_info.file_extension
    contents = '\n\n'.join(cell.source for cell in notebook.cells)
    with open(os.path.join(output_dir, notebook_name + ext), 'w') as f:
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


def add_thebelab_library(doctree, env):
    """Adds the thebelab configuration and library to the doctree"""
    thebe_config = env.config.jupyter_sphinx_thebelab_config
    if isinstance(thebe_config, dict):
        pass
    elif isinstance(thebe_config, str):
        if os.path.isabs(thebe_config):
            filename = thebe_config
        else:
            filename = os.path.join(os.path.abspath(env.app.srcdir), thebe_config)

        if not os.path.exists(filename):
            logger.warning('The supplied thebelab configuration file does not exist')
            return

        with open(filename, 'r') as config_file:
            try:
                thebe_config = json.load(config_file)
            except ValueError:
                logger.warning('The supplied thebelab configuration file is not in JSON format.')
                return
    else:
        logger.warning('The supplied thebelab configuration should be either a filename or a dictionary.')
        return

    # Force config values to make thebelab work correctly
    thebe_config['predefinedOutput'] = True
    thebe_config['requestKernel'] = True

    # Specify the thebelab config inline, a separate file is not supported
    doctree.append(docutils.nodes.raw(
        text='\n<script type="text/x-thebe-config">\n{}\n</script>'
             .format(json.dumps(thebe_config)),
        format='html'
    ))

    # Add thebelab library after the config is specified
    doctree.append(docutils.nodes.raw(
        text='\n<script type="text/javascript" src="{}"></script>'
             .format(env.config.jupyter_sphinx_thebelab_url),
        format='html'
    ))


def build_finished(app, env):
    if app.builder.format != 'html':
        return

    thebe_config = app.config.jupyter_sphinx_thebelab_config
    if not thebe_config:
        return

    # Copy all thebelab related assets
    src = os.path.join(os.path.dirname(__file__), 'thebelab')
    dst = os.path.join(app.outdir, '_static')
    copy_asset(src, dst)


def setup(app):
    # Configuration
    app.add_config_value(
        'jupyter_execute_kwargs',
        dict(timeout=-1, allow_errors=True, store_widget_state=True),
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
            WIDGET_VIEW_MIMETYPE,
            'application/javascript',
            'text/html',
            'image/svg+xml',
            'image/png',
            'image/jpeg',
            'text/latex',
            'text/plain'
        ],
        'env',
    )

    # ipywidgets config
    app.add_config_value('jupyter_sphinx_require_url', REQUIRE_URL_DEFAULT, 'html')
    app.add_config_value('jupyter_sphinx_embed_url', None, 'html')

    # thebelab config, can be either a filename or a dict
    app.add_config_value('jupyter_sphinx_thebelab_config', None, 'html')

    app.add_config_value('jupyter_sphinx_thebelab_url', THEBELAB_URL_DEFAULT, 'html')

    # Used for nodes that do not need to be rendered
    def skip(self, node):
        raise docutils.nodes.SkipNode

    # Renders the children of a container
    render_container = (
        lambda self, node: self.visit_container(node),
        lambda self, node: self.depart_container(node),
    )

    # Used to render the container and its children as HTML
    def visit_container_html(self, node):
        self.body.append(node.visit_html())
        self.visit_container(node)

    def depart_container_html(self, node):
        self.depart_container(node)
        self.body.append(node.depart_html())

    # Used to render an element node as HTML
    def visit_element_html(self, node):
        self.body.append(node.html())
        raise docutils.nodes.SkipNode

    # Used to render the ThebeSourceNode conditionally for non-HTML builders
    def visit_thebe_source(self, node):
        if node['hide_code']:
            raise docutils.nodes.SkipNode
        else:
            self.visit_container(node)

    render_thebe_source = (
        visit_thebe_source,
        lambda self, node: self.depart_container(node)
    )


    # JupyterKernelNode is just a doctree marker for the
    # ExecuteJupyterCells transform, so we don't actually render it.
    app.add_node(
        JupyterKernelNode,
        html=(skip, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )

    # JupyterCellNode is a container that holds the input and
    # any output, so we render it as a container.
    app.add_node(
        JupyterCellNode,
        html=render_container,
        latex=render_container,
        textinfo=render_container,
        text=render_container,
        man=render_container,
    )

    # JupyterWidgetViewNode holds widget view JSON,
    # but is only rendered properly in HTML documents.
    app.add_node(
        JupyterWidgetViewNode,
        html=(visit_element_html, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )
    # JupyterWidgetStateNode holds the widget state JSON,
    # but is only rendered in HTML documents.
    app.add_node(
        JupyterWidgetStateNode,
        html=(visit_element_html, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )

    # ThebeSourceNode holds the source code and is rendered if
    # hide-code is not specified. For HTML it is always rendered,
    # but hidden using the stylesheet
    app.add_node(
        ThebeSourceNode,
        html=(visit_container_html, depart_container_html),
        latex=render_thebe_source,
        textinfo=render_thebe_source,
        text=render_thebe_source,
        man=render_thebe_source,
    )

    # ThebeOutputNode holds the output of the Jupyter cells
    # and is rendered if hide-output is not specified.
    app.add_node(
        ThebeOutputNode,
        html=(visit_container_html, depart_container_html),
        latex=render_container,
        textinfo=render_container,
        text=render_container,
        man=render_container,
    )

    # ThebeButtonNode is the button that activates thebelab
    # and is only rendered for the HTML builder
    app.add_node(
        ThebeButtonNode,
        html=(visit_element_html, None),
        latex=(skip, None),
        textinfo=(skip, None),
        text=(skip, None),
        man=(skip, None),
    )

    app.add_directive('jupyter-execute', JupyterCell)
    app.add_directive('jupyter-kernel', JupyterKernel)
    app.add_directive('thebe-button', ThebeButton)
    app.add_role('jupyter-download:notebook', jupyter_download_role)
    app.add_role('jupyter-download:script', jupyter_download_role)
    app.add_transform(ExecuteJupyterCells)

    # For syntax highlighting
    app.add_lexer('ipythontb', IPythonTracebackLexer())
    app.add_lexer('ipython', IPython3Lexer())

    app.connect('builder-inited', builder_inited)
    app.connect('build-finished', build_finished)

    return {
        'version': __version__,
        'parallel_read_safe': True,
    }
