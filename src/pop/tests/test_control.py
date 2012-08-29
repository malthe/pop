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
        super(ControlTestCase, self).setUp()

        # To avoid overriding existing data in ZooKeeper, we prefix
        # the hierarchy with a random path.
        self.path = "/pop-%d/" % (int(time.time() * 1000) % (10 ** 6))

        # Always capture log
        self.log = self.capture_logging(level=DEBUG)

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

    # def assertContains(self, text, log):
    #     value = log.getvalue()
    #     self.assertIn(
    #         text, value, (
    #             "%r not contained in output!" +
    #             "\n\n" +
    #             "-------------------- >> " +
    #             "begin captured logging << " +
    #             "--------------------\n" +
    #             value.rstrip('\n') + "\n"
    #             "--------------------- >> " +
    #             "end captured logging << " +
    #             "---------------------"
    #             ) % text
    #         )


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
    pids = ()

    def tearDown(self):
        for pid in self.pids:
            os.kill(pid, signal.SIGKILL)

        for call in self.reactor.getDelayedCalls():
            if call.func.__name__ == 'reconnector':
                call.cancel()

        logged = "\n".join(
            (">>> %s" % line for line in
             self.log.getvalue().strip().split('\n')
             if line.strip()
             ))

        if logged and getLogger("nose").level <= INFO:
            sys.stderr.write("\n" + logged + "\n")

        return super(ServiceTest, self).tearDown()

    def get_machine_agent(self):
        from pop.utils import local_machine_uuid
        uuid = local_machine_uuid()

        client = self.get_client()

        from pop.machine import MachineAgent
        return MachineAgent(client, self.path[:-1], uuid)

    @inlineCallbacks
    def test_threaded_echo_service(self):
        yield self.cmd("init")
        yield self.cmd("add --name echo threaded-echo --port 0")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(1.5)
        state = yield self.wait_for_service("echo")

        try:
            yield self.verify_echo_service(state['port'])
        finally:
            yield agent.close()

    @inlineCallbacks
    def test_twisted_echo_service(self):
        yield self.cmd("init")
        yield self.cmd("add --name echo twisted-echo --port 0")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(0.5)
        state = yield self.wait_for_service("echo")

        try:
            yield self.verify_echo_service(state['port'])
        finally:
            yield agent.close()

    @inlineCallbacks
    def test_twisted_echo_service_stop_and_start(self):
        yield self.cmd("init")
        yield self.cmd("add --name echo twisted-echo --port 0")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(0.5)
        state = yield self.wait_for_service("echo")

        yield self.cmd("stop", "echo")

        try:
            yield self.verify_echo_service(state['port'], False)
        finally:
            yield agent.close()

    @inlineCallbacks
    def verify_echo_service(self, port, status=True):
        received = []

        from pop.tests.utils import create_echo_client
        factory = create_echo_client(received)

        connector = self.reactor.connectTCP('127.0.0.1', port, factory)

        def deferred():
            connector.disconnect()

            assertion = self.assertEqual if status \
                        else self.assertNotEqual

            assertion(
                " ".join(received),
                'Hello, world! What a fine day it is. Bye-bye!'
                )

        yield deferLater(self.reactor, 1.0, deferred)

    @inlineCallbacks
    def run_machine(self, time):
        agent = self.get_machine_agent()
        yield agent.connect()

        from pop.exceptions import ServiceException

        try:
            self.pids = yield agent.run()
        except ServiceException as exc:
            client = yield self.cmd("start", str(exc))

            @inlineCallbacks
            def stop():
                yield client.close()
                self.reactor.stop()
                os._exit(0)

            yield deferLater(self.reactor, time, stop)

        returnValue(agent)

    @inlineCallbacks
    def wait_for_service(self, name):
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
