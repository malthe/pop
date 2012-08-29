import os
import sys
import shutil
import signal
import functools

from StringIO import StringIO

from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue
from twisted.python.failure import Failure

from txzookeeper.client import ZOO_OPEN_ACL_UNSAFE

from zookeeper import PERM_ALL
from zookeeper import NodeExistsException

from pop import log
from pop.utils import YAMLState
from pop.utils import local_machine_uuid
from pop.exceptions import StateException
from pop.exceptions import ServiceException
from pop.machine import MachineAgent


def run(func, debug, options):
    from twisted.internet import reactor

    def wrapper():
        d = func(options)

        @d.addCallback
        def disconnect(client):
            return client.close()

        @d.addBoth
        def handle_exit(result, stream=sys.stderr, reactor=reactor):
            if isinstance(result, Failure):
                if debug:
                    tracebackIO = StringIO()
                    result.printTraceback(file=tracebackIO)
                    log.warn(tracebackIO.getvalue())

                message = result.getErrorMessage()
                for i, line in enumerate(message.split('\n')):
                    line = line[0:1].lower() + line[1:]

                    if i == 0:
                        line = "error - %s." % line.rstrip('.')

                    log.error(line)
            else:
                name = func.__name__.split('_', 1)[-1]
                log.debug("done - '%s' completed OK.\n" % name)

            if reactor.running:
                reactor.stop()

        return d

    reactor.callWhenRunning(wrapper)
    reactor.run()


def connected(func):
    @inlineCallbacks
    @functools.wraps(func)
    def decorator(command, **kwargs):
        log.debug("%s(%s)" % (
            func.__name__,
            ", ".join(("%s=%r" % args for args in kwargs.items()))
            ))

        log.debug("connecting to zookeeper...")
        yield command.client.connect()
        log.debug("connected.")
        yield func(command, **kwargs)
        returnValue(command.client)
        log.debug("connection closed.")
    return decorator


def twisted(func):
    return connected(inlineCallbacks(func))


class Command(object):
    scheme = "digest"
    permissions = PERM_ALL

    client = None
    path = None

    def __init__(self, client, path, services, force=False):
        assert path.endswith("/")

        self.client = client
        self.path = path
        self.services = services
        self.force = force

    @inlineCallbacks
    def get_service(self, name):
        path = self.get_service_path(name)
        factory_name, metadata = yield self.client.get(path + "/type")
        factory = self.get_service_factory(factory_name)
        service = factory(self.client, path)
        returnValue(service)

    def get_service_path(self, name):
        return self.path + "services/" + name

    def get_service_factory(self, name):
        try:
            return self.services[name]
        except KeyError:
            raise KeyError(
                "No such service type: %s." % name
                )

    @twisted
    def cmd_add(self, name, factory_name, **options):
        if name is None:
            log.info("using name: '%s'." % factory_name)
            name = factory_name

        path = self.get_service_path(name)
        factory = self.get_service_factory(factory_name)
        service = factory(self.client, path)
        yield service.add()

        if options:
            settings = yield service.get_settings()
            settings.update(options)
            yield settings.save()

    @twisted
    def cmd_fg(self):
        uuid = local_machine_uuid()
        agent = MachineAgent(self.client, self.path, uuid)
        try:
            yield agent.run()
        except ServiceException as exc:
            name = str(exc)
            yield self.cmd_start(name)

    @twisted
    def cmd_deploy(self, machine, name):
        service = yield self.get_service(name)

        if machine is None:
            log.info("deploying to local machine.")
            uuid = local_machine_uuid()
            machine = str(uuid)

        yield service.deploy(machine)
        log.info("service deployment registered.")

    @twisted
    def cmd_dump(self, format):
        assert format == 'yaml'
        path = self.path if self.path == "/" else self.path[:-1]
        state = YAMLState(self.client, path)
        yield state.read()
        stream = state.dump()
        stream.seek(0)
        shutil.copyfileobj(stream, sys.stdout)
        log.info("state output to stdout (%d bytes)." % stream.tell())

    @twisted
    def cmd_init(self, admin_identity):
        yield self._initialize_hierarchy(admin_identity)

    @twisted
    def cmd_start(self, name):
        uuid = local_machine_uuid()
        machine = str(uuid)

        service = yield self.get_service(name)
        log.info("starting service: %r..." % name)
        yield service.start()

        log.debug("registering service on machine: %s..." % machine)
        yield service.register(machine, pid=os.getpid())

        def stop(signum, frame, service=service):
            from twisted.internet import reactor
            reactor.callWhenRunning(service.stop)

        signal.signal(signal.SIGHUP, stop)

    @twisted
    def cmd_status(self):
        path = self.path + "services/" + self.options.name
        t, metadata = yield self.client.get(path + "/type")
        machines = yield self.client.get_children(path + "/machines")
        sys.stdout.write("status:   %s\n" % self.options.name)
        sys.stdout.write("type:     %s\n" % t)
        if machines:
            sys.stdout.write("machines: %s\n" % ", ".join(machines))
        else:
            sys.stdout.write("machines: -\n")

    @twisted
    def cmd_stop(self, name):
        service = yield self.get_service(name)
        uuid = local_machine_uuid()
        machine = str(uuid)

        state, watch = yield service.get_state(machine, True)
        pid = state.get('pid')

        if pid is None:
            log.info("no pid found; service probably not running.")
        else:
            log.debug("sending SIGHUP to process: %d." % state['pid'])
            os.kill(state['pid'], signal.SIGHUP)

            log.debug("waiting for ephemeral node to disappear...")
            yield watch

    @inlineCallbacks
    def _initialize_hierarchy(self, admin_identity):
        acls = [{"id": admin_identity,
                 "scheme": self.scheme,
                 "perms": self.permissions,
                 }, ZOO_OPEN_ACL_UNSAFE]

        create = self.client.create_or_clear if self.force else \
                 self.client.create

        # If the hierarchy root path is non-trivial, we create it
        # immediately. Note that this is currently only imagined
        # useful for automated testing.
        if self.path != "/":
            path = self.path.rstrip("/")
            assert path.count("/") == 1
            try:
                yield self.client.create(path, acls=acls)
            except NodeExistsException:
                pass

        if self.force:
            log.warn("using '--force' to initialize hierarchy.")

        try:
            yield create(self.path + "machines", acls=acls)
            yield create(self.path + "services", acls=acls)
        except NodeExistsException as exc:
            if self.force:
                raise

            raise StateException(
                "%s!\nIf you're sure, run command again "
                "with '--force'." % exc
                )
