"""Manipulating the Sphinx AST with Jupyter objects"""

import os
import json

import docutils
from docutils.parsers.rst import Directive, directives
from docutils.nodes import math_block, image, literal
from sphinx.util import parselinenos
from sphinx.util.docutils import ReferenceRole
from sphinx.addnodes import download_reference
from sphinx.transforms import SphinxTransform
from sphinx.environment.collectors.asset import ImageCollector

import ipywidgets.embed
import nbconvert

from .utils import strip_latex_delimiters, sphinx_abs_dir
from .thebelab import ThebeSourceNode, ThebeOutputNode

WIDGET_VIEW_MIMETYPE = "application/vnd.jupyter.widget-view+json"
WIDGET_STATE_MIMETYPE = "application/vnd.jupyter.widget-state+json"


def csv_option(s):
    return [p.strip() for p in s.split(",")] if s else []


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
    linenos : bool
        If provided, the code will be shown with line numbering.
    lineno-start: nonnegative int
        If provided, the code will be show with line numbering beginning from
        specified line.
    emphasize-lines : comma separated list of line numbers
        If provided, the specified lines will be highlighted.
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
        "hide-code": directives.flag,
        "hide-output": directives.flag,
        "code-below": directives.flag,
        "linenos": directives.flag,
        "lineno-start": directives.nonnegative_int,
        "emphasize-lines": directives.unchanged_required,
        "raises": csv_option,
        "stderr": directives.flag,
    }

    def run(self):
        # This only works lazily because the logger is inited by Sphinx
        from . import logger

        location = self.state_machine.get_source_and_line(self.lineno)

        if self.arguments:
            # As per 'sphinx.directives.code.LiteralInclude'
            env = self.state.document.settings.env
            rel_filename, filename = env.relfn2path(self.arguments[0])
            env.note_dependency(rel_filename)
            if self.content:
                logger.warning(
                    'Ignoring inline code in Jupyter cell included from "{}"'.format(
                        rel_filename
                    ),
                    location=location,
                )
            try:
                with open(filename) as f:
                    content = [line.rstrip() for line in f.readlines()]
            except (IOError, OSError):
                raise IOError("File {} not found or reading it failed".format(filename))
        else:
            self.assert_has_content()
            content = self.content

        # The code fragment is taken from CodeBlock directive almost unchanged:
        # https://github.com/sphinx-doc/sphinx/blob/0319faf8f1503453b6ce19020819a8cf44e39f13/sphinx/directives/code.py#L134-L148

        emphasize_linespec = self.options.get("emphasize-lines")
        if emphasize_linespec:
            try:
                nlines = len(content)
                hl_lines = parselinenos(emphasize_linespec, nlines)
                if any(i >= nlines for i in hl_lines):
                    logger.warning(
                        "Line number spec is out of range(1-{}): {}".format(
                            nlines, emphasize_linespec
                        ),
                        location=location,
                    )
                hl_lines = [i + 1 for i in hl_lines if i < nlines]
            except ValueError as err:
                return [self.state.document.reporter.warning(err, line=self.lineno)]
        else:
            hl_lines = []

        # A top-level placeholder for our cell
        cell_node = JupyterCellNode(
            hide_code=("hide-code" in self.options),
            hide_output=("hide-output" in self.options),
            code_below=("code-below" in self.options),
            linenos=("linenos" in self.options),
            linenostart=(self.options.get("lineno-start")),
            emphasize_lines=hl_lines,
            raises=self.options.get("raises"),
            stderr=("stderr" in self.options),
            classes=["jupyter_cell"],
        )

        # Add the input section of the cell, we'll add output at execution time
        cell_input = CellInputNode(classes=["cell_input"])
        cell_input += docutils.nodes.literal_block(text="\n".join(content))
        cell_node += cell_input
        return [cell_node]


class JupyterCellNode(docutils.nodes.container):
    """Inserted into doctree whever a JupyterCell directive is encountered.

    Contains code that will be executed in a Jupyter kernel at a later
    doctree-transformation step.
    """


class CellInputNode(docutils.nodes.container):
    """Represent an input cell in the Sphinx AST."""

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", **attributes)


class CellOutputNode(docutils.nodes.container):
    """Represent an output cell in the Sphinx AST."""

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", **attributes)


class CellOutputBundleNode(docutils.nodes.container):
    """Represent a MimeBundle in the Sphinx AST, to be transformed later."""

    def __init__(self, outputs, rawsource="", *children, **attributes):
        self.outputs = outputs
        super().__init__("", **attributes)


