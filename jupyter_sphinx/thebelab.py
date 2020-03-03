"""Inserting interactive links with Thebelab."""
import os
import json
import docutils
from docutils.parsers.rst import Directive

import jupyter_sphinx as js


class ThebeSourceNode(docutils.nodes.container):
    """Container that holds the cell source when thebelab is enabled"""

    def __init__(self, rawsource="", *children, **attributes):
        super().__init__("", **attributes)

    def visit_html(self):
        code_class = "thebelab-code"
        if self["hide_code"]:
            code_class += " thebelab-hidden"
        if self["code_below"]:
            code_class += " thebelab-below"
        language = self["language"]
        return '<div class="{}" data-executable="true" data-language="{}">'.format(
            code_class, language
        )

    def depart_html(self):
        return "</div>"


class ThebeOutputNode(docutils.nodes.container):
    """Container that holds all the output nodes when thebelab is enabled"""

    def visit_html(self):
        return '<div class="thebelab-output" data-output="true">'

    def depart_html(self):
        return "</div>"


class ThebeButtonNode(docutils.nodes.Element):
    """Appended to the doctree by the ThebeButton directive

    Renders as a button to enable thebelab on the page.

    If no ThebeButton directive is found in the document but thebelab
    is enabled, the node is added at the bottom of the document.
    """

    def __init__(self, rawsource="", *children, text="Make live", **attributes):
        super().__init__("", text=text)

    def html(self):
        text = self["text"]
        return (
            '<button title="{text}" class="thebelab-button" id="thebelab-activate-button" '
            'onclick="initThebelab()">{text}</button>'.format(text=text)
        )


class ThebeButton(Directive):
    """Specify a button to activate thebelab on the page

    Arguments
    ---------
    text : str (optional)
        If provided, the button text to display

    Content
    -------
    None
    """

    optional_arguments = 1
    final_argument_whitespace = True
    has_content = False

    def run(self):
        kwargs = {"text": self.arguments[0]} if self.arguments else {}
        return [ThebeButtonNode(**kwargs)]


def add_thebelab_library(doctree, env):
    """Adds the thebelab configuration and library to the doctree"""
    thebe_config = env.config.jupyter_sphinx_thebelab_config
    if isinstance(thebe_config, dict):
        pass
    elif isinstance(thebe_config, str):
        if os.path.isabs(thebe_config):
            filename = thebe_config
        else:
            filename = os.path.join(os.path.abspath(env.app.srcdir), thebe_config)

        if not os.path.exists(filename):
            js.logger.warning("The supplied thebelab configuration file does not exist")
            return

        with open(filename, "r") as config_file:
            try:
                thebe_config = json.load(config_file)
            except ValueError:
                js.logger.warning(
                    "The supplied thebelab configuration file is not in JSON format."
                )
                return
    else:
        js.logger.warning(
            "The supplied thebelab configuration should be either a filename or a dictionary."
        )
        return

    # Force config values to make thebelab work correctly
    thebe_config["predefinedOutput"] = True
    thebe_config["requestKernel"] = True

    # Specify the thebelab config inline, a separate file is not supported
    doctree.append(
        docutils.nodes.raw(
            text='\n<script type="text/x-thebe-config">\n{}\n</script>'.format(
                json.dumps(thebe_config)
            ),
            format="html",
        )
    )

    # Add thebelab library after the config is specified
    doctree.append(
        docutils.nodes.raw(
            text='\n<script type="text/javascript" src="{}"></script>'.format(
                env.config.jupyter_sphinx_thebelab_url
            ),
            format="html",
        )
    )
