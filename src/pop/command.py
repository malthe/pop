import os
import sys
import functools

from StringIO import StringIO

from twisted.internet.defer import inlineCallbacks, returnValue
from twisted.internet import defer
from twisted.internet import reactor
from twisted.python.failure import Failure

from txzookeeper.client import ZOO_OPEN_ACL_UNSAFE
from txzookeeper.client import ZookeeperClient

from zookeeper import PERM_ALL
from zookeeper import NodeExistsException

from pop import log
from pop.exceptions import StateException


def zookeeper(func):
    @inlineCallbacks
    def connect_and_invoke(self, args):
        client = self.client = ZookeeperClient(
            "%s:%d" % (args.host, args.port),
            session_timeout=1000
            )

        log.debug("connecting to zookeeper...")
        yield client.connect()

        result = yield inlineCallbacks(func)(self, args)
        yield client.close()
        log.debug("connection closed.")

        returnValue(result)

    def run(func, args):
        d = defer.maybeDeferred(connect_and_invoke, func, args)

        @d.addBoth
        def handle_exit(result, stream=sys.stderr):
            if reactor.running:
                reactor.stop()

            if isinstance(result, Failure):
                if args.verbose > 1:
                    tracebackIO = StringIO()
                    result.printTraceback(file=tracebackIO)
                    log.warn(tracebackIO.getvalue())

                message = result.getErrorMessage()
                for i, line in enumerate(message.split('\n')):
                    line = line[0].lower() + line[1:]

                    if i == 0:
                        line = "error - %s" % line

                    log.error(line)

                os._exit(1)

            name = args.func.__name__.split('_', 1)[-1]
            log.info("done - '%s' completed OK.\n" % name)

        return d

    @functools.wraps(func)
    def decorator(*args):
        reactor.callWhenRunning(run, *args)
        reactor.run()

    return decorator


class Command(object):
    scheme = "digest"
    permissions = PERM_ALL

    client = None

    @zookeeper
    def cmd_init(self, args):
        yield self._initialize_hierarchy(
            args.admin_identity,
            args.force
            )

    @inlineCallbacks
    def _initialize_hierarchy(self, admin_identity, force):
        acls = [{"id": admin_identity,
                 "scheme": self.scheme,
                 "perms": self.permissions,
                 }, ZOO_OPEN_ACL_UNSAFE]

        create = self._create_or_delete if force else \
                 self._create_or_fail

        if force:
            log.warn("using '--force' to initialize hierarchy.")

        yield create("/machines", acls)
        yield create("/services", acls)

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
