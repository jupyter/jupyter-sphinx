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

Jupyter-sphinx is a Sphinx extension that executes embedded code in a Jupyter
kernel, and embeds outputs of that code in the document. It has support
for rich output such as images, Latex math and even javascript widgets, and
it allows to enable `thebelab <https://thebelab.readthedocs.io/>`_ for live
code execution with minimal effort.

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
