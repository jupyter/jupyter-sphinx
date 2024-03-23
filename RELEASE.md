# Release instructions for jupyter-sphinx

Jupyter Sphinx uses a GitHub action to automatically push a new release to
PyPI when a GitHub release is added.

To cut a new Jupyter Sphinx release, follow these steps:

- Ensure that all tests are passing on main.

- Create a pull request to bump the version:

  - In [`_version.py`](https://github.com/jupyter/jupyter-sphinx/blob/main/jupyter_sphinx/_version.py),
    update the version number:

    ```python
    __version__ = "0.2.3"
    ```

- Merge the pull request.

- [Create a new Github Release](https://github.com/jupyter/jupyter-sphinx/releases/new).
  The target should be **main**, the tag and the title should be the version number,
  e.g. `v0.2.3`. Note that this requires admin permissions on the repository.

- Creating the release in GitHub will push a tag commit to the repository, which will
  trigger [a GitHub action](https://github.com/jupyter/jupyter-sphinx/blob/main/.github/workflows/artifacts.yml)
  to build `jupyter-sphinx` and push the new version to PyPI.
  [Confirm that the version has been bumped](https://pypi.org/project/jupyter-sphinx/).

- That's it!
