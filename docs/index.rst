Jupyter Sphinx Extension
========================

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Contents:

   setup
   thebelab
   options
   changelog <https://github.com/jupyter/jupyter-sphinx/releases>

Jupyter-sphinx is a Sphinx extension that executes embedded code in a Jupyter kernel and embeds the outputs of that code in the document. It has support for rich output such as images, Latex math and even javascript widgets, and it allows enabling `thebe <https://thebe.readthedocs.io/>`_ for live code execution with minimal effort.

.. code-block:: rst

    .. jupyter-execute::

        print("Hello world!")

.. jupyter-execute::

    print("Hello world!")

.. grid:: 1 2 2 3
    :gutter: 2

    .. grid-item-card:: :fas:`download` Getting started
        :link: setup.html

        Learn how to use the lib from different sources.

    .. grid-item-card:: :fas:`book-open` Advance usage
        :link: options.html

        Learn advance usage and extra configuration of ``jupyter-sphinx``.

    .. grid-item-card:: :fas:`plug` Thebelab
        :link: thebelab.html

        Discover how ``ThebeLab`` is linked to ``jupyter-sphinx``.

.. seealso::

    Other extensions exist to display the output of IPython cells in Sphinx documentation. If you want to execute entire notebooks you can consider using `nbsphinx <https://nbsphinx.readthedocs.io>`__ or `myst-nb <https://myst-nb.readthedocs.io/>`__. For in-page live execution consider using `sphinx-thebe <https://sphinx-thebe.readthedocs.io/>`__ or `jupyterlite-sphinx <https://jupyterlite-sphinx.readthedocs.io/>`__. For users that don't need to rely on a jupyter kernel the lightweight `IPython sphinx directive <https://ipython.readthedocs.io/en/stable/sphinxext.html#ipython-sphinx-directive>`__ can be used but remember it will only be able to display text outputs.
