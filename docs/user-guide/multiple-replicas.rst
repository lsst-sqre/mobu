=================
Multiple Replicas
=================

Multiple replicas of Mobu can be run in the same environment.
This is useful when a single replica's CPU gets saturated to the point where errors start occuring.
Spreading the load over multiple CPUs by using multiple replicas is useful for load testing, and probably not useful otherwise, as it comes with some downsides.

.. note::

   The ``count`` parameter in the flock config controls the total number of monkeys to start across ALL of the replicas.
   If you set ``count`` to ``100`` and then start 4 replicas, each replica will run 25 monkeys.

   Similarly, the ``start_batch_size`` parameter in the flock config controls the number of monkeys that will be started simultaneously in each back across ALL of the replicas.
   If you set the ``start_batch_size`` to ``40`` and then start 4 replicas, each replica will try to start 10 monkeys in each batch.

Downsides
---------

* The web API will only return info from a single replica. Getting info from every instance will require forwarding requests to individual pods.
* The GitHub refresh integration will not work because only one pod will get the webhook from GitHub.

Mobu should currently only be run with multiple replicas during explicitly monitored periods, like scheduled load testing.
Otherwise, the behavior described above could lead to confusion.
If other use cases for multiple replicas come up in the future, we can do some more work to mitigate some of these downsides.

Phalanx Configuration
---------------------

The replica count from the helm chart values is templated into the ``replicas`` value of the Mobu workload, and the ``MOBU_REPLICA_COUNT`` environment variable.

The Mobu workload is a ``StatefulSet`` instead of a ``Deployment`` so that the `pod index label`_ can be passed as the value to the ``MOBU_REPLICA_INDEX`` env var via the Kubernetes `Downward API`_.
This ensures that monkeys can be distributed as evenly as possible among all of the replicas in the ``StatefulSet``.

.. _pod index label: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#pod-index-label
.. _Downward API: https://kubernetes.io/docs/concepts/workloads/pods/downward-api/
