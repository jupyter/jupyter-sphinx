import tempfile
import shutil
import os
import sys
from io import StringIO
from unittest.mock import Mock
from pathlib import Path

from sphinx.addnodes import download_reference
from sphinx.testing.util import assert_node, SphinxTestApp, path
from sphinx.errors import ExtensionError
from docutils.nodes import literal, raw
from nbformat import from_dict

import pytest

from jupyter_sphinx.ast import (
    JupyterCellNode,
    CellInputNode,
    CellOutputNode,
    JupyterWidgetViewNode,
    JupyterWidgetStateNode,
    cell_output_to_nodes,
    JupyterDownloadRole,
)
from jupyter_sphinx.thebelab import ThebeSourceNode, ThebeOutputNode, ThebeButtonNode


@pytest.fixture()
def doctree():
    source_trees = []
    apps = []
    syspath = sys.path[:]

    def doctree(
        source, config=None, return_warnings=False, entrypoint="jupyter_sphinx"
    ):
        src_dir = Path(tempfile.mkdtemp())
        source_trees.append(src_dir.as_posix())

        conf_contents = "extensions = ['%s']" % entrypoint
        if config is not None:
            conf_contents += "\n" + config
        (src_dir / "conf.py").write_text(conf_contents, encoding = "utf8")
        (src_dir / "contents.rst").write_text(source, encoding = "utf8")
        
        warnings = StringIO()
        app = SphinxTestApp(srcdir=path(src_dir.as_posix()), status=StringIO(), warning=warnings)
        apps.append(app)
        app.build()

        doctree = app.env.get_and_resolve_doctree("contents", app.builder)

        if return_warnings:
            return doctree, warnings.getvalue()
        else:
            return doctree

    yield doctree

    sys.path[:] = syspath
    for app in reversed(apps):
        app.cleanup()
    for tree in source_trees:
        shutil.rmtree(tree)


def test_basic(doctree):
    source = """
    .. jupyter-execute::

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["code_below"] is False
    assert cell.attributes["hide_code"] is False
    assert cell.attributes["hide_output"] is False
    assert cell.attributes["linenos"] is False
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"


def test_basic_old_entrypoint(doctree):
    source = """
    .. jupyter-execute::

        2 + 2
    """
    tree = doctree(source, entrypoint="jupyter_sphinx.execute")
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["code_below"] is False
    assert cell.attributes["hide_code"] is False
    assert cell.attributes["hide_output"] is False
    assert cell.attributes["linenos"] is False
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"


def test_hide_output(doctree):
    source = """
    .. jupyter-execute::
        :hide-output:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_output"] is True
    assert len(celloutput.children) == 0
    assert cellinput.children[0].rawsource.strip() == "2 + 2"


def test_hide_code(doctree):
    source = """
    .. jupyter-execute::
        :hide-code:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (celloutput,) = cell.children
    assert cell.attributes["hide_code"] is True
    assert len(cell.children) == 1
    assert celloutput.children[0].rawsource.strip() == "4"


def test_code_below(doctree):
    source = """
    .. jupyter-execute::
        :code-below:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (celloutput, cellinput) = cell.children
    assert cell.attributes["code_below"] is True
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"


def test_linenos(doctree):
    source = """
    .. jupyter-execute::
        :linenos:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["linenos"] is True
    assert len(cell.children) == 2
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"
    source = """
    .. jupyter-execute::
        :linenos:
        :code-below:

        2 + 2
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert len(cell.children) == 2
    assert cell.attributes["linenos"] is True


def test_linenos_conf_option(doctree):
    source = """
    .. jupyter-execute::

        2 + 2
    """
    tree = doctree(source, config="jupyter_sphinx_linenos = True")
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cellinput.attributes["linenos"]
    assert "highlight_args" not in cellinput.attributes
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"


