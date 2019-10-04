import tempfile
import shutil
import os
import sys
from io import StringIO

from sphinx.testing.util import SphinxTestApp, path
from sphinx.errors import ExtensionError
from docutils.nodes import raw

import pytest

from jupyter_sphinx.execute import (
    JupyterCellNode,
    JupyterKernelNode,
    JupyterWidgetViewNode,
    JupyterWidgetStateNode,
    ThebeSourceNode,
    ThebeOutputNode,
    ThebeButtonNode,
)

@pytest.fixture()
def doctree():
    source_trees = []
    apps = []
    syspath = sys.path[:]

    def doctree(source, config=None, return_warnings=False):
        src_dir = tempfile.mkdtemp()
        source_trees.append(src_dir)
        with open(os.path.join(src_dir, 'conf.py'), 'w') as f:
            f.write("extensions = ['jupyter_sphinx.execute']")
            if config is not None:
                f.write('\n' + config)
        with open(os.path.join(src_dir, 'contents.rst'), 'w') as f:
            f.write(source)
        warnings = StringIO()
        app = SphinxTestApp(srcdir=path(src_dir), status=StringIO(),
                            warning=warnings)
        apps.append(app)
        app.build()

        doctree = app.env.get_doctree("contents")

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
    source = '''
    .. jupyter-execute::

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['code_below'] is False
    assert cell.attributes['hide_code'] is False
    assert cell.attributes['hide_output'] is False
    assert cell.attributes['linenos'] is False
    assert cell.children[0].rawsource.strip() == "2 + 2"
    assert cell.children[1].rawsource.strip() == "4"


def test_hide_output(doctree):
    source = '''
    .. jupyter-execute::
        :hide-output:

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['hide_output'] is True
    assert len(cell.children) == 1
    assert cell.children[0].rawsource.strip() == "2 + 2"


def test_hide_code(doctree):
    source = '''
    .. jupyter-execute::
        :hide-code:

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['hide_code'] is True
    assert len(cell.children) == 1
    assert cell.children[0].rawsource.strip() == "4"


def test_code_below(doctree):
    source = '''
    .. jupyter-execute::
        :code-below:

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['code_below'] is True
    assert cell.children[0].rawsource.strip() == "4"
    assert cell.children[1].rawsource.strip() == "2 + 2"


def test_linenos(doctree):
    source = '''
    .. jupyter-execute::
        :linenos:

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['linenos'] is True
    assert len(cell.children) == 2
    assert cell.children[0].rawsource.strip() == "2 + 2"
    assert cell.children[1].rawsource.strip() == "4"
    source = '''
    .. jupyter-execute::
        :linenos:
        :code-below:

        2 + 2
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert len(cell.children) == 2
    assert cell.attributes['linenos'] is True


def test_continue_linenos(doctree):
    source = '''
    .. jupyter-execute::
        :linenos:

        2 + 2

    .. jupyter-execute::
        :continue_linenos:

        3 + 3
    '''
    tree = doctree(source)
    (cell0, cell1) = tree.traverse(JupyterCellNode)
    # :linenos:
    assert cell0.attributes['linenos']
    assert cell0.attributes['continue_linenos'] is False
    assert cell0.children[0].attributes['linenos']
    assert 'highlight_args' not in cell0.children[0].attributes
    assert cell0.children[0].rawsource.strip() == "2 + 2"
    assert cell0.children[1].rawsource.strip() == "4"
    # :continue_linenos:
    assert cell1.attributes['linenos'] is False
    assert cell1.attributes['continue_linenos']
    assert 'highlight_args' not in cell1.attributes
    assert cell1.children[0].attributes['linenos']
    assert cell1.children[0].attributes['highlight_args']['linenostart'] == 2
    assert cell1.children[0].rawsource.strip() == "3 + 3"
    assert cell1.children[1].rawsource.strip() == "6"

    source2 = '''
    .. jupyter-execute::
        :linenos:

        'cell0'  # will be line number 1

    .. jupyter-execute::
        :linenos:

        'cell1'  # should restart with line number 1

    .. jupyter-execute::
        :continue_linenos:

        'cell2'  # should be line number 2

    .. jupyter-execute::

        'cell3' # no line number directive

    .. jupyter-execute::
        :continue_linenos:

        'cell4' # should restart at line number 1

    .. jupyter-execute::
        :continue_linenos:

        'cell5' # should continue with line number 2
    '''
    tree2 = doctree(source2)
    cells = tree2.traverse(JupyterCellNode)
    assert len(cells) == 6
    (cell0, cell1, cell2, cell3, cell4, cell5) = cells
    # :linenos:
    assert cell0.children[0].attributes["linenos"]
    assert "highlight_args" not in cell0.children[0].attributes
    # :linenos:
    assert cell1.children[0].attributes["linenos"]
    assert "highlight_args" not in cell1.children[0].attributes
    # :continue_linenos:
    assert cell2.children[0].attributes["linenos"]
    assert cell2.children[0].attributes["highlight_args"]["linenostart"] == 2
    # (No line number directive)
    assert "linenos" not in cell3.children[0].attributes
    assert "highlight_args" not in cell3.children[0].attributes
    # :continue_linenos:
    assert cell4.children[0].attributes["linenos"]
    assert cell4.children[0].attributes["highlight_args"]["linenostart"] == 1
    # :continue_linenos:
    assert cell5.children[0].attributes["linenos"]
    assert cell5.children[0].attributes["highlight_args"]["linenostart"] == 2


