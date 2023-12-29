"""Manipulating the Sphinx AST with Jupyter objects."""

import json
import warnings
from pathlib import Path

import docutils
import ipywidgets.embed
import nbconvert
from docutils.nodes import literal, math_block
from docutils.parsers.rst import Directive, directives
from sphinx.addnodes import download_reference
from sphinx.errors import ExtensionError
from sphinx.transforms import SphinxTransform
from sphinx.util import parselinenos
from sphinx.util.docutils import ReferenceRole

from .thebelab import ThebeOutputNode, ThebeSourceNode
from .utils import sphinx_abs_dir, strip_latex_delimiters

WIDGET_VIEW_MIMETYPE = "application/vnd.jupyter.widget-view+json"
WIDGET_STATE_MIMETYPE = "application/vnd.jupyter.widget-state+json"


def csv_option(s):
    return [p.strip() for p in s.split(",")] if s else []


def load_content(cell, location, logger):
    if cell.arguments:
        # As per 'sphinx.directives.code.LiteralInclude'
        env = cell.state.document.settings.env
        rel_filename, filename = env.relfn2path(cell.arguments[0])
        env.note_dependency(rel_filename)
        if cell.content:
            logger.warning(
                'Ignoring inline code in Jupyter cell included from "{}"'.format(rel_filename),
                location=location,
            )
        try:
            with Path(filename).open() as f:
                content = [line.rstrip() for line in f.readlines()]
        except OSError:
            raise OSError(f"File {filename} not found or reading it failed")
    else:
        cell.assert_has_content()
        content = cell.content
    return content


def get_highlights(cell, content, location, logger):
    # The code fragment is taken from CodeBlock directive almost unchanged:
    # https://github.com/sphinx-doc/sphinx/blob/0319faf8f1503453b6ce19020819a8cf44e39f13/sphinx/directives/code.py#L134-L148

    emphasize_linespec = cell.options.get("emphasize-lines")
    if emphasize_linespec:
        nlines = len(content)
        hl_lines = parselinenos(emphasize_linespec, nlines)
        if any(i >= nlines for i in hl_lines):
            logger.warning(
                "Line number spec is out of range(1-{}): {}".format(nlines, emphasize_linespec),
                location=location,
            )
        hl_lines = [i + 1 for i in hl_lines if i < nlines]
    else:
        hl_lines = []
    return hl_lines


class JupyterCell(Directive):
    """Define a code cell to be later executed in a Jupyter kernel.

    The content of the directive is the code to execute. Code is not
    executed when the directive is parsed, but later during a doctree
    transformation.

    Arguments:
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
        the cell may raise. If one of the listed exception types is raised
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

        content = load_content(self, location, logger)

        try:
            hl_lines = get_highlights(self, content, location, logger)
        except ValueError as err:
            return [self.state.document.reporter.warning(err, line=self.lineno)]

        # A top-level placeholder for our cell
        cell_node = JupyterCellNode(
            execute=True,
            hide_code=("hide-code" in self.options),
            hide_output=("hide-output" in self.options),
            code_below=("code-below" in self.options),
            emphasize_lines=hl_lines,
            raises=self.options.get("raises"),
            stderr=("stderr" in self.options),
            classes=["jupyter_cell"],
        )

        # Add the input section of the cell, we'll add output at execution time
        cell_input = CellInputNode(classes=["cell_input"])
        cell_input += docutils.nodes.literal_block(
            text="\n".join(content),
            linenos=("linenos" in self.options),
            linenostart=(self.options.get("lineno-start")),
        )
        cell_node += cell_input
        return [cell_node]


class CellInput(Directive):
    """Define a code cell to be included verbatim but not executed.

    Arguments:
    ---------
    filename : str (optional)
        If provided, a path to a file containing code.

    Options
    -------
    linenos : bool
        If provided, the code will be shown with line numbering.
    lineno-start: nonnegative int
        If provided, the code will be show with line numbering beginning from
        specified line.
    emphasize-lines : comma separated list of line numbers
        If provided, the specified lines will be highlighted.

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
        "linenos": directives.flag,
        "lineno-start": directives.nonnegative_int,
        "emphasize-lines": directives.unchanged_required,
    }

    def run(self):
        # This only works lazily because the logger is inited by Sphinx
        from . import logger

        location = self.state_machine.get_source_and_line(self.lineno)

        content = load_content(self, location, logger)

        try:
            hl_lines = get_highlights(self, content, location, logger)
        except ValueError as err:
            return [self.state.document.reporter.warning(err, line=self.lineno)]

        # A top-level placeholder for our cell
        cell_node = JupyterCellNode(
            execute=False,
            hide_code=False,
            hide_output=True,
            code_below=False,
            emphasize_lines=hl_lines,
            raises=False,
            stderr=False,
            classes=["jupyter_cell"],
        )

        # Add the input section of the cell, we'll add output when jupyter-execute cells are run
        cell_input = CellInputNode(classes=["cell_input"])
        cell_input += docutils.nodes.literal_block(
            text="\n".join(content),
            linenos=("linenos" in self.options),
            linenostart=(self.options.get("lineno-start")),
        )
        cell_node += cell_input
        return [cell_node]


