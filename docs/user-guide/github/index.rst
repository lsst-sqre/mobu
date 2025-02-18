##################
GitHub integration
##################
Mobu offers two integrations with GitHub:

* Automatic notebook refreshing in flocks
* GitHub Actions checks for PR commits

Each is enabled by enabling a GitHub application on a repo full of notebooks.
There is a separate GitHub application for each integration in each environment.
This lets you enable these integrations for different combinations of environments.
For example, you can enable the auto-refresh integration in ``idfdev``, ``idfint``, ``usdfdev``, ``usdfint``, and ``usdfprod``, but the CI integration only in ``idfint`` and ``usdfint``.

.. toctree::

   refresh
   ci
