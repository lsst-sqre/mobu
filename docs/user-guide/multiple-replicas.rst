=================
Multiple Replicas
=================

Multiple replicas of Mobu can be run in the same environment.
This is useful when a single replica's CPU gets saturated to the point where errors start occuring.
Spreading the load over multiple CPUs by using multiple replicas is useful for load testing, and probably not useful otherwise, as it comes with some downsides.

Downsides
---------

* Only ``user_spec`` with no ``gid_start`` and ``uid_start`` config is allowed, because:

  * There is no way to specify different user config for different replicas, so users must be dynamically created with different names.
  * Replicas don't have any knowledge of the other replicas to divide an explicit user pool amongst themselves.

* The web API will only return info from a single replica. Getting info from every instance will require forwarding requests to individual pods.
* The GitHub refresh integration will not work because only one pod will get the webhook from GitHub.

Mobu should currently only be run with multiple replicas during explicitly monitored periods, like scheduled load testing.
Otherwise, the behavior described above could lead to confusion.
If other use cases for multiple replicas come up in the future, we can do some more work to mitigate some of these downsides.

Differences From a Single Replica
---------------------------------

The only difference when running as one of multiple replicas is that ``user_spec`` usernames will be further prefixed with an instance identifier.
Mobu adds this prefix if the ``MOBU_REPLICA_COUNT`` env var contains a value that is greater than 1.
This instance identifier comes from the ``MOBU_INSTANCE_ID`` env var.

.. note::

   The ``count`` parameter in the autostart config still controls the number of monkeys to start for a single instance.
   If you set ``count`` to ``4`` for a given flock and then start 4 replicas, each replica will run 4 monkeys, giving you a total of 16 running monkeys.
   This means that the minimum total number of running monkeys for a given business is the number of replicas (by specifying a ``count`` of ``1`` in the autostart config).

Phalanx Configuration
---------------------

The replica count from the helm chart values is templated into the ``replicas`` value of the Mobu workload, and the ``MOBU_REPLICA_COUNT`` environment variable.

The Mobu workload is a ``StatefulSet`` instead of a ``Deployment`` so that the `pod index label`_ can be passed as the value to the ``MOBU_INSTANCE_ID`` env var via the Kubernetes `Downward API`_.
This ensures that:

* Every replica gets a different ID.
* Prefixed usernames are somewhat consistent across restarts to avoid creating a lot of orphaned users.

.. _pod index label: https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/#pod-index-label
.. _Downward API: https://kubernetes.io/docs/concepts/workloads/pods/downward-api/
