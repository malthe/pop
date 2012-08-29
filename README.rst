Let *pop* run your services!

Skip to `acknowledgements and credits`_.

Motivation
==========

Software builds, deployment and service management, are tasks that
become exceedingly difficult to carry out without the assistance of
a computer.

Typically, this assistance is a collection of scripts that require
some amount of handholding. When multiple machines are involved, this
handholding becomes a problem of distributed coordination.

We need a tool!

This is not meant to replace a configuration tool such as `Chef
<http://www.opscode.com/chef/>`_ or `Puppet
<http://puppetlabs.com/>`_. You'll probably still need those.

To add to the confusion, it's also not meant to replace `Supervisor
<http://supervisord.org/>`_, an excellent process control system
written in Python. In fact, we recommend that you run your machine
agents using this software.

What *pop* is meant to replace is you!

Now, we've already got a language – `Python
<http://www.python.org>`_. All we need is to model the actions that
you would carry out if you were the best possible system
administrator.


Principles
==========

With these principles we try to cover the basic design and philosophy.

#. *Adaptive*. The system is dynamic and the equilibrium is the target
   state. There's always a state and if it's not the target state,
   then we must take the necessary steps to reach that state.

#. *Distributed*. The system is comprised of services running on
   multiple machines. We use Apache's `ZooKeeper
   <http://zookeeper.apache.org/>`_ for "highly reliable distributed
   coordination" (via `txzookeeper
   <http://pypi.python.org/pypi/txzookeeper>`_, a `Twisted
   <http://twistedmatrix.com/trac/>`_ library written for the Ubuntu
   `Juju <https://juju.ubuntu.com/>`_ cloud deployment tool).

#. *Integrated*. This is a Python-based tool for running Python-based
   services. The system is extensible through plugins.

#. *Open*. The system should not be tied to a particular platform.


Installation
============

These steps will be necessary for each machine in the system – except
for the final step which applies only to the machine that should run
ZooKeeper.

We assume that Python 2.7 is installed and available as ``python2``.

#. To get started, log in to a machine, and install *pop* using
   `setuptools <http://pypi.python.org/pypi/setuptools>`_ and
   `virtualenv <http://www.virtualenv.org/>`_::

     $ wget http://peak.telecommunity.com/dist/ez_setup.py
     $ sudo python2 ez_setup.py
     $ sudo easy_install-2.7 virtualenv

   That's it for ``sudo``. We can continue with an unprivileged user.

   Let's install *pop* into an isolated, virtual environment under the
   home directory and enter the environment::

     $ virtualenv --python=python2 ~/pop
     $ source ~/pop/bin/activate
     $ easy_install pop

   This installs the ``pop`` command-line utility as well as
   supporting libraries.

#. Build and install ZooKeeper on the system (see `instructions
   <http://zookeeper.apache.org/doc/trunk/zookeeperStarted.html>`_ for
   more details).

   Make sure your system has `Apache Ant <http://ant.apache.org/>`_
   installed (a build tool for `Java <http://openjdk.java.net/>`_)
   before proceeding::

      $ cd ~/pop
      $ git clone git://git.apache.org/zookeeper.git
      $ cd zookeeper
      $ ant

   First we need to build the C-bindings::

      $ cd src/c
      $ autoreconf -if
      $ ./configure --prefix=~/pop/zookeeper
      $ make && make install

   Then the Python-bindings::

      $ cd ../contrib/zkpython
      $ ant install

   That's it for the installation.

#. Configure and start ZooKeeper::

      $ cd ~/pop/zookeeper/conf
      $ cp zoo_sample.cfg zoo.cfg

   You should edit ``zoo.cfg`` before you start a real deployment
   because the default storage setting is ``/tmp/zookeeper``.

   There's a script included to run the service::

      $ ../bin/zkServer.sh start

   If you want to keep track of what's going on, use
   ``start-foreground``. Note that the ``pop`` utility expects
   ZooKeeper to run on ``localhost`` unless the ``--host`` argument is
   provided.

   If everything's gone to plan, we're ready to use the system.

