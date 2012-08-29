import json

from pop import log
from pop.agent import Agent
from pop.exceptions import ProcessForked
from pop.exceptions import ServiceException
from pop.process import fork

from twisted.internet.defer import returnValue
from twisted.internet.defer import inlineCallbacks

from zookeeper import NoNodeException


class MachineAgent(Agent):
    """Machine agent implementation."""

    def __init__(self, client, path, uuid):
        super(MachineAgent, self).__init__(client, path)

        self.name = str(uuid)
        self.stopped = set()
        self.pids = []

    @inlineCallbacks
    def initialize(self):
        """Create machine state node."""

        yield self.client.create_path(
            self.path + "/machines/" + self.name + "/services"
            )

    @inlineCallbacks
    def scan(self):
        """Analyze state and queue tasks."""

        log.debug("scanning machine: %s..." % self.name)

        deployed = set()
        services = yield self.client.get_children(self.path + "/services")

        for name in services:
            log.debug("checking service: '%s'..." % name)

            try:
                value, metadata = yield self.client.get(
                    self.path + "/services/" + name + "/machines"
                    )
            except NoNodeException:
                log.warn(
                    "missing machines declaration for service: %s." %
                    name
                    )
                machines = []
            else:
                machines = json.loads(value)

            if machines:
                log.debug("machines: %s." % ", ".join(machines))

                if self.name in machines:
                    deployed.add(name)
            else:
                log.debug("service not configured for any machine.")

        count = len(deployed)
        log.debug("found %d service(s) configured for this machine." % count)

        running = yield self.client.get_children(
            self.path + "/machines/" + self.name
            )

        self.stopped = deployed - set(running)

        if self.stopped:
            log.debug("services not running: %s." % ", ".join(
                map(repr, self.stopped)))
        elif running:
            log.debug("all services are up.")

    @inlineCallbacks
    def run(self):
        pids = self.start_services()
        returnValue(pids)

    @inlineCallbacks
    def start(self):
        yield self.initialize()
        yield self.scan()

    def start_services(self):
        pids = []
        for service in self.stopped:
            log.debug("starting service: %s..." % service)
            try:
                pid = fork()
            except ProcessForked:
                raise ServiceException(service)

            log.info("process started: %d." % pid)
            pids.append(pid)

        return pids
