import os
import json
import signal
import zookeeper

from twisted.internet.defer import \
     inlineCallbacks, \
     returnValue, \
     succeed

from pop import log
from pop.agent import Agent

from .utils import nodeproperty
from .utils import DeferredDict


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
    kind = nodeproperty("type")

    defaults = {
        'host': '0.0.0.0',
        'port': 8080,
        }

    # Internal attributes.
    _settings = None
    _states = None

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

    def get_settings(self):
        if self._settings is None:
            defaults = {}
            for cls in reversed(type(self).__mro__):
                try:
                    entries = cls.__dict__['defaults']
                except KeyError:
                    continue

                defaults.update(entries)

            settings = self._settings = DeferredDict(
                self.client, self.path + "/settings",
                defaults, json.loads, json.dumps
                )

            d = settings.load()

            @d.addCallback
            def get(metadata):
                return succeed(settings)

            return d

        return succeed(self._settings)

    def get_state(self, machine, watch=False):
        if self._states is None:
            self._states = {}

        state = self._states.get(machine)
        if state is None:
            state = self._states[machine] = DeferredDict(
                self.client, self.path + "/state/" + machine,
                {}, json.loads, json.dumps
                )

            d = state.load(watch=watch)

            @d.addCallback
            def get(metadata):
                return succeed(state)
        else:
            d = succeed(state)

        if watch:
            @d.addCallback
            def _get(state):
                return state, watch

        return d

    def hangup(self, machine):
        path = self.path + "/state/" + machine
        d, watch = self.client.get_and_watch(path)

        try:
            pid, metadata = yield d
        except zookeeper.NoNodeException:
            raise ValueError("Service not running on this machine.")

        yield watch

    def register(self, machine, **state):
        return self.client.create(
            self.path + "/state/" + machine,
            json.dumps(state),
            flags=zookeeper.EPHEMERAL,
            )

    @inlineCallbacks
    def add(self):
        """Add service definition to hierarchy."""

        yield self.client.create(self.path)
        yield self.client.create(self.path + "/type", self.name)
        yield self.client.create(self.path + "/state")
        yield self.client.create(self.path + "/machines", "[]")

        log.debug("registered service '%s' at %s." % (self.name, self.path))

    def save(self):
        return self.settings.save()


class PythonService(Service):
    """Base class for Python-based services."""


class PythonNetworkService(PythonService):
    """Base class for Python-based network services."""

    port = None

    def register(self, machine, **state):
        assert self.port is not None

        return super(PythonNetworkService, self).register(
            machine, port=self.port, **state)
