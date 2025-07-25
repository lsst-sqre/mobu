.. toctree::
   :maxdepth: 1
   :hidden:

   user-guide/index
   operations/index
   dev/index
   api

.. toctree::
   :hidden:

   changelog

####
Mobu
####

mobu (short for "monkey business") is a continous integration testing framework for the `Rubin Science Platform <https://phalanx.lsst.io/>`__ .
It attempts to simulate user interactions with Science Platform services continuously, recording successes and failures and reporting failures to `Sentry <https://sentry.io/welcome/>`_.
It runs some number of "monkeys" that simulate a random user of the Science Platform.
Those monkeys are organized into "flocks" that share a single configuration across all of the monkeys.
It can be used for both monitoring and synthetic load testing.

mobu is on github at https://github.com/lsst-sqre/mobu.

.. grid:: 3

   .. grid-item-card:: User Guide
      :link: user-guide/index
      :link-type: doc

      Learn how to configure mobu to run your run and test your code.

   .. grid-item-card:: Operations
      :link: operations/index
      :link-type: doc

      Learn how to add mobu to new environments and add new integrations to mobu.

   .. grid-item-card:: Development
      :link: dev/index
      :link-type: doc

      Learn how to add contribute to the mobu codebase.