class CellOutput(Directive):
    """Define an output cell to be included verbatim.

    Arguments:
    ---------
    filename : str (optional)
        If provided, a path to a file containing output.

    Content
    -------
    code : str
        An output cell.
    """

    required_arguments = 0
    optional_arguments = 1
    final_argument_whitespace = True
    has_content = True

    option_spec = {}

    def run(self):
        # This only works lazily because the logger is inited by Sphinx
        from . import logger

        location = self.state_machine.get_source_and_line(self.lineno)

        content = load_content(self, location, logger)

        # A top-level placeholder for our cell
        cell_node = JupyterCellNode(
            execute=False,
            hide_code=True,
            hide_output=False,
            code_below=False,
            emphasize_lines=[],
            raises=False,
            stderr=False,
        )

        # Add a blank input and the given output to the cell
        cell_input = CellInputNode(classes=["cell_input"])
        cell_input += docutils.nodes.literal_block(
            text="",
            linenos=False,
            linenostart=None,
        )
        cell_node += cell_input
        content_str = "\n".join(content)
        cell_output = CellOutputNode(classes=["cell_output"])
        cell_output += docutils.nodes.literal_block(
            text=content_str,
            rawsource=content_str,
            language="none",
            classes=["output", "stream"],
        )
        cell_node += cell_output
        return [cell_node]


