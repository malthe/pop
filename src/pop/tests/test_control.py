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
        result = yield self.cmd("init")
        self.assertIs(result, None)

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
        result = yield self.cmd("--force", "init")
        self.assertIs(result, None)


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

        from twisted.internet import reactor
        for call in reactor.getDelayedCalls():
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
    def test_echo_service(self):
        yield self.cmd("init")
        yield self.cmd("add", "--name", "echo", "socket-based-echo")
        yield self.cmd("deploy", "echo")

        agent = self.get_machine_agent()
        yield agent.connect()

        from twisted.internet import reactor
        from pop.exceptions import ServiceException

        try:
            try:
                self.pids = yield agent.run()
            except ServiceException as exc:
                yield self.cmd("start", str(exc))
                deferred = reactor.stop
            else:
                from pop.tests.utils import create_echo_client
                received = []
                factory = create_echo_client(received)
                connector = reactor.connectTCP('127.0.0.1', 8080, factory)

                def deferred():
                    connector.disconnect()

                    self.assertEqual(
                        " ".join(received),
                        'Hello, world! What a fine day it is. Bye-bye!'
                        )

            yield deferLater(reactor, 0.3, deferred)
        finally:
            yield agent.close()
