import socket
import threading

from twisted.internet.defer import inlineCallbacks, Deferred, returnValue
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

    stop = None

    backlog = 5
    size = 1024

    @inlineCallbacks
    def start(self):
        settings = yield self.get_settings()
        deferred = self._spawn(settings['host'], settings['port'])
        host, port = yield deferred
        returnValue({'host': host, 'port': port})

    def _spawn(self, host, port):
        d = Deferred()

        def start(s, host=host, port=port):
            s.settimeout(0.1)

            try:
                s.bind((host, port))
            except socket.error as exc:
                log.fatal(exc)
                return

            if port == 0:
                host, port = s.getsockname()

            d.callback((host, port))

            s.listen(self.backlog)

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

    stop = None

    @inlineCallbacks
    def start(self):
        settings = yield self.get_settings()

        f = Factory()
        f.protocol = Echo

        from twisted.internet import reactor
        p = reactor.listenTCP(settings['port'], f, interface=settings['host'])
        self.stop = p.stopListening

        host, port = p.socket.getsockname()
        returnValue({'host': host, 'port': port})
