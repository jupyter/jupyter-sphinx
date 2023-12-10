import asyncio
import os
import shutil
import sys
import tempfile
import warnings
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from docutils.nodes import container, image, literal, literal_block, math_block, raw
from nbformat import from_dict
from sphinx.addnodes import download_reference
from sphinx.errors import ExtensionError
from sphinx.testing.util import SphinxTestApp, assert_node

try:
    from sphinx.testing.util import path
except ImportError:
    path = None


from jupyter_sphinx.ast import (
    JupyterCellNode,
    JupyterDownloadRole,
    JupyterWidgetStateNode,
    JupyterWidgetViewNode,
    cell_output_to_nodes,
)
from jupyter_sphinx.thebelab import ThebeButtonNode, ThebeOutputNode, ThebeSourceNode


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture()
def doctree():
    source_trees = []
    apps = []
    syspath = sys.path[:]

    def doctree(
        source,
        config=None,
        return_all=False,
        entrypoint="jupyter_sphinx",
        buildername="html",
    ):
        src_dir = Path(tempfile.mkdtemp())
        source_trees.append(src_dir)

        conf_contents = "extensions = ['%s']" % entrypoint
        if config is not None:
            conf_contents += "\n" + config
        (src_dir / "conf.py").write_text(conf_contents, encoding="utf8")
        (src_dir / "index.rst").write_text(source, encoding="utf8")

        warnings = StringIO()
        if path is not None:
            src_dir = path(src_dir.as_posix())
        app = SphinxTestApp(
            srcdir=src_dir,
            status=StringIO(),
            warning=warnings,
            buildername=buildername,
        )
        apps.append(app)
        app.build()

        doctree = app.env.get_and_resolve_doctree("index", app.builder)
        if return_all:
            return doctree, app, warnings.getvalue()
        else:
            return doctree

    yield doctree

    sys.path[:] = syspath
    for app in reversed(apps):
        app.cleanup()
    for tree in source_trees:
        shutil.rmtree(tree)


@pytest.mark.parametrize("buildername", ["html", "singlehtml"])
def test_basic(doctree, buildername):
    source = """
    .. jupyter-execute::

        2 + 2
    """
    tree = doctree(source, buildername=buildername)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert not cell.attributes["code_below"]
    assert not cell.attributes["hide_code"]
    assert not cell.attributes["hide_output"]
    assert not cellinput.children[0]["linenos"]
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert celloutput.children[0].astext().strip() == "4"


def test_hide_output(doctree):
    source = """
    .. jupyter-execute::
        :hide-output:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_output"]
    assert len(celloutput.children) == 0
    assert cellinput.children[0].astext().strip() == "2 + 2"


def test_hide_code(doctree):
    source = """
    .. jupyter-execute::
        :hide-code:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (celloutput,) = cell.children
    assert cell.attributes["hide_code"]
    assert len(cell.children) == 1
    assert celloutput.children[0].astext().strip() == "4"