class JupyterKernelNode(docutils.nodes.Element):
    """Inserted into doctree whenever a JupyterKernel directive is encountered.

    Used as a marker to signal that the following JupyterCellNodes (until the
    next, if any, JupyterKernelNode) should be executed in a separate kernel.
    """


class JupyterWidgetViewNode(docutils.nodes.Element):
    """Inserted into doctree whenever a Jupyter cell produces a widget as output.

    Contains a unique ID for this widget; enough information for the widget
    embedding javascript to render it, given the widget state. For non-HTML
    outputs this doctree node is rendered generically.
    """

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", view_spec=attributes["view_spec"])

    def html(self):
        return ipywidgets.embed.widget_view_template.format(
            view_spec=json.dumps(self["view_spec"])
        )


class JupyterWidgetStateNode(docutils.nodes.Element):
    """Appended to doctree if any Jupyter cell produced a widget as output.

    Contains the state needed to render a collection of Jupyter widgets.

    Per doctree there is 1 JupyterWidgetStateNode per kernel that produced
    Jupyter widgets when running. This is fine as (presently) the
    'html-manager' Javascript library, which embeds widgets, loads the state
    from all script tags on the page of the correct mimetype.
    """

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", state=attributes["state"])

    def html(self):
        # TODO: render into a separate file if 'html-manager' starts fully
        #       parsing script tags, and not just grabbing their innerHTML
        # https://github.com/jupyter-widgets/ipywidgets/blob/master/packages/html-manager/src/libembed.ts#L36
        return ipywidgets.embed.snippet_template.format(
            load="", widget_views="", json_data=json.dumps(self["state"])
        )


def cell_output_to_nodes(outputs, data_priority, write_stderr, dir, thebe_config):
    """Convert a jupyter cell with outputs and filenames to doctree nodes.

    Parameters
    ----------
    outputs : a list of outputs from a Jupyter cell
    data_priority : list of mime types
        Which media types to prioritize.
    write_stderr : bool
        If True include stderr in cell output
    dir : string
        Sphinx "absolute path" to the output folder, so it is a relative path
        to the source folder prefixed with ``/``.
    thebe_config: dict
        Thebelab configuration object or None

    Returns
    -------
    to_add : list of docutils nodes
        Each output, converted into a docutils node.
    """
    to_add = []
    for output in outputs:
        output_type = output["output_type"]
        if output_type == "stream":
            if output["name"] == "stderr":
                if not write_stderr:
                    continue
                else:
                    # Output a container with an unhighlighted literal block for
                    # `stderr` messages.
                    #
                    # Adds a "stderr" class that can be customized by the user for both
                    # the container and the literal_block.
                    #
                    # Not setting "rawsource" disables Pygment hightlighting, which
                    # would otherwise add a <div class="highlight">.

                    container = docutils.nodes.container(classes=["stderr"])
                    container.append(
                        docutils.nodes.literal_block(
                            text=output["text"],
                            rawsource="",  # disables Pygment highlighting
                            language="none",
                            classes=["stderr"],
                        )
                    )
                    to_add.append(container)
            else:
                to_add.append(
                    docutils.nodes.literal_block(
                        text=output["text"],
                        rawsource=output["text"],
                        language="none",
                        classes=["output", "stream"],
                    )
                )
        elif output_type == "error":
            traceback = "\n".join(output["traceback"])
            text = nbconvert.filters.strip_ansi(traceback)
            to_add.append(
                docutils.nodes.literal_block(
                    text=text,
                    rawsource=text,
                    language="ipythontb",
                    classes=["output", "traceback"],
                )
            )
        elif output_type in ("display_data", "execute_result"):
            try:
                # First mime_type by priority that occurs in output.
                mime_type = next(x for x in data_priority if x in output["data"])
            except StopIteration:
                continue
            data = output["data"][mime_type]
            if mime_type.startswith("image"):
                # Sphinx treats absolute paths as being rooted at the source
                # directory, so make a relative path, which Sphinx treats
                # as being relative to the current working directory.
                filename = os.path.basename(output.metadata["filenames"][mime_type])

                # checks if file dir path is inside a subdir of dir
                filedir = os.path.dirname(output.metadata["filenames"][mime_type])
                subpaths = filedir.split(dir)
                if subpaths and len(subpaths) > 1:
                    subpath = subpaths[1]
                    dir += subpath

                uri = os.path.join(dir, filename)
                to_add.append(docutils.nodes.image(uri=uri))
            elif mime_type == "text/html":
                to_add.append(
                    docutils.nodes.raw(
                        text=data, format="html", classes=["output", "text_html"]
                    )
                )
            elif mime_type == "text/latex":
                to_add.append(
                    math_block(
                        text=strip_latex_delimiters(data),
                        nowrap=False,
                        number=None,
                        classes=["output", "text_latex"],
                    )
                )
            elif mime_type == "text/plain":
                to_add.append(
                    docutils.nodes.literal_block(
                        text=data,
                        rawsource=data,
                        language="none",
                        classes=["output", "text_plain"],
                    )
                )
            elif mime_type == "application/javascript":
                to_add.append(
                    docutils.nodes.raw(
                        text='<script type="{mime_type}">{data}</script>'.format(
                            mime_type=mime_type, data=data
                        ),
                        format="html",
                    )
                )
            elif mime_type == WIDGET_VIEW_MIMETYPE:
                to_add.append(JupyterWidgetViewNode(view_spec=data))

    return to_add


