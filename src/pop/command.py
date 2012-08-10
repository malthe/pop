import sys
import functools

from StringIO import StringIO

from twisted.internet.defer import inlineCallbacks
from twisted.internet.defer import returnValue

from twisted.internet.defer import maybeDeferred

from twisted.python.failure import Failure

from txzookeeper.client import ZOO_OPEN_ACL_UNSAFE
from txzookeeper.client import ZookeeperClient

from zookeeper import PERM_ALL
from zookeeper import NodeExistsException

from pop import log
from pop.exceptions import StateException


def run(options):
    from twisted.internet import reactor

    def wrapper():
        d = maybeDeferred(options.func, options)

        @d.addBoth
        def handle_exit(result, stream=sys.stderr, reactor=reactor):
            if isinstance(result, Failure):
                if options.verbose > 1:
                    tracebackIO = StringIO()
                    result.printTraceback(file=tracebackIO)
                    log.warn(tracebackIO.getvalue())

                message = result.getErrorMessage()
                for i, line in enumerate(message.split('\n')):
                    line = line[0].lower() + line[1:]

                    if i == 0:
                        line = "error - %s" % line

                    log.error(line)
            else:
                name = options.func.__name__.split('_', 1)[-1]
                log.info("done - '%s' completed OK.\n" % name)

            if reactor.running:
                reactor.stop()

        return d

    reactor.callWhenRunning(wrapper)
    reactor.run()


def constructor(func):
    """Decorator that wraps a command action in a class constructor."""

    @functools.wraps(func)
    def decorator(factory, options):
        command = factory(options)
        return maybeDeferred(func, command)

    return classmethod(decorator)


def connected(func):
    @inlineCallbacks
    @functools.wraps(func)
    def decorator(command, *args):
        log.debug("connecting to zookeeper...")
        yield command.client.connect()
        log.debug("connected.")
        result = yield func(command, *args)
        try:
            returnValue(result)
        finally:
            yield command.client.close()
            log.debug("connection closed.")

    return decorator


def twisted(func):
    return constructor(connected(inlineCallbacks(func)))


class Command(object):
    scheme = "digest"
    permissions = PERM_ALL

    client = None
    path = None

    def __init__(self, options):
        self.options = options
        self.client = self.get_client()

    def get_client(self):
        """Return ZooKeeper client."""

        return ZookeeperClient(
            "%s:%d" % (self.options.host, self.options.port),
            session_timeout=1000
            )

    @property
    def path(self):
        """Return path prefix."""

        return self.options.path_prefix

    @twisted
    def cmd_init(self):
        yield self._initialize_hierarchy(
            self.options.admin_identity,
            self.options.force
            )

    @twisted
    def cmd_purge(self):
        yield self.client.delete(self.path)

    @inlineCallbacks
    def _initialize_hierarchy(self, admin_identity, force):
        acls = [{"id": admin_identity,
                 "scheme": self.scheme,
                 "perms": self.permissions,
                 }, ZOO_OPEN_ACL_UNSAFE]

        create = self._create_or_delete if force else \
                 self._create_or_fail

        # If the hierarchy root path is non-trivial, we create it
        # immediately. Note that this is currently only imagined
        # useful for automated testing.
        if self.path != "/":
            assert self.path.count("/") == 1
            try:
                yield self.client.create(self.path, acls=acls)
            except NodeExistsException:
                pass

        if force:
            log.warn("using '--force' to initialize hierarchy.")

        yield create(self.path + "machines", acls)
        yield create(self.path + "services", acls)

    @inlineCallbacks
    def _create_or_delete(self, path, acls):
        try:
            yield self.client.create(path, acls=acls)
        except NodeExistsException:
            names = yield self.client.get_children(path)
            for name in names:
                yield self.client.delete("%s/%s" % (path, name))

    @inlineCallbacks
    def _create_or_fail(self, path, acls):
        try:
            yield self.client.create(path, acls=acls)
        except NodeExistsException as exc:
            raise StateException(
                "%s!\nIf you're sure, run command again "
                "with '--force'." % exc
                )