def test_execution_environment_carries_over(doctree):
    source = '''
    .. jupyter-execute::

        a = 1

    .. jupyter-execute::

        a += 1
        a
    '''
    tree = doctree(source)
    cell0, cell1 = tree.traverse(JupyterCellNode)
    assert cell1.children[1].rawsource.strip() == "2"


def test_kernel_restart(doctree):
    source = '''
    .. jupyter-execute::

        a = 1

    .. jupyter-kernel::
        :id: new-kernel

    .. jupyter-execute::
        :raises:

        a += 1
        a
    '''
    tree = doctree(source)
    cell0, cell1 = tree.traverse(JupyterCellNode)
    assert 'NameError' in cell1.children[1].rawsource


def test_raises(doctree):
    source = '''
    .. jupyter-execute::

        raise ValueError()
    '''
    with pytest.raises(ExtensionError):
        doctree(source)

    source = '''
    .. jupyter-execute::
        :raises:

        raise ValueError()
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert 'ValueError' in cell.children[1].rawsource

    source = '''
    .. jupyter-execute::
        :raises: KeyError, ValueError

        raise ValueError()
    '''
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert 'ValueError' in cell.children[1].rawsource


def test_widgets(doctree):
    source = '''
    .. jupyter-execute::

        import ipywidgets
        ipywidgets.Button()
    '''
    tree = doctree(source)
    assert len(list(tree.traverse(JupyterWidgetViewNode))) == 1
    assert len(list(tree.traverse(JupyterWidgetStateNode))) == 1


def test_javascript(doctree):
    source = '''
    .. jupyter-execute::

        from IPython.display import display_javascript, Javascript
        Javascript('window.alert("Hello world!")')
    '''
    tree = doctree(source)
    node, = list(tree.traverse(raw))
    text, = node.children
    assert 'world' in text


def test_stdout(doctree):
    source = """
    .. jupyter-execute::

        print('hello world')
    """
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert len(cell.children) == 2
    assert cell.children[1].rawsource.strip() == "hello world"


def test_stderr(doctree):
    source = """
    .. jupyter-execute::

        import sys
        print('hello world', file=sys.stderr)
    """

    tree, warnings = doctree(source, return_warnings=True)
    assert "hello world" in warnings
    cell, = tree.traverse(JupyterCellNode)
    assert len(cell.children) == 1  # no output

    source = """
    .. jupyter-execute::
        :stderr:

        import sys
        print('hello world', file=sys.stderr)
    """
    tree = doctree(source)
    cell, = tree.traverse(JupyterCellNode)
    assert len(cell.children) == 2
    assert cell.children[1].rawsource.strip() == "hello world"


thebe_config = "jupyter_sphinx_thebelab_config = {\"dummy\": True}"


def test_thebe_hide_output(doctree):
    source = '''
    .. jupyter-execute::
        :hide-output:

        2 + 2
    '''
    tree = doctree(source, thebe_config)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['hide_output'] is True
    assert len(cell.children) == 1

    source = cell.children[0]
    assert type(source) == ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"


def test_thebe_hide_code(doctree):
    source = '''
    .. jupyter-execute::
        :hide-code:

        2 + 2
    '''
    tree = doctree(source, thebe_config)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['hide_code'] is True
    assert len(cell.children) == 2

    source = cell.children[0]
    assert type(source) == ThebeSourceNode
    assert source.attributes['hide_code'] is True
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"

    output = cell.children[1]
    assert type(output) == ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].rawsource.strip() == "4"


def test_thebe_code_below(doctree):
    source = '''
    .. jupyter-execute::
        :code-below:

        2 + 2
    '''
    tree = doctree(source, thebe_config)
    cell, = tree.traverse(JupyterCellNode)
    assert cell.attributes['code_below'] is True

    output = cell.children[0]
    assert type(output) is ThebeOutputNode
    assert len(output.children) == 1
    assert output.children[0].rawsource.strip() == "4"

    source = cell.children[1]
    assert type(source) is ThebeSourceNode
    assert len(source.children) == 1
    assert source.children[0].rawsource.strip() == "2 + 2"
    assert source.attributes['code_below'] is True


def test_thebe_button_auto(doctree):
    config = "jupyter_sphinx_thebelab_config = {\"dummy\": True}"
    source = """
    .. jupyter-execute::

        1 + 1
    """
    tree = doctree(source, config=config)
    assert len(tree.traverse(ThebeButtonNode)) == 1


def test_thebe_button_manual(doctree):
    config = "jupyter_sphinx_thebelab_config = {\"dummy\": True}"
    source = """
    .. jupyter-execute::

        1 + 1

    .. thebe-button::
    """
    tree = doctree(source, config)
    assert len(tree.traverse(ThebeButtonNode)) == 1


def test_thebe_button_none(doctree):
    config = "jupyter_sphinx_thebelab_config = {\"dummy\": True}"
    source = "No Jupyter cells"
    tree = doctree(source, config)
    assert len(tree.traverse(ThebeButtonNode)) == 0