def attach_outputs(output_nodes, node, thebe_config, cm_language):
    if not node.attributes["hide_code"]:  # only add css if code is displayed
        classes = node.attributes.get("classes", [])
        classes += ["jupyter_container"]

    (input_node,) = node.traverse(CellInputNode)
    (outputbundle_node,) = node.traverse(CellOutputBundleNode)
    output_node = CellOutputNode(classes=["cell_output"])
    if thebe_config:
        # Move the source from the input node into the thebe_source node
        source = input_node.children.pop(0)
        thebe_source = ThebeSourceNode(
            hide_code=node.attributes["hide_code"],
            code_below=node.attributes["code_below"],
            language=cm_language,
        )
        thebe_source.children = [source]
        input_node.children = [thebe_source]

        if not node.attributes["hide_output"]:
            thebe_output = ThebeOutputNode()
            thebe_output.children = output_nodes
            output_node += thebe_output
    else:
        if node.attributes["hide_code"]:
            node.children.pop(0)
        if not node.attributes["hide_output"]:
            output_node.children = output_nodes

    # Now replace the bundle with our OutputNode
    outputbundle_node.replace_self(output_node)

    # Swap inputs and outputs if we want the code below
    if node.attributes["code_below"]:
        node.children = node.children[::-1]


class JupyterDownloadRole(ReferenceRole):
    def run(self):
        _, filetype = self.name.split(":")

        assert filetype in ("notebook", "nb", "script")
        ext = ".ipynb" if filetype in ("notebook", "nb") else ".py"
        download_file = self.target + ext
        reftarget = sphinx_abs_dir(self.env, download_file)
        node = download_reference(self.rawtext, reftarget=reftarget)
        self.set_source_info(node)
        title = self.title if self.has_explicit_title else download_file
        node += literal(self.rawtext, title, classes=["xref", "download"])
        return [node], []


def get_widgets(notebook):
    try:
        return notebook.metadata.widgets[WIDGET_STATE_MIMETYPE]
    except AttributeError:
        # Don't catch KeyError, as it's a bug if 'widgets' does
        # not contain 'WIDGET_STATE_MIMETYPE'
        return None


class CellOutputsToNodes(SphinxTransform):
    """Use the builder context to transform a CellOutputNode into Sphinx nodes."""

    default_priority = 700

    def apply(self):
        thebe_config = self.config.jupyter_sphinx_thebelab_config

        for cell_node in self.document.traverse(JupyterCellNode):
            (output_bundle_node,) = cell_node.traverse(CellOutputBundleNode)

            # Create doctree nodes for cell outputs.
            output_nodes = cell_output_to_nodes(
                output_bundle_node.outputs,
                self.config.jupyter_execute_data_priority,
                bool(cell_node.attributes["stderr"]),
                sphinx_abs_dir(self.env),
                thebe_config,
            )
            # Remove the outputbundlenode and we'll attach the outputs next
            attach_outputs(output_nodes, cell_node, thebe_config, cell_node.cm_language)

        # Image collect extra nodes from cell outputs that we need to process
        for node in self.document.traverse(image):
            # If the image node has `candidates` then it's already been processed
            # as in-line content, so skip it
            if "candidates" in node:
                continue
            # re-initialize an ImageCollector because the `app` imagecollector instance
            # is only available via event listeners.
            col = ImageCollector()
            col.process_doc(self.app, node)
