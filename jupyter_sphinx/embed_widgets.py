"""
Sphinx Extension for Jupyter Interactive Widgets
================================================

This extension provides a means of inserting live-rendered Jupyter
interactive widgets within sphinx documentation.

Two directives are provided: ``ipywidgets-setup`` and ``ipywidgets-display``.

``ipywidgets-setup`` code is used to set-up various options
prior to running the display code. For example::

    .. ipywidgets-setup::

		from ipywidgets import VBox, jsdlink, IntSlider, Button

    .. ipywidgets-display::

        s1, s2 = IntSlider(max=200, value=100), IntSlider(value=40)
		b = Button(icon='legal')
		jsdlink((s1, 'value'), (s2, 'max'))
		VBox([s1, s2, b])

In the case of the ``ipywidgets-display`` code, if the *last statement* of the
code-block contains a widget object, it will be rendered.

Options
-------

The directives have the following options::

    .. ipywidgets-setup::
        :show: # if set, then show the setup code as a code block

        from ipywidgets import Button

    .. pywidgets-display::
        :hide-code:   # if set, then hide the code and only show the widget
        :code-below:  # if set, then code is below rather than above the widget
        :alt: text    # alternate text when widget cannot be rendered

        Button()
"""

import os
import json
import warnings

from docutils import nodes
from docutils.parsers.rst import Directive
from docutils.parsers.rst.directives import flag, unchanged

from ipywidgets import Widget

from sphinx.locale import _
from sphinx import addnodes, directives
from sphinx.util.nodes import set_source_info

import ast

def exec_then_eval(code, namespace=None):
    """Exec a code block & return evaluation of the last line"""
    namespace = namespace or {}

    block = ast.parse(code, mode='exec')
    last = ast.Expression(block.body.pop().value)

    exec(compile(block, '<string>', mode='exec'), namespace)
    return eval(compile(last, '<string>', mode='eval'), namespace)


class widget(nodes.General, nodes.Element):
    pass


class IPywidgetsSetupDirective(Directive):
    has_content = True

    option_spec = {
        'show': flag
    }

    def run(self):
        env = self.state.document.settings.env

        targetid = "ipywidgets-setup-{0}".format(env.new_serialno('ipywidgets-setup'))
        targetnode = nodes.target('', '', ids=[targetid])

        code = '\n'.join(self.content)

        # Here we cache the code for use in later setup
        if not hasattr(env, 'ipywidgets_setup'):
            env.ipywidgets_setup = []

        env.ipywidgets_setup.append({
            'docname': env.docname,
            'lineno': self.lineno,
            'code': code,
            'target': targetnode,
        })

        result = [targetnode]

        if 'show' in self.options:
            source_literal = nodes.literal_block(code, code)
            source_literal['language'] = 'python'
            result.append(source_literal)

        return result

def purge_widget_setup(app, env, docname):
    if not hasattr(env, 'ipywidgets_setup'):
        return
    env.ipywidgets_setup = [item for item in env.ipywidgets_setup if item['docname'] != docname]


