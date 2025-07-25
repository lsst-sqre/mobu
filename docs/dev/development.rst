#################
Development guide
#################

This page provides procedures and guidelines for developing and contributing to mobu.

Scope of contributions
======================

mobu is an open source package, meaning that you can contribute to mobu itself, or fork mobu for your own purposes.

Since mobu is intended for internal use by Rubin Observatory, community contributions can only be accepted if they align with Rubin Observatory's aims.
For that reason, it's a good idea to propose changes with a new `GitHub issue`_ before investing time in making a pull request.

mobu is developed by the LSST SQuaRE team.

.. _GitHub issue: https://github.com/lsst-sqre/mobu/issues/new

.. _dev-environment:

Setting up a local development environment
==========================================

Prerequisites
-------------

mobu uses uv_ for all dependency management.
A reasonably recent version of :command:`uv` must already be installed.
See `the uv installation instructions <https://docs.astral.sh/uv/getting-started/installation/>`__ if needed.

Set up development environment
------------------------------

To develop mobu, create a virtual environment with :command:`uv venv` and then run :command:`make init`.

.. prompt:: bash

   git clone https://github.com/lsst-sqre/mobu.git
   cd mobu
   uv venv
   make init

This init step does three things:

1. Installs mobu in a virtualenv in the :file:`.venv` directory, including the dependency groups for local development.
2. Installs pre-commit_, tox_, and the necessary tox plugins.
3. Installs the pre-commit hooks.

Finally, you can optionally enter the mobu development virtualenv with:

.. prompt:: bash

   source .venv/bin/activate

This is optional; you do not have to activate the virtualenv to do development.
However, if you do, you can omit :command:`uv run` from the start of all commands described below.
Also, editors with Python integration, such as VSCode, may work more smoothly if you activate the virtualenv before starting them.

.. _pre-commit-hooks:

Pre-commit hooks
================

The pre-commit hooks, which are automatically installed by running the :command:`make init` command on :ref:`set up <dev-environment>`, ensure that files are valid and properly formatted.
Some pre-commit hooks may automatically reformat code or update files:

blacken-docs
    Automatically formats Python code in reStructuredText documentation and docstrings.

ruff
    Lint Python code and attempt to automatically fix some problems.

uv-lock
    Update the :file:`uv.lock` file if dependencies in :file:`pyproject.toml` have changed.

When these hooks fail, your Git commit will be aborted.
To proceed, stage the new modifications and proceed with your Git commit.

.. _dev-run-tests:

Running tests
=============

To test mobu, run tox_:

.. prompt:: bash

   uv run tox run

To see a listing of test environments, run:

.. prompt:: bash

   uv run tox list

To run a specific test environment, run:

.. prompt:: bash

   uv run tox -e <environment>

For example, ``uv run tox -e typing`` will only run mypy and not the rest of the tests.

To run a specific test or list of tests, you can add test file names (and any other pytest_ options) after ``--`` when executing the ``py`` tox environment.
For example:

.. prompt:: bash

   uv run tox run -e py -- tests/business/nubladopythonloop_test.py

You can run a specific test function by appending two colons and the function name to the end of the file name.

Updating dependencies
=====================

All mobu dependencies are configured in :file:`pyproject.toml` like a regular Python package.
Runtime dependencies are configured in ``project.dependencies``, and development dependencies are configured under ``dependency-groups``.
The following dependency groups are used:

dev
    Dependencies required to run the test suite, not including the dependencies required to run tox itself.

lint
    Dependencies required to run pre-commit_ and to lint the code base.

tox
    Dependencies required to run tox_.

typing
    Dependencies required to run mypy_

These dependency groups are used by the tox configuration in :file:`tox.ini` to install the appropriate dependencies based on the tox action.
The development virtualenv in :file:`.venv` will have all of these dependency groups installed so the developer can freely use commands such as :command:`ruff` and :command:`mypy`.

A frozen version of all of these dependencies is managed by uv_ in the file :file:`uv.lock`.
This is used to pin all dependencies so that they only change when a developer intends to update them and is prepared to run tests to ensure nothing broke.

After changing any dependency, run :command:`make update-deps` to rebuild the :file:`uv.lock` file.
To also update the development virtualenv, run :command:`make update` instead.

Temporary Git dependencies
--------------------------

By default, all Python dependencies are retrieved from PyPI.

