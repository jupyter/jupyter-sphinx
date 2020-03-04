"""Manipulating the Sphinx AST with Jupyter objects"""

import os
import json

import docutils
from docutils.parsers.rst import Directive, directives
from docutils.nodes import math_block
from sphinx.util import parselinenos
from sphinx.addnodes import download_reference

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

        return [
            JupyterCellNode(
                "",
                docutils.nodes.literal_block(text="\n".join(content)),
                hide_code=("hide-code" in self.options),
                hide_output=("hide-output" in self.options),
                code_below=("code-below" in self.options),
                linenos=("linenos" in self.options),
                emphasize_lines=hl_lines,
                raises=self.options.get("raises"),
                stderr=("stderr" in self.options),
            )
        ]


class JupyterCellNode(docutils.nodes.container):
    """Inserted into doctree whever a JupyterCell directive is encountered.

    Contains code that will be executed in a Jupyter kernel at a later
    doctree-transformation step.
    """


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


def cell_output_to_nodes(cell, data_priority, write_stderr, dir, thebe_config):
    """Convert a jupyter cell with outputs and filenames to doctree nodes.

    Parameters
    ----------
    cell : jupyter cell
    data_priority : list of mime types
        Which media types to prioritize.
    write_stderr : bool
        If True include stderr in cell output
    dir : string
        Sphinx "absolute path" to the output folder, so it is a relative path
        to the source folder prefixed with ``/``.
    thebe_config: dict
        Thebelab configuration object or None
    """
    to_add = []
    for _, output in enumerate(cell.get("outputs", [])):
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
        node.attributes["classes"] = ["jupyter_container"]
    if thebe_config:
        source = node.children[0]
        thebe_source = ThebeSourceNode(
            hide_code=node.attributes["hide_code"],
            code_below=node.attributes["code_below"],
            language=cm_language,
        )
        thebe_source.children = [source]

        node.children = [thebe_source]

        if not node.attributes["hide_output"]:
            thebe_output = ThebeOutputNode()
            thebe_output.children = output_nodes
            if node.attributes["code_below"]:
                node.children = [thebe_output] + node.children
            else:
                node.children = node.children + [thebe_output]
    else:
        if node.attributes["hide_code"]:
            node.children = []
        if not node.attributes["hide_output"]:
            if node.attributes["code_below"]:
                node.children = output_nodes + node.children
            else:
                node.children = node.children + output_nodes


def jupyter_download_role(name, rawtext, text, lineno, inliner):
    _, filetype = name.split(":")
    assert filetype in ("notebook", "script")
    ext = ".ipynb" if filetype == "notebook" else ".py"
    output_dir = sphinx_abs_dir(inliner.document.settings.env)
    download_file = text + ext
    node = download_reference(
        download_file, download_file, reftarget=os.path.join(output_dir, download_file)
    )
    return [node], []


def get_widgets(notebook):
    try:
        return notebook.metadata.widgets[WIDGET_STATE_MIMETYPE]
    except AttributeError:
        # Don't catch KeyError, as it's a bug if 'widgets' does
        # not contain 'WIDGET_STATE_MIMETYPE'
        return None