def test_code_below(doctree):
    source = """
    .. jupyter-execute::
        :code-below:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (celloutput, cellinput) = cell.children
    assert cell.attributes["code_below"]
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert celloutput.children[0].astext().strip() == "4"


def test_linenos(doctree):
    source = """
    .. jupyter-execute::
        :linenos:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cellinput.children[0]["linenos"]
    assert len(cell.children) == 2
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert celloutput.children[0].astext().strip() == "4"
    source = """
    .. jupyter-execute::
        :linenos:
        :code-below:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (celloutput, cellinput) = cell.children
    assert cellinput.children[0]["linenos"]


def test_linenos_conf_option(doctree):
    source = """
    .. jupyter-execute::

        2 + 2
    """
    tree = doctree(source, config="jupyter_sphinx_linenos = True")
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cellinput.children[0].attributes["linenos"]
    assert "highlight_args" not in cellinput.children[0].attributes
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert celloutput.children[0].astext().strip() == "4"


def test_continue_linenos_conf_option(doctree):
    # Test no linenumbering without linenos config or lineno-start directive
    source = """
    .. jupyter-execute::

        2 + 2

    """

    tree = doctree(source, config="jupyter_sphinx_continue_linenos = True")
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert not cellinput.children[0].attributes["linenos"]
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert celloutput.children[0].astext().strip() == "4"

    # Test continuous line numbering
    source = """
    .. jupyter-execute::

        2 + 2

    .. jupyter-execute::

        3 + 3

    """

    tree = doctree(
        source,
        config="jupyter_sphinx_linenos = True\n"
        "jupyter_sphinx_continue_linenos = True",
    )

    cell0, cell1 = tree.findall(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert cellinput0.children[0].attributes["linenos"]
    assert cellinput0.children[0].astext().strip() == "2 + 2"
    assert celloutput0.children[0].astext().strip() == "4"

    assert cellinput1.children[0].attributes["linenos"]
    assert cellinput1.children[0].attributes["highlight_args"]["linenostart"] == 2
    assert cellinput1.children[0].astext().strip() == "3 + 3"
    assert celloutput1.children[0].astext().strip() == "6"

    # Line number should continue after lineno-start option

    source = """
    .. jupyter-execute::
       :lineno-start: 7

        2 + 2

    .. jupyter-execute::

        3 + 3

    """
    tree = doctree(
        source,
        config="jupyter_sphinx_linenos = True\n"
        "jupyter_sphinx_continue_linenos = True",
    )
    cell0, cell1 = tree.findall(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert cellinput0.children[0].attributes["highlight_args"]["linenostart"] == 7
    assert cellinput0.children[0].astext().strip() == "2 + 2"
    assert celloutput0.children[0].astext().strip() == "4"

    assert cellinput1.children[0].attributes["linenos"]
    assert cellinput1.children[0].attributes["highlight_args"]["linenostart"] == 8
    assert cellinput1.children[0].astext().strip() == "3 + 3"
    assert celloutput1.children[0].astext().strip() == "6"


def test_emphasize_lines(doctree):
    source = """
    .. jupyter-execute::
        :emphasize-lines: 1,3-5

        1 + 1
        2 + 2
        3 + 3
        4 + 4
        5 + 5

    .. jupyter-execute::
        :emphasize-lines: 2, 4

        1 + 1
        2 + 2
        3 + 3
        4 + 4
        5 + 5
    """
    tree = doctree(source)
    cell0, cell1 = tree.findall(JupyterCellNode)

    assert cell0.attributes["emphasize_lines"] == [1, 3, 4, 5]
    assert cell1.attributes["emphasize_lines"] == [2, 4]


def test_execution_environment_carries_over(doctree):
    source = """
    .. jupyter-execute::

        a = 1

    .. jupyter-execute::

        a += 1
        a
    """
    tree = doctree(source)
    _, cell1 = tree.findall(JupyterCellNode)
    (_, celloutput1) = cell1.children
    assert celloutput1.children[0].astext().strip() == "2"


def test_kernel_restart(doctree):
    source = """
    .. jupyter-execute::

        a = 1

    .. jupyter-kernel::
        :id: new-kernel

    .. jupyter-execute::
        :raises:

        a += 1
        a
    """
    tree = doctree(source)
    _, cell1 = tree.findall(JupyterCellNode)
    (_, celloutput1) = cell1.children
    assert "NameError" in celloutput1.children[0].astext()


def test_raises(doctree):
    source = """
    .. jupyter-execute::

        raise ValueError()
    """
    with pytest.raises(ExtensionError):
        doctree(source)

    source = """
    .. jupyter-execute::
        :raises:

        raise ValueError()
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (_, celloutput) = cell.children
    assert "ValueError" in celloutput.children[0].astext()

    source = """
    .. jupyter-execute::
        :raises: KeyError, ValueError

        raise ValueError()
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (_, celloutput) = cell.children
    assert "ValueError" in celloutput.children[0].astext()


def test_widgets(doctree):
    source = """
    .. jupyter-execute::

        import ipywidgets
        ipywidgets.Button()
    """
    tree = doctree(source)
    assert len(list(tree.findall(JupyterWidgetViewNode))) == 1
    assert len(list(tree.findall(JupyterWidgetStateNode))) == 1


def test_javascript(doctree):
    source = """
    .. jupyter-execute::

        from IPython.display import display_javascript, Javascript
        Javascript('window.alert("Hello world!")')
    """
    tree = doctree(source)
    (node,) = list(tree.findall(raw))
    (text,) = node.children
    assert "world" in text


def test_stdout(doctree):
    source = """
    .. jupyter-execute::

        print('hello world')
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (_, celloutput) = cell.children
    assert len(cell.children) == 2
    assert celloutput.children[0].astext().strip() == "hello world"


