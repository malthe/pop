from twisted.internet.protocol import ReconnectingClientFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet.defer import Deferred


def create_echo_client(received):
    disconnected = Deferred()

    class EchoClient(LineReceiver):
        end = "Bye!"

        def connectionMade(self):
            self.sendLine("Hello world!")
            self.sendLine("What a fine day it is.")
            self.sendLine(self.end)

        def connectionLost(self, reason):
            pass

        def lineReceived(self, line):
            received.append(line)

            if line == self.end:
                self.transport.loseConnection()

    class EchoClientFactory(ReconnectingClientFactory):
        initialDelay = delay = 0.1
        protocol = EchoClient

        def clientConnectionLost(self, connector, reason):
            self.stopTrying()
            disconnected.callback(self)

    return EchoClientFactory()
