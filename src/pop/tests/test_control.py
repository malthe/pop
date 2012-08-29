import os
import sys
import json
import time
import signal

from logging import DEBUG
from logging import INFO
from logging import getLogger

from twisted.internet.task import deferLater

from twisted.internet.defer import \
     inlineCallbacks, \
     returnValue

from pop.exceptions import StateException

from .common import TestCase


class ControlTestCase(TestCase):
    path = "/"
    host = 'localhost'
    port = 2181
    timeout = 2.0

    def setUp(self):
        # To avoid overriding existing data in ZooKeeper, we prefix
        # the hierarchy with a random path.
        self.path = "/pop-%d/" % (int(time.time() * 1000))

        # Always capture log
        self.log = self.capture_logging(level=DEBUG)

        return super(ControlTestCase, self).setUp()

    @inlineCallbacks
    def tearDown(self):
        client = self.get_client()

        yield client.connect()
        yield client.recursive_delete(self.path[:-1])
        yield client.close()

        super(ControlTestCase, self).tearDown()

    def get_client(self):
        from pop.client import ZookeeperClient
        return ZookeeperClient(
            "%s:%d" % (self.host, self.port),
            session_timeout=100
            )

    @inlineCallbacks
    def cmd(self, *args):
        _args = []
        for arg in args:
            arg = str(arg)
            _args.extend(arg.split())

        args = self.parse(*_args)
        d = args.__dict__
        del d['verbosity']
        func = d.pop('func')
        result = yield func(d)
        returnValue(result)

    def parse(self, *args):
        args = ('--path', self.path,
                '--host', self.host,
                '--port', str(self.port)) + \
                args

        from pop.control import parse
        return parse(args)


class InitializationTest(ControlTestCase):
    @inlineCallbacks
    def test_bare_invocation(self):
        yield self.cmd("init")

    @inlineCallbacks
    def test_repeat_bare_invocation(self):
        yield self.cmd("init")
        yield self.assertFailure(
            self.cmd("init"),
            StateException,
            )

    @inlineCallbacks
    def test_repeat_invocation_using_force(self):
        yield self.cmd("init")
        yield self.cmd("--force", "init")


class DumpTest(ControlTestCase):
    @inlineCallbacks
    def test_bare_invocation(self):
        stream = self.capture_stream("stdout")
        yield self.cmd("dump")
        self.assertEquals(stream.getvalue(), '{}\n')


class ServiceTest(ControlTestCase):
    @inlineCallbacks
    def setUp(self):
        yield super(ServiceTest, self).setUp()

        # Global state initialization.
        yield self.cmd("init")

        # Connect local machine agent.
        agent = self.agent = self.get_machine_agent()
        yield agent.connect()
        yield agent.initialize()

        self.pids = []

    @inlineCallbacks
    def tearDown(self):
        # First, close down agent connection.
        yield self.agent.close()

        # Then kill any child processes.
        for pid in self.pids:
            os.kill(pid, signal.SIGKILL)

        # Just in case, cancel any deferred reconnectors.
        for call in self.reactor.getDelayedCalls():
            if call.func.__name__ == 'reconnector':
                call.cancel()

        # If verbosity is above the threshold level, send the logged
        # text to the standard error stream.
        if getLogger("nose").level <= INFO:
            logged = "\n".join(
                (">>> %s" % line for line in
                 self.log.getvalue().strip().split('\n')
                 if line.strip()
                 ))

            if logged:
                sys.stderr.write("\n" + logged + "\n")

        yield super(ServiceTest, self).tearDown()

    @inlineCallbacks
    def test_threaded_echo_service(self):
        yield self.cmd("add --name echo threaded-echo --port 0")
        yield self.cmd("deploy", "echo")
        yield self.run_services(0.5)
        state = yield self.wait_for_service("echo")
        result = yield self.verify_echo_service(state['port'])
        self.assertEqual(result, 'Hello world! What a fine day it is. Bye!')

    @inlineCallbacks
    def test_twisted_echo_service(self):
        yield self.cmd("add --name echo twisted-echo --port 0")
        yield self.cmd("deploy", "echo")
        yield self.run_services(0.5)
        state = yield self.wait_for_service("echo")
        result = yield self.verify_echo_service(state['port'])
        self.assertEqual(result, 'Hello world! What a fine day it is. Bye!')

    @inlineCallbacks
    def test_twisted_echo_service_stop_and_start(self):
        yield self.cmd("add --name echo twisted-echo --port 0")
        yield self.cmd("deploy", "echo")
        yield self.run_services(0.5)
        state = yield self.wait_for_service("echo")
        yield self.cmd("stop", "echo")
        result = yield self.verify_echo_service(state['port'])
        self.assertNotEqual(result, 'Hello world! What a fine day it is. Bye!')

    def get_machine_agent(self):
        assert self.path != "/"
        from pop.utils import local_machine_uuid
        uuid = local_machine_uuid()
        client = self.get_client()
        from pop.machine import MachineAgent
        return MachineAgent(client, self.path[:-1], uuid)

    @inlineCallbacks
    def verify_echo_service(self, port):
        received = []
        from pop.tests.utils import create_echo_client
        factory = create_echo_client(received)
        connector = self.reactor.connectTCP('127.0.0.1', port, factory)

        def deferred(received=received):
            connector.disconnect()
            returnValue(" ".join(received))

        yield deferLater(self.reactor, 1.0, deferred)

    @inlineCallbacks
    def run_services(self, time):
        """Run configured services on local machine agent.

        Services are stopped after the provided time has elapsed.
        """

        from pop.exceptions import ServiceException

        try:
            pids = yield self.start_services()
            self.pids.extend(pids)

        except ServiceException as exc:
            client = yield self.cmd("start", str(exc))

            @inlineCallbacks
            def stop():
                yield client.close()
                self.reactor.stop()
                os._exit(0)

            yield deferLater(self.reactor, time, stop)

    @inlineCallbacks
    def start_services(self, attempts=0, maximum=1, delay=0.1):
        """Scan and start the services not already running."""

        yield self.agent.scan()
        pids = self.agent.start_services()

        if not pids and attempts < maximum:
            pids = yield deferLater(
                self.reactor, delay, self.start_services, attempts + 1
                )

        returnValue(pids)

    @inlineCallbacks
    def wait_for_service(self, name):
        """Wait for a service to appear and return state."""

        client = self.get_client()

        from pop.utils import local_machine_uuid
        uuid = local_machine_uuid()

        yield client.connect()

        path = self.path + "services/" + name + "/state"

        value, metadata = yield client.get_or_wait(
            path, str(uuid)
            )

        yield client.close()

        state = json.loads(value)
        returnValue(state)