class IPywidgetsDisplayDirective(Directive):

    has_content = True

    option_spec = {
        'hide-code': flag,
        'code-below': flag,
        'alt': unchanged,
    }

    def run(self):
        env = self.state.document.settings.env
        app = env.app

        show_code = 'hide-code' not in self.options
        code_below = 'code-below' in self.options

        setupcode =  '\n'.join([
            'from ipywidgets import Widget',
            'Widget._ipython_display_ = custom_display'
        ]) + '\n' + '\n'.join(item['code']
            for item in getattr(env, 'ipywidgets_setup', [])
            if item['docname'] == env.docname
        )

        code = '\n'.join(self.content)

        if show_code:
            source_literal = nodes.literal_block(code, code)
            source_literal['language'] = 'python'

        # get the name of the source file we are currently processing
        rst_source = self.state_machine.document['source']
        rst_dir = os.path.dirname(rst_source)
        rst_filename = os.path.basename(rst_source)

        # use the source file name to construct a friendly target_id
        serialno = env.new_serialno('jupyter-widget')
        rst_base = rst_filename.replace('.', '-')
        target_id = "jupyter-widget-%d" % serialno
        target_node = nodes.target('', '', ids=[target_id])

        # create the node in which the widget will appear;
        # this will be processed by html_visit_widget
        widget_node = widget()
        widget_node['code'] = code
        widget_node['setupcode'] = setupcode
        widget_node['relpath'] = os.path.relpath(rst_dir, env.srcdir)
        widget_node['rst_source'] = rst_source
        widget_node['rst_lineno'] = self.lineno

        if 'alt' in self.options:
            widget_node['alt'] = self.options['alt']

        result = [target_node]

        if code_below:
            result += [widget_node]
        if show_code:
            result += [source_literal]
        if not code_below:
            result += [widget_node]

        return result

def make_custom_display(body):
    def custom_display(self, **kwargs):
        view_spec = json.dumps(self.get_view_spec())
        body.append('<script type="application/vnd.jupyter.widget-view+json">' + view_spec + '</script>')
    return custom_display

def html_visit_widget(self, node):
    # Execute the setup code, saving the global & local state
    namespace = dict(custom_display=make_custom_display(self.body))

    if node['setupcode']:
        exec(node['setupcode'], namespace)

    # Execute the widget code in this context, evaluating the last line
    try:
        w = exec_then_eval(node['code'], namespace)
    except Exception as e:
        warnings.warn("ipywidgets-display: {0}:{1} Code Execution failed:"
                      "{2}: {3}".format(node['rst_source'], node['rst_lineno'],
                                        e.__class__.__name__, str(e)))
        raise nodes.SkipNode

    if isinstance(w, Widget):
        view_spec = json.dumps(w.get_view_spec())
        self.body.append('<script type="application/vnd.jupyter.widget-view+json">' + view_spec + '</script>')
    raise nodes.SkipNode

def generic_visit_widget(self, node):
    if 'alt' in node.attributes:
        self.body.append(_('[ widget: %s ]') % node['alt'])
    else:
        self.body.append(_('[ widget ]'))
    raise nodes.SkipNode

def add_widget_state(app, pagename, templatename, context, doctree):
    if 'body' in context and Widget.widgets:
        state_spec = json.dumps(Widget.get_manager_state(drop_defaults=True))
        Widget.widgets = {}
        context['body'] += '<script type="application/vnd.jupyter.widget-state+json">' + state_spec + '</script>'

def setup(app):
    setup.app = app
    setup.config = app.config
    setup.confdir = app.confdir

    app.add_stylesheet('https://unpkg.com/font-awesome@4.5.0/css/font-awesome.min.css')
    try:
        import ipywidgets.embed
        from ipywidgets._version import __html_manager_version__
        app.add_javascript('https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.4/require.min.js')
        app.add_javascript('https://unpkg.com/@jupyter-widgets/html-manager@%s/dist/libembed-amd.js' % __html_manager_version__)
        app.add_javascript('https://unpkg.com/@jupyter-widgets/html-manager@%s/dist/embed-amd.js' % __html_manager_version__)
    except ImportError:
        app.add_javascript('https://unpkg.com/jupyter-js-widgets@^2.0.13/dist/embed.js')

    app.add_node(widget,
                 html=(html_visit_widget, None),
                 latex=(generic_visit_widget, None),
                 texinfo=(generic_visit_widget, None),
                 text=(generic_visit_widget, None),
                 man=(generic_visit_widget, None))

    app.add_directive('ipywidgets-setup', IPywidgetsSetupDirective)
    app.add_directive('ipywidgets-display', IPywidgetsDisplayDirective)
    app.connect('html-page-context', add_widget_state)
    app.connect('env-purge-doc', purge_widget_setup)

    return {
        'version': '0.1'
    }