def test_stderr(doctree):
    source = """
    .. jupyter-execute::

        import sys
        print('hello world', file=sys.stderr)
    """

    tree, _, warnings = doctree(source, return_all=True)
    assert "hello world" in warnings
    (cell,) = tree.findall(JupyterCellNode)
    (_, celloutput) = cell.children
    assert len(celloutput) == 0  # no output

    source = """
    .. jupyter-execute::
        :stderr:

        import sys
        print('hello world', file=sys.stderr)
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (_, celloutput) = cell.children
    assert len(cell.children) == 2
    assert "stderr" in celloutput.children[0].attributes["classes"]
    assert celloutput.children[0].astext().strip() == "hello world"


thebe_config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'


def test_thebe_hide_output(doctree):
    source = """
    .. jupyter-execute::
        :hide-output:

        2 + 2
    """
    tree = doctree(source, thebe_config)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_output"]
    assert len(celloutput.children) == 0

    source = cellinput.children[0]
    assert type(source) == ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].astext().strip() == "2 + 2"


def test_thebe_hide_code(doctree):
    source = """
    .. jupyter-execute::
        :hide-code:

        2 + 2
    """
    tree = doctree(source, thebe_config)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_code"]
    assert len(cell.children) == 2

    source = cellinput.children[0]
    assert type(source) == ThebeSourceNode
    assert source.attributes["hide_code"]
    assert len(source.children) == 1
    assert source.children[0].astext().strip() == "2 + 2"

    output = celloutput.children[0]
    assert type(output) == ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].astext().strip() == "4"


def test_thebe_code_below(doctree):
    source = """
    .. jupyter-execute::
        :code-below:

        2 + 2
    """
    tree = doctree(source, thebe_config)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["code_below"]

    output = cellinput.children[0]
    assert type(output) is ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].astext().strip() == "4"

    source = celloutput.children[0]
    assert type(source) is ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].astext().strip() == "2 + 2"
    assert source.attributes["code_below"]


def test_thebe_button_auto(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = """
    .. jupyter-execute::

        1 + 1
    """
    tree = doctree(source, config=config)
    assert len(list(tree.findall(ThebeButtonNode))) == 1


def test_thebe_button_manual(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = """
    .. jupyter-execute::

        1 + 1

    .. thebe-button::
    """
    tree = doctree(source, config)
    assert len(list(tree.findall(ThebeButtonNode))) == 1


def test_thebe_button_none(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = "No Jupyter cells"
    tree = doctree(source, config)
    assert len(list(tree.findall(ThebeButtonNode))) == 0


def test_latex(doctree):
    source = r"""
    .. jupyter-execute::

        from IPython.display import Latex
        Latex(r"{}\int{}")
    """

    delimiter_pairs = (pair.split() for pair in r"\( \),\[ \],$$ $$,$ $".split(","))

    for start, end in delimiter_pairs:
        tree = doctree(source.format(start, end))
        (cell,) = tree.findall(JupyterCellNode)
        (_, celloutput) = cell.children
        assert next(iter(celloutput.findall(math_block))).astext() == r"\int"


def test_cell_output_to_nodes(doctree):
    # tests the image uri paths on conversion to docutils image nodes
    output_dir = "/_build/jupyter_execute"
    img_locs = [
        "/_build/jupyter_execute/docs/image_1.png",
        "/_build/jupyter_execute/image_2.png",
    ]

    cells = [
        {
            "outputs": [
                {
                    "data": {
                        "image/png": "Vxb6L1wAAAABJRU5ErkJggg==\n",
                        "text/plain": "<Figure size 432x288 with 1 Axes>",
                    },
                    "metadata": {"filenames": {"image/png": img_locs[0]}},
                    "output_type": "display_data",
                }
            ]
        },
        {
            "outputs": [
                {
                    "data": {
                        "image/png": "iVBOJggg==\n",
                        "text/plain": "<Figure size 432x288 with 1 Axes>",
                    },
                    "metadata": {"filenames": {"image/png": img_locs[1]}},
                    "output_type": "display_data",
                }
            ]
        },
    ]

    for index, cell in enumerate(cells):
        cell = from_dict(cell)
        (output_node,) = cell_output_to_nodes(cell["outputs"], True, output_dir, None)
        (image_node,) = output_node.findall(image)
        assert image_node.attributes["uri"] == img_locs[index]

    # Testing inline functionality
    outputs = [
        {"name": "stdout", "output_type": "stream", "text": ["hi\n"]},
        {"name": "stderr", "output_type": "stream", "text": ["hi\n"]},
    ]
    output_nodes = cell_output_to_nodes(outputs, True, output_dir, None)
    for output, kind in zip(output_nodes, [literal_block, container]):
        assert isinstance(output, kind)

    output_nodes = cell_output_to_nodes(outputs, True, output_dir, None, inline=True)
    for output, kind in zip(output_nodes, [literal, literal]):
        assert isinstance(output, kind)


@pytest.mark.parametrize(
    "text,reftarget,caption",
    (
        ("nb_name", "/../jupyter_execute/path/to/nb_name.ipynb", "nb_name.ipynb"),
        ("../nb_name", "/../jupyter_execute/path/nb_name.ipynb", "../nb_name.ipynb"),
        ("text <nb_name>", "/../jupyter_execute/path/to/nb_name.ipynb", "text"),
    ),
)
def test_download_role(text, reftarget, caption, tmp_path):
    role = JupyterDownloadRole()
    mock_inliner = Mock()
    config = {
        "document.settings.env.app.outdir": str(tmp_path),
        "document.settings.env.docname": "path/to/docname",
        "document.settings.env.srcdir": str(tmp_path),
        "document.settings.env.app.srcdir": str(tmp_path),
        "reporter.get_source_and_line": lambda line: ("source", line),
    }
    mock_inliner.configure_mock(**config)
    ret, msg = role("jupyter-download-notebook", text, text, 0, mock_inliner)

    if os.name == "nt":
        # Get equivalent abs path for Windows
        reftarget = (Path(tmp_path) / reftarget[1:]).resolve().as_posix()

    assert_node(ret[0], [download_reference], reftarget=reftarget)
    assert_node(ret[0][0], [literal, caption])
    assert msg == []


def test_save_script(doctree):
    source = """
    .. jupyter-kernel:: python3
      :id: test

    .. jupyter-execute::

      a = 1
      print(a)
    """
    _, app, _ = doctree(source, return_all=True)
    outdir = Path(app.outdir)
    saved_text = (outdir / "../jupyter_execute/test.py").read_text()
    assert saved_text.startswith("#!/usr/bin/env python")
    assert "print(a)" in saved_text


def test_bash_kernel(doctree):
    pytest.importorskip("bash_kernel")
    if sys.platform == "win32":
        pytest.skip("Not trying bash on windows.")

    # we set enable-bracketed-paste off
    # to avoid bash_kernel accidentally raising errors
    # (related to https://github.com/takluyver/bash_kernel/issues/107)
    source = """
    .. jupyter-kernel:: bash
      :id: test

    .. jupyter-execute::

      bind 'set enable-bracketed-paste off'
      echo "foo"
    """
    with warnings.catch_warnings():
        # See https://github.com/takluyver/bash_kernel/issues/105
        warnings.simplefilter("ignore", DeprecationWarning)
        _, app, _ = doctree(source, return_all=True)

    outdir = Path(app.outdir)
    saved_text = (outdir / "../jupyter_execute/test.sh").read_text()
    assert 'echo "foo"' in saved_text


def test_input_cell(doctree):
    source = """
    .. jupyter-input::

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, empty) = cell.children
    assert cell.attributes["hide_output"] is True
    assert cellinput.children[0].attributes["linenos"] is False
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert len(empty.children) == 0


