"""Global configuration of the test session"""
import os
import sys
from pathlib import Path
import tempfile
from io import StringIO
import shutil
import asyncio
from typing import Callable, List

import pytest
from sphinx.testing.util import SphinxTestApp

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
        return_all=True,
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


@pytest.fixture(scope="session")
def directive() -> Callable:
    """A function to build the directive string"""

    def _func(type: str, code: List[str], options: [List[str]] = []) -> str:
        """Return the formatted string of the required directive

        Args:
            type: the type of directive to build, one of [execute, input, output]
            code: the list of code instructions to write in the cell
            options: the list of options of the directive
        """
        s = f".. jupyter-{type}::"
        s += "".join([f"\n\t:{o}:" for o in options])
        s += "\n"
        s += "".join([f"\n\t{c}" for c in code])
        s += "\n"

        return s

    return _func
