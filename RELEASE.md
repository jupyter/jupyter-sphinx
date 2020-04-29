# Release instructions for jupyter-sphinx

Jupyter Sphinx uses a GitHub action to automatically push a new release to
PyPI when a GitHub release is added.

To cut a new Jupyter Sphinx release, follow these steps:

* Ensure that all tests are passing on master.
* In [`_version.py`](https://github.com/jupyter/jupyter-sphinx/blob/master/jupyter_sphinx/_version.py),
  change the "release type" section to "final" e.g.:

  ```python
  version_info = (0, 2, 3, "final")
  ```
* Make a release commit and push to master

  ```
  git add jupyter_sphinx/_version.py
  git commit -m "RLS: 0.2.3"
  git push upstream master
  ```
* [Create a new github release](https://github.com/jupyter/jupyter-sphinx/releases/new).
  The target should be **master**, the tag and the title should be the version number,
  e.g. `0.2.3`.
* Creating the release in GitHub will push a tag commit to the repository, which will
  trigger [a GitHub action](https://github.com/jupyter/jupyter-sphinx/blob/master/.github/workflows/artifacts.yml)
  to build `jupyter-sphinx` and push the new version to PyPI.
  [Confirm that the version has been bumped](https://pypi.org/project/jupyter-sphinx/).
* In [`_version.py`](https://github.com/jupyter/jupyter-sphinx/blob/master/jupyter_sphinx/_version.py),
  bump the minor version and change the "release type" section to "alpha" e.g.:

  ```python
  version_info = (0, 2, 4, "alpha")
  ```
* That's it!
