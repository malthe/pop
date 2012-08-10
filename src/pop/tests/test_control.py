from functools import wraps
from logging import ERROR
from uuid import uuid4

from twisted.internet.defer import maybeDeferred, inlineCallbacks, returnValue
from pop.exceptions import StateException

from .common import TestCase

def capture(test):
    @wraps(test)
    def decorator(self, *args):
        log = self.capture_logging(level=ERROR)
        return test(self, log, *args)
    return decorator


class ControlTestCase(TestCase):
    path = "/"

    def setUp(self):
        super(ControlTestCase, self).setUp()

        # To avoid overriding existing data in ZooKeeper, we prefix
        # the hierarchy with a random path.
        self.path = "/%s" % str(uuid4())

    def tearDown(self):
        # This is a bit of a hack, but we don't want this method to be
        # exposed as a proper command.
        args = self.parse("init")
        command = args.func.im_self
        # command.cmd_purge(args)

        super(ControlTestCase, self).tearDown()

    @inlineCallbacks
    def cmd(self, *args):
        args = self.parse(*args)
        result = yield args.func(args)
        returnValue(result)

    def parse(self, *args):
        args = ('--path', self.path, ) + args
        from pop.control import parse
        return parse(args)

    def assertContains(self, text, log):
        value = log.getvalue()
        self.assertIn(
            text, value, (
                "%r not contained in output!" +
                "\n\n" +
                "-------------------- >> " +
                "begin captured logging << " +
                "--------------------\n" +
                value.rstrip('\n') + "\n"
                "--------------------- >> " +
                "end captured logging << " +
                "---------------------"
                ) % text
            )


class InitializationTest(ControlTestCase):
    @capture
    @inlineCallbacks
    def test_bare_invocation(self, log):
        result = yield self.cmd("init")
        self.assertIs(result, None)

    @capture
    @inlineCallbacks
    def test_repeat_bare_invocation(self, log):
        yield self.cmd("init")
        yield self.assertFailure(
            self.cmd("init"),
            StateException,
            )

    @capture
    @inlineCallbacks
    def test_repeat_invocation_using_force(self, log):
        yield self.cmd("init")
        result = yield self.cmd("--force", "init")
        self.assertIs(result, None)


class DumpTest(ControlTestCase):
    @inlineCallbacks
    def test_bare_invocation(self):
        stream = self.capture_stream("stdout")
        yield self.cmd("dump")
        self.assertEquals(stream.getvalue(), '{}\n')
