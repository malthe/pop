from twisted.internet.defer import inlineCallbacks

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
        yield self.client.create(self.path + "/machines/" + machine)

    @inlineCallbacks
    def register(self):
        """Register service."""

        yield self.client.create(self.path)
        yield self.client.create(self.path + "/type", self.name)
        yield self.client.create(self.path + "/machines")

        log.debug("registered service '%s' at %s." % (self.name, self.path))


class PythonService(Service):
    """Base class for Python-based services."""


class PythonNetworkService(PythonService):
    """Base class for Python-based network services."""

    host = nodeproperty("host", "localhost")
    port = nodeproperty("port", 8080)
