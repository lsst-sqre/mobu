##########################################
Run notebooks in Mobu as a GitHub CI check
##########################################

Problem
   You have a GitHub repo filled with Python notebooks.
   You’ve already configured Mobu to run a flock that executes these notebooks.
   You want to make sure that any changes to these notebooks don’t cause them to break when they run in Mobu, but you don’t want to have to commit the possibly-broken changes just to get Mobu to run them to test the changes.

Solution
   Enable a GitHub app for your repo, and Mobu will create a GitHub Actions
   check that runs changed notebooks in Mobu on any commit associated with
   a pull request!

.. _configuration-1:

Configuration
=============

There is a ``mobu CI (<env url>)`` GitHub app for every non-production environment that runs Mobu (Except environments behind a VPN).
For every environment in which you want to run your changed notebooks on every PR commit, you have to install the app in your repo's organization and enable the app for your repo.

Install the app
---------------
If it’s not already installed, that is.

#. Install that environment’s ``mobu CI`` app in your repo’s GitHub organization.
   Someone with appropriate permissions can do that from the `app’s homepage <#mobu-ci-github-app-urls>`__.
#. Add your organization to the ``accetped_github_orgs`` list in the Mobu configuration in Phalanx for the matching env.

Enable the app for your repo
----------------------------

#. Go to your repo’s organization settings page in GitHub, and go to the “GitHub Apps” page in the “Third-party Access” section in the left sidebar.
   `Here <https://github.com/organizations/lsst-sqre/settings/installations>`__ is that page for the ``lsst-sqre`` organization.
#. Click the ``Configure`` button in the ``mobu CI (<env url>)`` row.
#. In the “Repository access” section, click the “Select repositories” dropdown and add your repository.

Optional configuration
======================

You can have mobu ignore changed notebooks in certain directories in these CI checks by listing them in a file named ``mobu.yaml`` at the root of your repo, like this:

.. code:: yaml

   exclude_dirs:
   - somedir
   - some/other/dir

With this configuration, no notebooks in the ``somedir``, or ``some/other/dir`` directories, or any of their descendant directories, will be executed, even if they changed in the commit.

Troubleshooting
===============

There is a small chance that a GitHub check could get stuck in a forever-in-progress state for a given commit if the stars align in a very specific way when mobu restarts.
If this happens, you can push a commit to your branch, and it will start a new check run.
If you don’t have any actual changes to commit, you can push an empty commit like this::

   git commit --allow-empty -m "Empty commit"

You can squash that commit later if you want a clean history.

Mobu CI GitHub app URLs
=======================

-  `data-dev.lsst.cloud <https://github.com/apps/mobu-ci-data-dev-lsst-cloud>`__
