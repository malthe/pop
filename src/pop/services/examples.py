import socket
import threading

from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.internet.protocol import Protocol, Factory

from pop.services.common import PythonNetworkService
from pop.services import register
from pop import log


class Echo(Protocol):
    def dataReceived(self, data):
        self.transport.write(data)


@register
class ThreadedEchoService(PythonNetworkService):
    name = "threaded-echo"

    running = False
    stop = None

    backlog = 5
    size = 1024

    @inlineCallbacks
    def start(self):
        assert self.running is False

        host = yield self.host
        port = yield self.port

        yield self._spawn_thread(host, port)

    def _spawn_thread(self, host, port):
        d = Deferred()

        def start(s):
            d.callback(s)
            s.settimeout(0.1)

            try:
                s.bind((host, port))
            except socket.error as exc:
                log.fatal(exc)
                return

            s.listen(self.backlog)
            self.running = True

            while 1:
                try:
                    client, address = s.accept()

                    data = client.recv(self.size)
                    if data:
                        client.send(data)

                    client.close()
                except socket.timeout as exc:
                    log.debug(exc)
                except socket.error as exc:
                    log.info(exc)
                    break

            s.close()
            self.running = False

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        def stop():
            del self.stop
            s.shutdown()

        self.stop = stop

        thread = threading.Thread(target=start, args=(s, ))
        thread.daemon = True
        thread.start()

        return d


@register
class TwistedEchoService(PythonNetworkService):
    name = "twisted-echo"

    running = False
    stop = None

    @inlineCallbacks
    def start(self):
        assert self.running is False

        host = yield self.host
        port = yield self.port

        f = Factory()
        f.protocol = Echo

        from twisted.internet import reactor
        tcp = reactor.listenTCP(port, f, interface=host)
        self.running = True

        def stop():
            self.running = False
            return tcp.stopListening()

        self.stop = stop

        yield tcp