def test_input_cell_linenos(doctree):
    source = """
    .. jupyter-input::
        :linenos:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (cellinput, empty) = cell.children
    assert cell.attributes["hide_output"] is True
    assert cellinput.children[0].attributes["linenos"] is True
    assert cellinput.children[0].astext().strip() == "2 + 2"
    assert len(empty.children) == 0


def test_output_cell(doctree):
    source = """
    .. jupyter-input::

        3 + 2

    .. jupyter-output::

        4
    """
    tree = doctree(source)
    (cell,) = tree.findall(JupyterCellNode)
    (
        cellinput,
        celloutput,
    ) = cell.children
    assert cellinput.children[0].astext().strip() == "3 + 2"
    assert celloutput.children[0].astext().strip() == "4"


def test_output_only_error(doctree):
    source = """
    .. jupyter-output::

        4
    """
    with pytest.raises(ExtensionError):
        doctree(source)


def test_multiple_directives(doctree):
    source = """
    .. jupyter-execute::

        2 + 2

    .. jupyter-input::

        3 + 3

    .. jupyter-output::

        5
    """
    tree = doctree(source)
    (ex, jin) = tree.findall(JupyterCellNode)
    (ex_in, ex_out) = ex.children
    (jin_in, jin_out) = jin.children
    assert ex_in.children[0].astext().strip() == "2 + 2"
    assert ex_out.children[0].astext().strip() == "4"
    assert jin_in.children[0].astext().strip() == "3 + 3"
    assert jin_out.children[0].astext().strip() == "5"


def test_builder_priority(doctree):
    source = """
    .. jupyter-execute::

        display({"text/plain": "I am html output", "text/latex": "I am latex"})
    """
    config = (
        "render_priority_html = ['text/plain', 'text/latex']\n"
        "render_priority_latex = ['text/latex', 'text/plain']"
    )
    _, app, _ = doctree(source, config=config, return_all=True, buildername="html")
    html = (Path(app.outdir) / "index.html").read_text()
    assert "I am html output" in html
    _, app, _ = doctree(source, config=config, return_all=True, buildername="latex")
    latex = (Path(app.outdir) / "python.tex").read_text()
    assert "I am latex" in latex
