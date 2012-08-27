import os
import sys
import signal

from functools import wraps
from logging import INFO
from uuid import uuid4

from twisted.internet.task import deferLater

from twisted.internet.defer import \
     inlineCallbacks, \
     returnValue, \
     Deferred

from pop.exceptions import StateException

from .common import TestCase


class ControlTestCase(TestCase):
    path = "/"
    host = 'localhost'
    port = 2181

    def setUp(self):
        super(ControlTestCase, self).setUp()

        # To avoid overriding existing data in ZooKeeper, we prefix
        # the hierarchy with a random path.
        self.path = "/%s/" % str(uuid4())

        # Always capture log
        self.log = self.capture_logging(level=INFO)

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

    # def get_command(self, services={}, **kwargs):
    #     client = self.get_client()
    #     from pop.command import Command
    #     return Command(client, self.path, {}, **kwargs)

    @inlineCallbacks
    def cmd(self, *args):
        args = self.parse(*args)
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
        yield self.cmd("add", "--name", "echo", "threaded-echo")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(0.5)

        try:
            yield self.verify_echo_service()
        finally:
            yield agent.close()

    @inlineCallbacks
    def test_twisted_echo_service(self):
        yield self.cmd("init")
        yield self.cmd("add", "--name", "echo", "twisted-echo")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(0.5)

        try:
            yield self.verify_echo_service()
        finally:
            yield agent.close()

    @inlineCallbacks
    def test_twisted_echo_service_stop_and_start(self):
        yield self.cmd("init")
        yield self.cmd("add", "--name", "echo", "twisted-echo")
        yield self.cmd("deploy", "echo")

        agent = yield self.run_machine(1.0)
        yield self.sleep(0.5)
        yield self.cmd("stop", "echo")

        try:
            yield self.verify_echo_service(False)
        finally:
            yield agent.close()

    def verify_echo_service(self, status=True):
        received = []

        from pop.tests.utils import create_echo_client
        factory = create_echo_client(received)

        connector = self.reactor.connectTCP('127.0.0.1', 8080, factory)

        def deferred():
            connector.disconnect()

            assertion = self.assertEqual if status \
                        else self.assertNotEqual

            assertion(
                " ".join(received),
                'Hello, world! What a fine day it is. Bye-bye!'
                )

        return deferLater(self.reactor, 0.5, deferred)

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
