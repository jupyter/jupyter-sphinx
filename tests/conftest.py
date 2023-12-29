"""Global configuration of the test session"""
import os
import sys
from pathlib import Path
import tempfile
from io import StringIO
import shutil
import asyncio
from typing import Callable, List, Tuple, Union

import pytest
from sphinx.testing.util import SphinxTestApp
from bs4 import BeautifulSoup
import sphinx

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
    [app.cleanup() for app in reversed(apps)]
    [shutil.rmtree(tree) for tree in source_trees]


class SphinxBuild:
    """Helper class to build a test documentation."""

    def __init__(self, app: SphinxTestApp, src: Path):
        self.app = app
        self.src = src

    def build(self, no_warning: bool = False):
        """Build the application."""
        self.app.build()
        if no_warning is True:
            assert self.warnings == "", self.status
        return self

    @property
    def status(self) -> str:
        """Returns the status of the current build."""
        return self.app._status.getvalue()

    @property
    def warnings(self) -> str:
        """Returns the warnings raised by the current build."""
        return self.app._warning.getvalue()

    @property
    def outdir(self) -> Path:
        """Returns the output directory of the current build."""
        return Path(self.app.outdir)

    @property
    def index_html(self) -> BeautifulSoup:
        """Returns the html tree of the current build."""
        path_page = self.outdir.joinpath("index.html")
        return BeautifulSoup(path_page.read_text("utf8"), "html.parser")


@pytest.fixture()
def sphinx_build_factory(tmp_path: Path) -> Callable:
    """Return a factory builder"""

    def _func(
        source,
        config: str = "",
        entrypoint: str = "jupyter_sphinx",
        buildername: str = "html",
    ) -> SphinxBuild:
        """Create the Sphinxbuild from the source folder."""
        src_dir = tmp_path
        conf_contents = f"extensions = ['{entrypoint}']"
        conf_contents += "\n" + config
        (src_dir / "conf.py").write_text(conf_contents, encoding="utf8")
        (src_dir / "index.rst").write_text(source, encoding="utf8")

        # api inconsistency from sphinx
        if sphinx.version_info < (7, 2):
            from sphinx.testing.path import path as sphinx_path

            src_dir = sphinx_path(src_dir)

        app = SphinxTestApp(srcdir=src_dir, buildername=buildername)

        return SphinxBuild(app, tmp_path)

    return _func


@pytest.fixture(scope="session")
def directive() -> Callable:
    """A function to build the directive string"""

    def _func(
        type: str,
        code: List[str],
        options: List[Union[str, Tuple]] = [],
        parameter: str = "",
    ) -> str:
        """Return the formatted string of the required directive

        Args:
            type: the type of directive to build, one of [execute, input, output, kernel]
            code: the list of code instructions to write in the cell
            options: the list of options of the directive if option requires a parameter, use a tuple
            parameter: The parameter of the directive (written on the first line)
        """
        # parse all the options as tuple
        options = [(o, "") if isinstance(o, str) else o for o in options]

        # create the output string
        s = f".. jupyter-{type}:: {parameter}"
        s += "".join([f"\n\t:{o[0]}: {o[1]}" for o in options])
        s += "\n"
        s += "".join([f"\n\t{c}" for c in code])
        s += "\n"

        return s

    return _func