class JupyterCellNode(docutils.nodes.container):
    """Inserted into doctree wherever a JupyterCell directive is encountered.

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


class MimeBundleNode(docutils.nodes.container):
    """A node with multiple representations rendering as the highest priority one."""

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", *children, mimetypes=attributes["mimetypes"])

    def render_as(self, visitor):
        """Determine which node to show based on the visitor."""
        try:
            # Or should we go to config via the node?
            priority = visitor.builder.env.app.config["render_priority_" + visitor.builder.format]
        except (AttributeError, KeyError):
            # Not sure what do to, act as a container and show everything just in case.
            return super()
        for mimetype in priority:
            try:
                return self.children[self.attributes["mimetypes"].index(mimetype)]
            except ValueError:
                pass
        # Same
        return super()

    def walk(self, visitor):
        return self.render_as(visitor).walk(visitor)

    def walkabout(self, visitor):
        return self.render_as(visitor).walkabout(visitor)


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
        return ipywidgets.embed.widget_view_template.format(view_spec=json.dumps(self["view_spec"]))


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
        # escape </script> to avoid early closing of the tag in the html page
        json_data = json.dumps(self["state"]).replace("</script>", r"<\/script>")

        # TODO: render into a separate file if 'html-manager' starts fully
        #       parsing script tags, and not just grabbing their innerHTML
        # https://github.com/jupyter-widgets/ipywidgets/blob/master/packages/html-manager/src/libembed.ts#L36
        return ipywidgets.embed.snippet_template.format(
            load="", widget_views="", json_data=json_data
        )


def cell_output_to_nodes(outputs, write_stderr, out_dir, thebe_config, inline=False):
    """Convert a jupyter cell with outputs and filenames to doctree nodes.

    Parameters
    ----------
    outputs : a list of outputs from a Jupyter cell
    write_stderr : bool
        If True include stderr in cell output
    out_dir : string
        Sphinx "absolute path" to the output folder, so it is a relative path
        to the source folder prefixed with ``/``.
    thebe_config: dict
        Thebelab configuration object or None
    inline: False
        Whether the nodes will be placed in-line with the text.

    Returns:
    -------
    to_add : list of docutils nodes
        Each output, converted into a docutils node.
    """
    # If we're in `inline` mode, ensure that we don't add block-level nodes
    literal_node = docutils.nodes.literal if inline else docutils.nodes.literal_block

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
                    # Not setting "rawsource" disables Pygment highlighting, which
                    # would otherwise add a <div class="highlight">.

                    literal = literal_node(
                        text=output["text"],
                        rawsource="",  # disables Pygment highlighting
                        language="none",
                        classes=["stderr"],
                    )
                    if inline:
                        # In this case, we don't wrap the text in containers
                        to_add.append(literal)
                    else:
                        container = docutils.nodes.container(classes=["stderr"])
                        container.append(literal)
                        to_add.append(container)
            else:
                to_add.append(
                    literal_node(
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
                literal_node(
                    text=text,
                    rawsource=text,
                    language="ipythontb",
                    classes=["output", "traceback"],
                )
            )
        elif output_type in ("display_data", "execute_result"):
            children_by_mimetype = {
                mime_type: output2sphinx(data, mime_type, output["metadata"], out_dir)
                for mime_type, data in output["data"].items()
            }
            # Filter out unknown mimetypes
            # TODO: rewrite this using walrus once we depend on Python 3.8
            children_by_mimetype = {
                mime_type: node
                for mime_type, node in children_by_mimetype.items()
                if node is not None
            }
            to_add.append(
                MimeBundleNode(
                    "",
                    *list(children_by_mimetype.values()),
                    mimetypes=list(children_by_mimetype.keys()),
                )
            )

    return to_add


def output2sphinx(data, mime_type, metadata, out_dir, inline=False):
    """Convert a Jupyter output with a specific mimetype to its sphinx representation."""
    # This only works lazily because the logger is inited by Sphinx
    from . import logger

    # If we're in `inline` mode, ensure that we don't add block-level nodes
    if inline:
        literal_node = docutils.nodes.literal
        math_node = docutils.nodes.math
    else:
        literal_node = docutils.nodes.literal_block
        math_node = math_block

    if mime_type == "text/html":
        return docutils.nodes.raw(text=data, format="html", classes=["output", "text_html"])
    elif mime_type == "text/plain":
        return literal_node(
            text=data,
            rawsource=data,
            language="none",
            classes=["output", "text_plain"],
        )
    elif mime_type == "text/latex":
        return math_node(
            text=strip_latex_delimiters(data),
            nowrap=False,
            number=None,
            classes=["output", "text_latex"],
        )
    elif mime_type == "application/javascript":
        return docutils.nodes.raw(
            text='<script type="{mime_type}">{data}</script>'.format(
                mime_type=mime_type, data=data
            ),
            format="html",
        )
    elif mime_type == WIDGET_VIEW_MIMETYPE:
        return JupyterWidgetViewNode(view_spec=data)
    elif mime_type.startswith("image"):
        file_path = Path(metadata["filenames"][mime_type])
        out_dir = Path(out_dir)
        # Sphinx treats absolute paths as being rooted at the source
        # directory, so make a relative path, which Sphinx treats
        # as being relative to the current working directory.
        filename = file_path.name

        if out_dir in file_path.parents:
            out_dir = file_path.parent

        uri = (out_dir / filename).as_posix()
        return docutils.nodes.image(uri=uri)
    else:
        logger.debug(f"Unknown mime type in cell output: {mime_type}")


def apply_styling(node, thebe_config):
    """Change the cell node appearance, according to its settings."""
    if not node.attributes["hide_code"]:  # only add css if code is displayed
        classes = node.attributes.get("classes", [])
        classes += ["jupyter_container"]

    (input_node, output_node) = node.children
    if thebe_config:
        # Move the source from the input node into the thebe_source node
        source = input_node.children.pop(0)
        thebe_source = ThebeSourceNode(
            hide_code=node.attributes["hide_code"],
            code_below=node.attributes["code_below"],
            language=node.attributes["cm_language"],
        )
        thebe_source.children = [source]
        input_node.children = [thebe_source]

        thebe_output = ThebeOutputNode()
        thebe_output.children = output_node.children
        output_node.children = [thebe_output]
    else:
        if node.attributes["hide_code"]:
            node.children.pop(0)

    if node.attributes["hide_output"]:
        output_node.children = []

    # Swap inputs and outputs if we want the code below
    if node.attributes["code_below"]:
        node.children = node.children[::-1]


class JupyterDownloadRole(ReferenceRole):
    def run(self):
        sep = ":" if ":" in self.name else "-"
        name, filetype = self.name.rsplit(sep, maxsplit=1)
        if sep == ":":
            warnings.warn(
                f"The {self.name} syntax is deprecated and "
                f"will be removed in 0.5.0, please use {name}-{filetype}",
                category=DeprecationWarning,
            )

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
        # Don't catch KeyError because it's a bug if 'widgets' does
        # not contain 'WIDGET_STATE_MIMETYPE'
        return None


class CombineCellInputOutput(SphinxTransform):
    """Merge nodes from CellOutput with the preceding CellInput node."""

    default_priority = 120

    def apply(self):
        moved_outputs = set()

        for cell_node in self.document.findall(JupyterCellNode):
            if not cell_node.attributes["execute"]:
                if not cell_node.attributes["hide_code"]:
                    # Cell came from jupyter-input
                    sibling = cell_node.next_node(descend=False, siblings=True)
                    if (
                        isinstance(sibling, JupyterCellNode)
                        and not sibling.attributes["execute"]
                        and sibling.attributes["hide_code"]
                    ):
                        # Sibling came from jupyter-output, so we merge
                        cell_node += sibling.children[1]
                        cell_node.attributes["hide_output"] = False
                        moved_outputs.update({sibling})
                else:
                    # Call came from jupyter-output
                    if cell_node not in moved_outputs:
                        raise ExtensionError(
                            "Found a jupyter-output node without a preceding jupyter-input"
                        )

        for output_node in moved_outputs:
            output_node.replace_self([])
