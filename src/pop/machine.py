import os
import json

from pop import log
from pop.agent import Agent
from pop.exceptions import ServiceException


from twisted.internet.defer import returnValue
from twisted.internet.defer import inlineCallbacks

from zookeeper import NodeExistsException
from zookeeper import NoNodeException


class MachineAgent(Agent):
    """Machine agent implementation."""

    def __init__(self, client, path, uuid):
        super(MachineAgent, self).__init__(client, path)

        self.name = str(uuid)
        self.stopped = set()

    @inlineCallbacks
    def initialize(self):
        """Create machine state node."""

        yield self.client.create_multiple(
            self.path + "/machines/" + self.name,
            self.path + "/machines/" + self.name + "/services"
            )

    @inlineCallbacks
    def scan(self):
        """Analyze state and queue tasks."""

        deployed = set()
        services = yield self.client.get_children(self.path + "/services")

        for name in services:
            log.debug("scanning service: '%s'..." % name)

            value, metadata = yield self.client.get(
                self.path + "/services/" + name + "/machines"
                )

            machines = json.loads(value)

            if self.name in machines:
                deployed.add(name)

        count = len(deployed)
        log.debug("found %d services deployed for this machine." % count)

        running = yield self.client.get_children(
            self.path + "/machines/" + self.name + "/services"
            )

        self.stopped = deployed - set(running)

    @inlineCallbacks
    def run(self):
        yield self.initialize()
        yield self.scan()

        pids = []
        for service in self.stopped:
            pid = os.fork()
            if not pid:
                raise ServiceException(service)

            pids.append(pid)

        returnValue(pids)
