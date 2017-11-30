# Jupyter Sphinx Extensions

Jupyter Sphinx extensions enable jupyter-specific features in sphinx.

## Installation

With pip:

```bash
pip install jupyter_sphinx
```

with conda:

```bash
conda install jupyter_sphinx -c conda-forge
```

## Render Jupyter Interactive Widgets `jupyter_sphinx.embed_widgets`

This extension provides a means of inserting live-rendered Jupyter
interactive widgets within sphinx documentation.

It is derived from the [`altair`](https://github.com/altair-viz/altair) sphinx
extension, which is distributed under the terms of the BSD 3-Clause license.

### Enabling the extension

To enable this extension, add `jupyter_sphinx.embed_widgets` to your enabled
extensions in `conf.py`.

### Directives

Two directives are provided: `ipywidgets-setup` and `ipywidgets-display`.

`ipywidgets-setup` code is used to set-up various options
prior to running the display code. For example:

```rst
.. ipywidgets-setup::

	from ipywidgets import VBox, jsdlink, IntSlider, Button

.. ipywidgets-display::

    s1, s2 = IntSlider(max=200, value=100), IntSlider(value=40)
	b = Button(icon='legal')
	jsdlink((s1, 'value'), (s2, 'max'))
	VBox([s1, s2, b])
```

In the case of the `ipywidgets-display` code, if the *last statement* of the
code-block returns a widget object, it will be rendered.

### Options

The directives have the following options:

```rst
.. ipywidgets-setup::
    :show: # if set, then show the setup code as a code block

    from ipywidgets import Button

.. ipywidgets-display::
    :hide-code:   # if set, then hide the code and only show the widget
    :code-below:  # if set, then code is below rather than above the widget
    :alt: text    # alternate text when widget cannot be rendered

    Button()
```

### Configuration

You conf.py has two extra (optional) configuration options:

 * jupyter_sphinx_require_url: url for `require.js` (if your theme already provides this, set it to False or '')
 * jupyter_sphinx_embed_url: url for the embedding, if set to None (default) a proper default will be taken from the `ipywidgets.embed` module. 

### Misc.

- For the widgets to be succesfuly rendered, this extension requires an
  internet connection, since it depends on a cdn-distributed JavaScript.
- Widgets rendered on the same page use the same widget manager. As a
  consequence, they can be linked with each other via JavaScript link widgets.
  However, no kernel is connect and therefore, interaction with the backend
  will not happen.

## License
We use a shared copyright model that enables all contributors to maintain the
copyright on their contributions.

All code is licensed under the terms of the revised BSD license.
