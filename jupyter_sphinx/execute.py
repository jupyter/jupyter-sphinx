"""Execution and managing kernels."""

import os
import warnings
from logging import Logger
from pathlib import Path

import nbconvert
from docutils.parsers.rst import Directive, directives
from nbconvert.preprocessors import ExtractOutputPreprocessor
from nbconvert.writers import FilesWriter
from sphinx.errors import ExtensionError
from sphinx.transforms import SphinxTransform

if nbconvert.version_info < (6,):
    from nbconvert.preprocessors.execute import executenb
else:
    from nbclient.client import execute as executenb

import traitlets

# Workaround of https://github.com/ipython/traitlets/issues/606
if traitlets.version_info < (5, 1):

    class LoggerAdapterWrapper(Logger):
        """Wrap a logger adapter, while pretending to be a logger."""

        def __init__(self, wrapped):
            self._wrapped = wrapped

        def __getattribute__(self, attr):
            if attr == "_wrapped":
                return object.__getattribute__(self, attr)
            return self._wrapped.__getattribute__(attr)

else:

    def LoggerAdapterWrapper(logger_adapter):
        return logger_adapter


import nbformat

import jupyter_sphinx as js

from .ast import (
    CellOutputNode,
    JupyterCellNode,
    JupyterKernelNode,
    JupyterWidgetStateNode,
    apply_styling,
    cell_output_to_nodes,
    get_widgets,
)
from .thebelab import ThebeButtonNode, add_thebelab_library
from .utils import (
    blank_nb,
    default_notebook_names,
    output_directory,
    sphinx_abs_dir,
    split_on,
)


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

    option_spec = {"id": directives.unchanged}

    def run(self):
        return [
            JupyterKernelNode(
                "",
                kernel_name=self.arguments[0].strip() if self.arguments else "",
                kernel_id=self.options.get("id", "").strip(),
            )
        ]


