import os
import json
import signal

import zookeeper

from twisted.internet.defer import \
     inlineCallbacks, \
     returnValue

from pop import log
from pop.agent import Agent

from .utils import nodeproperty


class Service(Agent):
    """Base service class.

    Note that at the implementation level, service instances are not
    named as such. Instead, a service path argument is given to the
    constructor.

    The ``name`` and ``description`` attributes pertain to the service
    implementation.
    """

    name = None
    description = None

    @inlineCallbacks
    def deploy(self, machine):
        """Deploy service."""

        log.debug("machine id: %s." % machine)

        path = self.path + "/machines"
        value, metadata = yield self.client.get(path)
        machines = json.loads(value)
        machines.append(machine)

        yield self.client.set(path, json.dumps(machines))

    @inlineCallbacks
    def get_process_id(self, machine):
        """Return process id for service running on provided machine."""

        d = self.client.get(self.path + "/machines/" + machine)
        pid, metadata = yield d
        returnValue(pid)

    @inlineCallbacks
    def hangup(self, machine):
        path = self.path + "/machines/" + machine
        d, watch = self.client.get_and_watch(path)

        try:
            pid, metadata = yield d
        except zookeeper.NoNodeException:
            raise ValueError("Service not running on this machine.")

        os.kill(int(pid), signal.SIGHUP)
        yield watch

    @inlineCallbacks
    def register(self, machine):
        """Register service for machine."""

        yield self.client.create(
            self.path + "/machines/" + machine,
            str(os.getpid()),
            flags=zookeeper.EPHEMERAL
            )

    @inlineCallbacks
    def add(self):
        """Add service definition to hierarchy."""

        yield self.client.create(self.path)
        yield self.client.create(self.path + "/type", self.name)
        yield self.client.create(self.path + "/machines", "[]")

        log.debug("registered service '%s' at %s." % (self.name, self.path))


class PythonService(Service):
    """Base class for Python-based services."""


class PythonNetworkService(PythonService):
    """Base class for Python-based network services."""

    host = nodeproperty("host", "localhost")
    port = nodeproperty("port", 8080, int)
