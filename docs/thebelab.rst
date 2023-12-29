Thebelab support
================

To turn on `thebelab <https://thebelab.readthedocs.io/>`_, specify its configuration directly in ``conf.py``:

.. code-block:: python

  jupyter_sphinx_thebelab_config = {
      "requestKernel": True,
      "binderOptions": {
          "repo": "binder-examples/requirements",
      },
  }

With this configuration, thebelab is activated with a button click:

.. thebe-button:: Activate Thebelab

By default the button is added at the end of the document, but it may also be inserted anywhere using

.. code-block:: rst

  .. thebe-button:: Optional title