Sometimes during development it may be useful to test mobu against an unreleased version of one of its dependencies.
uv_ supports this by setting a `dependency source <https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-sources>`__.

For example, to use the current main branch of Safir_ instead of the latest released version, add the following to the end of :file:`pyproject.toml`:

.. code-block:: toml

   [tool.uv.sources]
   safir = { git = "https://github.com/lsst-sqre/safir", branch = "main", subdirectory = "safir" }

The :command:`uv add` command can be used to configure these sources if desired.
As always, after changing dependencies, run :command:`make update` or :command:`make update-deps`.
mobu will now use the unreleased version of Safir.

Do not release new non-alpha versions of mobu with these types of Git dependencies.
The other package should be released first before a new version of mobu is released.

Building documentation
======================

Documentation is built with Sphinx_:

.. _Sphinx: https://www.sphinx-doc.org/en/master/

.. prompt:: bash

   uv run tox run -e docs

The build documentation is located in the :file:`docs/_build/html` directory.

To check the documentation for broken links, run:

.. prompt:: bash

   uv run tox run -e docs-linkcheck

.. _dev-change-log:

Updating the change log
=======================

mobu uses scriv_ to maintain its change log.

When preparing a pull request, run :command:`uv run scriv create`.
This will create a change log fragment in :file:`changelog.d`.
Edit that fragment, removing the sections that do not apply and adding entries fo this pull request.
You can pass the ``--edit`` flag to :command:`uv run scriv create` to open the created fragment automatically in an editor.

Change log entries use the following sections:

- **Backward-incompatible changes**
- **New features**
- **Bug fixes**
- **Other changes** (for minor, patch-level changes that are not bug fixes, such as logging formatting changes or updates to the documentation)

Versioning assumes that mobu is installed via Phalanx, so changes to its internal configuration file do not count as backward-incompatible chnages unless they require changes to per-environment Helm :file:`values-{environment}.yaml` files.

Do not include a change log entry solely for updating pinned dependencies, without any visible change to mobu's behavior.
Every release is implicitly assumed to update all pinned dependencies.

These entries will eventually be cut and pasted into the release description for the next release, so the Markdown for the change descriptions must be compatible with GitHub's Markdown conventions for the release description.
Specifically:

- Each bullet point should be entirely on one line, even if it contains multiple sentences.
  This is an exception to the normal documentation convention of a newline after each sentence.
  Unfortunately, GitHub interprets those newlines as hard line breaks, so they would result in an ugly release description.
- Avoid using too much complex markup, such as nested bullet lists, since the formatting in the GitHub release description may not be what you expect and manually editing it is tedious.

.. _style-guide:

Style guide
===========

Code
----

- mobu follows the :sqr:`072` Python style guide.

- The code formatting follows :pep:`8`, though in practice lean on Ruff to format the code for you.

- Use :pep:`484` type annotations.
  The :command:`uv run tox run -e typing` command, which runs mypy_, ensures that the project's types are consistent.

- mobu uses the Ruff_ linter with most checks enabled.
  Its primary configuration is in :file:`ruff-shared.toml`, which should be an exact copy of the version from the `FastAPI Safir app template <https://github.com/lsst/templates/blob/main/project_templates/fastapi_safir_app/example/ruff-shared.toml>`__.
  Try to avoid ``noqa`` markers except for issues that need to be fixed in the future.
  Tests that generate false positives should normally be disabled, but if the lint error can be avoided with minor rewriting that doesn't make the code harder to read, prefer the rewriting.

- Write tests for pytest_.

Documentation
-------------

- Follow the `LSST DM User Documentation Style Guide`_, which is primarily based on the `Google Developer Style Guide`_.

- Document the Python API with numpydoc-formatted docstrings.
  See the `LSST DM Docstring Style Guide`_.

- Follow the `LSST DM ReStructuredTextStyle Guide`_.
  In particular, ensure that prose is written **one-sentence-per-line** for better Git diffs.

.. _`LSST DM User Documentation Style Guide`: https://developer.lsst.io/user-docs/index.html
.. _`Google Developer Style Guide`: https://developers.google.com/style/
.. _`LSST DM Docstring Style Guide`: https://developer.lsst.io/python/style.html
.. _`LSST DM ReStructuredTextStyle Guide`: https://developer.lsst.io/restructuredtext/style.html
