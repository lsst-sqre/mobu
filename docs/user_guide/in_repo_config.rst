##############
In-repo config
##############

Some mobu behavior can be controlled by files within notebook repos that mobu clones and runs.

.. _in_repo_exclude_dirs:

Exclude notebooks in specific directories
=========================================

You can tell mobu to exclude notebooks in specific directories by creating a ``mobu.yaml`` file at the root of your notebook repo that looks like this:

.. code-block:: yaml

   exclude_dirs:
     - "some-dir"
     - "some-other-dir"

This prevents mobu from executing any notebooks in these directories or any descendant directories.
These directories are relative to the repo root.
If this is set in the repo config file like this, it will override the ``exclude_dirs`` value specified in the :ref:`autostart config <autostart_exclude_dirs>`.

Service-specific notebooks
==========================

Each mobu instance knows what other `services <https://phalanx.lsst.io/applications/index.html>`_ are running in its environment.
You can annotate a notebook to tell mobu to only run it if certain services are available.
Add a ``mobu`` section to the `notebook metadata <https://phalanx.lsst.io/applications/index.html>`_ with a ``required_services`` key:

.. code-block:: jsonnet

   {
     "cells": [
       // A bunch of cells
     ],
     "metadata": {
       "mobu": {
         "required_services": ["nublado"]
       },
       // A bunch of other metadata
     },
     "nbformat": 4,
     "nbformat_minor": 5
   }
