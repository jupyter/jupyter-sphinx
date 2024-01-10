import json
import os
import re
import warnings

import pytest
from sphinx.errors import ExtensionError


@pytest.mark.parametrize("buildername", ["html", "singlehtml"])
def test_basic(sphinx_build_factory, directive, file_regression, buildername):
    source = directive("execute", ["2 + 2"])

    sphinx_build = sphinx_build_factory(source, buildername=buildername).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_hide_output(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["hide-output"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_hide_code(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["hide-code"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_code_below(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["code-below"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_linenos(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["linenos"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_linenos_code_below(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["linenos", "code-below"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_linenos_conf_option(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"])
    config = "jupyter_sphinx_linenos = True"

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_continue_linenos_not_automatic(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"])
    config = "jupyter_sphinx_continue_linenos = True"

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_continue_lineos_conf_option(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"])
    source += "\n" + directive("execute", ["3 + 3"])

    config = "jupyter_sphinx_linenos = True"
    config += "\n" + "jupyter_sphinx_continue_linenos = True"

    sphinx_build = sphinx_build_factory(source, config=config).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_continue_linenos_with_start(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], [("lineno-start", "7")])
    source += "\n" + directive("execute", ["3 + 3"])

    config = "jupyter_sphinx_linenos = True"
    config += "\n" + "jupyter_sphinx_continue_linenos = True"

    sphinx_build = sphinx_build_factory(source, config=config).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_emphasize_lines(sphinx_build_factory, directive, file_regression):
    source = directive("execute", [f"{i} + {i}" for i in range(1, 6)], [("emphasize-lines", "2,4")])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_emphasize_lines_with_dash(sphinx_build_factory, directive, file_regression):
    source = directive(
        "execute", [f"{i} + {i}" for i in range(1, 6)], [("emphasize-lines", "2,3-5")]
    )

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_execution_environment_carries_over(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["a = 1"])
    source += "\n" + directive("execute", ["a += 1", "a"])

    sphinx_build = sphinx_build_factory(source).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_kernel_restart(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["a = 1"])
    source += "\n" + directive("kernel", [], [("id", "new-kernel")])
    source += "\n" + directive("execute", ["a += 1", "a"], ["raises"])

    sphinx_build = sphinx_build_factory(source).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_raises(sphinx_build_factory, directive):
    source = directive("execute", ["raise ValueError()"])

    with pytest.raises(ExtensionError):
        sphinx_build_factory(source).build()


def test_raises_incell(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["raise ValueError()"], ["raises"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_raises_specific_error_incell(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["raise ValueError()"], [("raises", "ValueError")])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_widgets(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["import ipywidgets", "ipywidgets.Button()"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]

    # replace model_id value as it changes every time the test suit is run
    script = json.loads(html.find("script").string)
    script["model_id"] = "toto"
    html.find("script").string = json.dumps(script)
    file_regression.check(html.prettify(), extension=".html")


def test_javascript(sphinx_build_factory, directive, file_regression):
    source = directive(
        "execute",
        [
            "from IPython.display import Javascript",
            "Javascript('window.alert(\"Hello there!\")')",
        ],
    )

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_stdout(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["print('Hello there!')"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_stderr_hidden(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["import sys", "print('Hello there!', file=sys.stderr)"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_stderr(sphinx_build_factory, directive, file_regression):
    source = directive(
        "execute", ["import sys", "print('Hello there!', file=sys.stderr)"], ["stderr"]
    )

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_hide_output(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 +2"], ["hide-output"])
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_hide_code(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["hide-code"])
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_code_below(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"], ["code-below"])
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_button_auto(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["1 + 1"])
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    # the button should fall after the cell i.e. index == 1
    html = sphinx_build.index_html.select("div.jupyter_cell,button.thebelab-button")[1]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_button_manual(sphinx_build_factory, directive, file_regression):
    source = ".. thebe-button::"
    source += "\n" + directive("execute", ["1 + 1"])
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    # the button should fall before the cell i.e. index == 0
    html = sphinx_build.index_html.select("div.jupyter_cell,button.thebelab-button")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_thebe_button_none(sphinx_build_factory, directive):
    source = "No Jupyter cells"
    config = 'jupyter_sphinx_thebelab_config = {"dummy": True}'

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("button.thebelab-button")
    assert len(list(html)) == 0


def test_latex(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["from IPython.display import Latex", r"Latex(r'$$\int$$')"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


@pytest.mark.xfail
def test_cell_output_to_nodes(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["import matplotlib.pyplot as plt", "plt.plot([1, 2], [1, 4])"])

    sphinx_build = sphinx_build_factory(source).build()

    # workaround to rename the trace ID as it's changed for each session
    # it's currently not working even though it's the same code as in test_widgets
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    text = r"[&lt;matplotlib.lines.Line2D at toto&gt;]"
    html.find(string=re.compile(r".*matplotlib\.lines\.Line2D.*")).string = text
    file_regression.check(html.prettify(), extension=".html")


@pytest.mark.parametrize("type", ["script", "notebook", "nb"])
def test_jupyter_download(sphinx_build_factory, file_regression, type):
    source = f"This is a script: :jupyter-download-{type}:`a file <test>`"

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.body")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_save_script(sphinx_build_factory, directive, file_regression):
    source = directive("kernel", [], [("id", "test")], "python3")
    source += "\n" + directive("execute", ["a = 1", "print(a)", ""])

    sphinx_build = sphinx_build_factory(source).build()
    saved_text = (sphinx_build.outdir / "../jupyter_execute/test.py").read_text()
    file_regression.check(saved_text, extension=".py")


@pytest.mark.skipif(os.name == "nt", reason="No bash test on windows")
def test_bash_kernel(sphinx_build_factory, directive, file_regression):
    source = directive("kernel", [], [("id", "test")], "bash")
    source += "\n" + directive("execute", ['echo "foo"'])

    # See https://github.com/takluyver/bash_kernel/issues/105
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        sphinx_build = sphinx_build_factory(source).build()

    saved_text = (sphinx_build.outdir / "../jupyter_execute/test.sh").read_text()
    file_regression.check(saved_text, extension=".sh")


def test_input_cell(sphinx_build_factory, directive, file_regression):
    source = directive("input", ("2 + 2"))

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_input_cell_linenos(sphinx_build_factory, directive, file_regression):
    source = directive("input", ["2 + 2"], ["linenos"])

    sphinx_build = sphinx_build_factory(source).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_output_cell(sphinx_build_factory, directive, file_regression):
    source = directive("input", ["3 + 2"])
    source += "\n" + directive("output", ["4"])

    sphinx_build = sphinx_build_factory(source).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_output_only_error(sphinx_build_factory, directive):
    source = directive("output", ["4"])

    with pytest.raises(ExtensionError):
        sphinx_build_factory(source).build()


def test_multiple_directives_types(sphinx_build_factory, directive, file_regression):
    source = directive("execute", ["2 + 2"])
    source += "\n" + directive("input", ["3 + 3"])
    source += "\n" + directive("output", ["6"])

    sphinx_build = sphinx_build_factory(source).build()
    htmls = sphinx_build.index_html.select("div.jupyter_cell")
    file_regression.check("\n".join([e.prettify() for e in htmls]), extension=".html")


def test_builder_priority_html(sphinx_build_factory, directive, file_regression):
    source = directive(
        "execute",
        ['display({"text/plain": "I am html output", "text/latex": "I am latex"})'],
    )
    config = "render_priority_html = ['text/plain', 'text/latex']"

    sphinx_build = sphinx_build_factory(source, config=config).build()
    html = sphinx_build.index_html.select("div.jupyter_cell")[0]
    file_regression.check(html.prettify(), extension=".html")


def test_builder_priority_latex(sphinx_build_factory, directive, file_regression):
    source = directive(
        "execute",
        ['display({"text/plain": "I am html output", "text/latex": "I am latex"})'],
    )
    "render_priority_latex = ['text/latex', 'text/plain']"

    sphinx_build = sphinx_build_factory(source, buildername="latex").build()
    latex = (sphinx_build.outdir / "python.tex").read_text()
    file_regression.check(latex, extension=".tex")