# Doctree transformations
class ExecuteJupyterCells(SphinxTransform):
    """Execute code cells in Jupyter kernels.

    Traverses the doctree to find JupyterKernel and JupyterCell nodes,
    then executes the code in the JupyterCell nodes in sequence, starting
    a new kernel every time a JupyterKernel node is encountered. The output
    from each code cell is inserted into the doctree.
    """

    # Beginning of main transforms. Not 100% sure it's the correct time.
    default_priority = 400

    def apply(self):
        doctree = self.document
        docname_path = Path(self.env.docname)
        doc_dir_relpath = docname_path.parent  # relative to src dir
        docname = docname_path.name
        default_kernel = self.config.jupyter_execute_default_kernel
        default_names = default_notebook_names(docname)
        thebe_config = self.config.jupyter_sphinx_thebelab_config
        linenos_config = self.config.jupyter_sphinx_linenos
        continue_linenos = self.config.jupyter_sphinx_continue_linenos
        # Check if we have anything to execute.
        if not doctree.traverse(JupyterCellNode):
            return

        if thebe_config:
            # Add the button at the bottom if it is not present
            if not doctree.traverse(ThebeButtonNode):
                doctree.append(ThebeButtonNode())

            add_thebelab_library(doctree, self.env)

        js.logger.info(f"executing {docname}")
        output_dir = Path(output_directory(self.env)) / doc_dir_relpath

        # Start new notebook whenever a JupyterKernelNode is encountered
        jupyter_nodes = (JupyterCellNode, JupyterKernelNode)
        nodes_by_notebook = split_on(
            lambda n: isinstance(n, JupyterKernelNode),
            doctree.traverse(lambda n: isinstance(n, jupyter_nodes)),
        )

        for first, *nodes in nodes_by_notebook:
            if isinstance(first, JupyterKernelNode):
                kernel_name = first["kernel_name"] or default_kernel
                file_name = first["kernel_id"] or next(default_names)
            else:
                nodes = (first, *nodes)
                kernel_name = default_kernel
                file_name = next(default_names)

            # Add empty placeholder cells for non-executed nodes so nodes
            # and cells can be zipped and the provided input/output
            # can be inserted later
            notebook = execute_cells(
                kernel_name,
                [
                    nbformat.v4.new_code_cell(node.astext() if node["execute"] else "")
                    for node in nodes
                ],
                self.config.jupyter_execute_kwargs,
            )

            # Raise error if cells raised exceptions and were not marked as doing so
            for node, cell in zip(nodes, notebook.cells):
                errors = [
                    output
                    for output in cell.outputs
                    if output["output_type"] == "error"
                ]
                allowed_errors = node.attributes.get("raises") or []
                raises_provided = node.attributes["raises"] is not None
                if (
                    raises_provided and not allowed_errors
                ):  # empty 'raises': suppress all errors
                    pass
                elif errors and not any(e["ename"] in allowed_errors for e in errors):
                    raise ExtensionError(
                        "Cell raised uncaught exception:\n{}".format(
                            "\n".join(errors[0]["traceback"])
                        )
                    )

            # Raise error if cells print to stderr
            for node, cell in zip(nodes, notebook.cells):
                stderr = [
                    output
                    for output in cell.outputs
                    if output["output_type"] == "stream" and output["name"] == "stderr"
                ]
                if stderr and not node.attributes["stderr"]:
                    js.logger.warning(
                        "Cell printed to stderr:\n{}".format(stderr[0]["text"])
                    )

            # Insert input/output into placeholders for non-executed cells
            for node, cell in zip(nodes, notebook.cells):
                if not node["execute"]:
                    cell.source = node.children[0].astext()
                    if len(node.children) == 2:
                        output = nbformat.v4.new_output("stream")
                        output.text = node.children[1].astext()
                        cell.outputs = [output]
                        node.children.pop()

            try:
                lexer = notebook.metadata.language_info.pygments_lexer
            except AttributeError:
                lexer = notebook.metadata.kernelspec.language

            # Highlight the code cells now that we know what language they are
            for node in nodes:
                source = node.children[0].children[0]
                source.attributes["language"] = lexer

            # Add line numbering

            linenostart = 1

            for node in nodes:
                # The literal_block node with the source
                source = node.children[0].children[0]
                nlines = source.rawsource.count("\n") + 1
                show_numbering = (
                    linenos_config or source["linenos"] or source["linenostart"]
                )

                if show_numbering:
                    source["linenos"] = True
                    if source["linenostart"]:
                        linenostart = source["linenostart"]
                    if source["linenostart"] or continue_linenos:
                        source["highlight_args"] = {"linenostart": linenostart}
                    else:
                        linenostart = 1
                    linenostart += nlines

                hl_lines = node["emphasize_lines"]
                if hl_lines:
                    highlight_args = source.setdefault("highlight_args", {})
                    highlight_args["hl_lines"] = hl_lines

            # Add code cell CSS class
            for node in nodes:
                source = node.children[0]
                source.attributes["classes"].append("code_cell")

            # Write certain cell outputs (e.g. images) to separate files, and
            # modify the metadata of the associated cells in 'notebook' to
            # include the path to the output file.
            write_notebook_output(
                notebook, str(output_dir), file_name, self.env.docname
            )

            try:
                cm_language = notebook.metadata.language_info.codemirror_mode.name
            except AttributeError:
                cm_language = notebook.metadata.kernelspec.language
            for node in nodes:
                node.attributes["cm_language"] = cm_language

            # Add doctree nodes for cell outputs.
            for node, cell in zip(nodes, notebook.cells):
                # Add the outputs as children
                output = CellOutputNode(classes=["cell_output"])
                output.children = cell_output_to_nodes(
                    cell.outputs,
                    bool(node.attributes["stderr"]),
                    sphinx_abs_dir(self.env),
                    thebe_config,
                )
                node += output

                apply_styling(node, thebe_config)

            if contains_widgets(notebook):
                doctree.append(JupyterWidgetStateNode(state=get_widgets(notebook)))


# Roles


def execute_cells(kernel_name, cells, execute_kwargs):
    """Execute Jupyter cells in the specified kernel and return the notebook."""
    notebook = blank_nb(kernel_name)
    notebook.cells = cells
    # Modifies 'notebook' in-place
    try:
        executenb(notebook, **execute_kwargs)
    except Exception as e:
        raise ExtensionError("Notebook execution failed", orig_exc=e)

    return notebook


def write_notebook_output(notebook, output_dir, notebook_name, location=None):
    """Extract output from notebook cells and write to files in output_dir.

    This also modifies 'notebook' in-place, adding metadata to each cell that
    maps output mime-types to the filenames the output was saved under.
    """
    resources = dict(unique_key=os.path.join(output_dir, notebook_name), outputs={})

    # Modifies 'resources' in-place
    ExtractOutputPreprocessor().preprocess(notebook, resources)
    # Write the cell outputs to files where we can (images and PDFs),
    # as well as the notebook file.
    FilesWriter(build_directory=output_dir).write(
        nbformat.writes(notebook),
        resources,
        os.path.join(output_dir, notebook_name + ".ipynb"),
    )

    exporter = nbconvert.exporters.ScriptExporter(log=LoggerAdapterWrapper(js.logger))
    with warnings.catch_warnings():
        # See https://github.com/jupyter/nbconvert/issues/1388
        warnings.simplefilter("ignore", DeprecationWarning)
        contents, resources = exporter.from_notebook_node(notebook)

    notebook_file = notebook_name + resources["output_extension"]
    output_dir = Path(output_dir)
    # utf-8 is the de-facto standard encoding for notebooks.
    (output_dir / notebook_file).write_text(contents, encoding="utf8")


def contains_widgets(notebook):
    widgets = get_widgets(notebook)
    return widgets and widgets["state"]
