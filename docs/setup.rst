Getting started
===============

Installation
------------
Get ``jupyter-sphinx`` from pip:

.. code-block:: bash

  pip install jupyter-sphinx

or ``conda``:

.. code-block:: bash

  conda install jupyter_sphinx -c conda-forge

Enabling the extension
----------------------

To enable the extension, add ``jupyter_sphinx`` to your enabled extensions in ``conf.py``:

.. code-block:: python

   extensions = [
      "jupyter_sphinx",
   ]

Basic Usage
-----------

You can use the ``jupyter-execute`` directive to embed code into the document:

.. code-block:: rst

  .. jupyter-execute::

    name = "world"
    print(f"hello {name} !")

The above is rendered as follows:

.. jupyter-execute::

  name = "world"
  print(f"hello {name} !")

Note that the code produces *output* (printing the string ``"hello world!"``), and the output is rendered directly after the code snippet.

Because all code cells in a document are run in the same kernel, cells later in the document can use variables and functions defined in cells earlier in the document:

.. jupyter-execute::

    a = 1
    print(f"first cell: a = {a}")

.. jupyter-execute::

    a += 1
    print("second cell: a = {a}")

Because ``jupyter-sphinx`` uses the machinery of ``nbconvert``, it is capable of rendering any rich output, for example plots:

.. jupyter-execute::

    import numpy as np
    from matplotlib import pyplot
    %matplotlib inline

    x = np.linspace(1E-3, 2 * np.pi)

    pyplot.plot(x, np.sin(x) / x)
    pyplot.plot(x, np.cos(x))
    pyplot.grid()

LaTeX output:

.. jupyter-execute::

  from IPython.display import Latex
  Latex("\\int_{-\\infty}^\\infty e^{-x²}dx = \\sqrt{\\pi}")

or even full-blown javascript widgets:

.. jupyter-execute::

    import ipywidgets as w
    from IPython.display import display

    a = w.IntSlider()
    b = w.IntText()
    w.jslink((a, "value"), (b, "value"))
    display(a, b)

It is also possible to include code from a regular file by passing the filename as argument to ``jupyter-execute``:

.. code-block:: rst

  .. jupyter-execute:: some_code.py

``jupyter-execute`` may also be used in docstrings within your Python code, and will be executed
when they are included with Sphinx autodoc.