def test_continue_linenos_conf_option(doctree):
    # Test no linenumbering without linenos config or lineno-start directive
    source = """
    .. jupyter-execute::

        2 + 2

    """

    tree = doctree(source, config="jupyter_sphinx_continue_linenos = True")
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert "linenos" not in cellinput.attributes
    assert cellinput.children[0].rawsource.strip() == "2 + 2"
    assert celloutput.children[0].rawsource.strip() == "4"

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

    cell0, cell1 = tree.traverse(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert cellinput0.attributes["linenos"]
    assert cellinput0.children[0].rawsource.strip() == "2 + 2"
    assert celloutput0.children[0].rawsource.strip() == "4"

    assert cellinput1.attributes["linenos"]
    assert cellinput1.attributes["highlight_args"]["linenostart"] == 2
    assert cellinput1.children[0].rawsource.strip() == "3 + 3"
    assert celloutput1.children[0].rawsource.strip() == "6"

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
    cell0, cell1 = tree.traverse(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert cellinput0.attributes["highlight_args"]["linenostart"] == 7
    assert cellinput0.children[0].rawsource.strip() == "2 + 2"
    assert celloutput0.children[0].rawsource.strip() == "4"

    assert cellinput1.attributes["linenos"]
    assert cellinput1.attributes["highlight_args"]["linenostart"] == 8
    assert cellinput1.children[0].rawsource.strip() == "3 + 3"
    assert celloutput1.children[0].rawsource.strip() == "6"


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
    cell0, cell1 = tree.traverse(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children

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
    cell0, cell1 = tree.traverse(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert celloutput1.children[0].rawsource.strip() == "2"


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
    cell0, cell1 = tree.traverse(JupyterCellNode)
    (cellinput0, celloutput0) = cell0.children
    (cellinput1, celloutput1) = cell1.children
    assert "NameError" in celloutput1.children[0].rawsource


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
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert "ValueError" in celloutput.children[0].rawsource

    source = """
    .. jupyter-execute::
        :raises: KeyError, ValueError

        raise ValueError()
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert "ValueError" in celloutput.children[0].rawsource


def test_widgets(doctree):
    source = """
    .. jupyter-execute::

        import ipywidgets
        ipywidgets.Button()
    """
    tree = doctree(source)
    assert len(list(tree.traverse(JupyterWidgetViewNode))) == 1
    assert len(list(tree.traverse(JupyterWidgetStateNode))) == 1


def test_javascript(doctree):
    source = """
    .. jupyter-execute::

        from IPython.display import display_javascript, Javascript
        Javascript('window.alert("Hello world!")')
    """
    tree = doctree(source)
    (node,) = list(tree.traverse(raw))
    (text,) = node.children
    assert "world" in text


def test_stdout(doctree):
    source = """
    .. jupyter-execute::

        print('hello world')
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert len(cell.children) == 2
    assert celloutput.children[0].rawsource.strip() == "hello world"


def test_stderr(doctree):
    source = """
    .. jupyter-execute::

        import sys
        print('hello world', file=sys.stderr)
    """

    tree, warnings = doctree(source, return_warnings=True)
    assert "hello world" in warnings
    (cell,) = tree.traverse(JupyterCellNode)
    (_, celloutput) = cell.children
    assert len(celloutput) == 0  # no output

    source = """
    .. jupyter-execute::
        :stderr:

        import sys
        print('hello world', file=sys.stderr)
    """
    tree = doctree(source)
    (cell,) = tree.traverse(JupyterCellNode)
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
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_output"] is True
    assert len(celloutput.children) == 0

    source = cellinput.children[0]
    assert type(source) == ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"


def test_thebe_hide_code(doctree):
    source = """
    .. jupyter-execute::
        :hide-code:

        2 + 2
    """
    tree = doctree(source, thebe_config)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["hide_code"] is True
    assert len(cell.children) == 2

    source = cellinput.children[0]
    assert type(source) == ThebeSourceNode
    assert source.attributes["hide_code"] is True
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"

    output = celloutput.children[0]
    assert type(output) == ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].rawsource.strip() == "4"


def test_thebe_code_below(doctree):
    source = """
    .. jupyter-execute::
        :code-below:

        2 + 2
    """
    tree = doctree(source, thebe_config)
    (cell,) = tree.traverse(JupyterCellNode)
    (cellinput, celloutput) = cell.children
    assert cell.attributes["code_below"] is True

    output = cellinput.children[0]
    assert type(output) is ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].rawsource.strip() == "4"

    source = celloutput.children[0]
    assert type(source) is ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"
    assert source.attributes["code_below"] is True


def test_thebe_button_auto(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = """
    .. jupyter-execute::

        1 + 1
    """
    tree = doctree(source, config=config)
    assert len(tree.traverse(ThebeButtonNode)) == 1


def test_thebe_button_manual(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = """
    .. jupyter-execute::

        1 + 1

    .. thebe-button::
    """
    tree = doctree(source, config)
    assert len(tree.traverse(ThebeButtonNode)) == 1


def test_thebe_button_none(doctree):
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'
    source = "No Jupyter cells"
    tree = doctree(source, config)
    assert len(tree.traverse(ThebeButtonNode)) == 0


def test_latex(doctree):
    source = r"""
    .. jupyter-execute::

        from IPython.display import Latex
        Latex(r"{}\int{}")
    """

    delimiter_pairs = (pair.split() for pair in r"\( \),\[ \],$$ $$,$ $".split(","))

    for start, end in delimiter_pairs:
        tree = doctree(source.format(start, end))
        (cell,) = tree.traverse(JupyterCellNode)
        (cellinput, celloutput) = cell.children
        assert celloutput.children[0].astext() == r"\int"


def test_image_mimetype_uri(doctree):
    # tests the image uri paths on conversion to docutils image nodes
    priority =  ['image/png', 'image/jpeg', 'text/latex', 'text/plain']
    output_dir = '/_build/jupyter_execute'
    img_locs = ['/_build/jupyter_execute/docs/image_1.png','/_build/jupyter_execute/image_2.png']

    cells = [
        {'outputs':
            [{'data': {'image/png': 'Vxb6L1wAAAABJRU5ErkJggg==\n', 'text/plain': '<Figure size 432x288 with 1 Axes>'}, 'metadata': {'filenames': {'image/png': img_locs[0]}}, 'output_type': 'display_data'}]
        },
        {'outputs':
            [{'data': {'image/png': 'iVBOJggg==\n', 'text/plain': '<Figure size 432x288 with 1 Axes>'}, 'metadata': {'filenames': {'image/png': img_locs[1]}}, 'output_type': 'display_data'}]
        }]

    for index, cell in enumerate(cells):
        cell = from_dict(cell)
        output_node = cell_output_to_nodes(cell["outputs"], priority, True, output_dir, None)
        assert output_node[0].attributes['uri'] == img_locs[index]


@pytest.mark.parametrize('text,reftarget,caption', (
    ('nb_name', '/../jupyter_execute/path/to/nb_name.ipynb', 'nb_name.ipynb'),
    ('../nb_name', '/../jupyter_execute/path/nb_name.ipynb', '../nb_name.ipynb'),
    ('text <nb_name>', '/../jupyter_execute/path/to/nb_name.ipynb', 'text'),
))
def test_download_role(text, reftarget, caption, tmp_path):
    role = JupyterDownloadRole()
    mock_inliner = Mock()
    config = {
        'document.settings.env.app.outdir': str(tmp_path),
        'document.settings.env.docname': 'path/to/docname',
        'document.settings.env.srcdir': str(tmp_path),
        'document.settings.env.app.srcdir': str(tmp_path),
        'reporter.get_source_and_line': lambda l: ('source', l)
    }
    mock_inliner.configure_mock(**config)
    ret, msg = role('jupyter-download:notebook', text, text, 0, mock_inliner)

    if os.name == "nt":
        # Get equivalent abs path for Windows
        reftarget = (Path(tmp_path) / reftarget[1:]).resolve().as_posix()

    assert_node(ret[0], [download_reference], reftarget=reftarget)
    assert_node(ret[0][0], [literal, caption])
    assert msg == []