Tutorial
========

As a first look, in this tutorial we'll learn how to use *pop* to run
a vanilla installation of `Plone <http://www.plone.org>`_.

#. Initialize *pop* namespace::

     $ pop init

   This adds a number of nodes to the hierarchy that *pop* requires
   for its operation. Note that the command effectively resets the
   configuration although this requires the ``--force`` option if
   an existing configuration is in place.

#. Add the ``plone4`` service which runs the latest version of Plone::

     $ pop add plone4

   The service will be set up with the default configuration with the
   name ``"plone4"`` (unless the ``--name`` argument was provided). We
   can confirm this using the ``status`` command::

     $ pop status plone4

   In the default configuration, Plone is set to listen on port
   8080. To change this, use the ``--port`` parameter when you first
   add the service.

#. To make the local machine available as a system that we can run
   services on, we need to start the *machine agent*::

     $ pop start

   This process can also run in the foreground using ``pop fg``.

#. Finally, to deploy the Plone service on the local machine::

     $ pop deploy plone4

   This works because the utility assumes that we want to deploy the
   service on the local machine.

The order of the last two steps is *not* important. We could easily
have deployed the service first, then made the machine available.


State
=====

*Pop* keeps all state in ZooKeeper (ZK).

The table below lists the various paths involved.

=================================================  ==============  ==============  ==============
 Path                                               Data            Format          Type
=================================================  ==============  ==============  ==============
``/machines``
``/machines/<machine-id>``
``/machines/<machine-id>/<service-name>``           PID [#]_        Integer         Ephemeral
``/services``
``/services/<service-name>``
``/services/<service-name>/machines``               Machines [#]_   JSON
``/services/<service-name>/settings``               Settings [#]_   JSON
``/services/<service-name>/state/<machine-id>``     State [#]_      JSON            Ephemeral
=================================================  ==============  ==============  ==============

Notes:

.. [#] The process identifier.

.. [#] This is a list of machines on which the service should run.

.. [#] These are the settings used to bring up the service (regardless
       of the machine). If changed, the service will be restarted.

.. [#] This is set by the service when it's up and running; the
       contents is specific to the implementation, but must be in JSON-format.

Note that an ephemeral node is one that's created using the
``zookeeper.EPHEMERAL`` flag and immediately removed when the creator
disconnects.

Terminology
-----------

Machine identification

    The *machine id* is a hardware UUIDs. On Linux this is the value
    returned by `HAL <http://linux.die.net/man/8/hald>`_ for the
    ``"system.hardware.uuid"`` key.

Service identification

    Each service is required to have a unique *service name* (a string).

Scripts
=======

To carry out tasks such as upgrades, coordinated script execution is
needed.

Plugins can define tasks on a service level and make them available on
the command-line::

  $ pop run <service> <command> [args]

Environment
-----------

The ``PythonEnvironment`` base class comes with a set of tasks that
help to set up the interpreter environment. These are available to all
services that derive from this base class.

1. *Install packages*. To make a Python package available in the
   instance environment::

     $ pop run plone install lxml==2.3.5

   Multiple packages can be listed, separate with space.

2. *List packages*. Return a list of installed Python libraries. For
   each package, print time of installation, source and version::

     $ pop run plone packages


Development
===========

This section documents the development of pop (not *with*).

Tests
-----

To run the automated test suite, you need a running ZooKeeper service
and the `nose <http://nose.readthedocs.org/en/latest/>`_ test runner.

In your ``virtualenv`` environment::

  $ python setup.py nosetests

It's often useful to get a more verbose output::

  $ python setup.py nosetests --verbosity=3

Note that a higher verbosity setting will result in a great amount of
noise from the nose test runner itself.


Acknowledgements and Credits
============================

The architecture and technical implementation of this software was
inspired by Canonical's Juju cloud deployment tool, originally
designed by Kapil Thangavelu. We deliberately use the same terms and
conventions when possible (for example *machines* and *services*).

The author of this software:

  Malthe Borch – mborch@gmail.com


License
=======

*Pop* is available under the GPL.


■


