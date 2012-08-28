from twisted.internet import defer
from twisted.internet.defer import returnValue
from twisted.internet.defer import inlineCallbacks
from twisted.python.failure import Failure

from zookeeper import NoNodeException


def nodeproperty(path, default=None, typecast=str):
    @property
    @inlineCallbacks
    def prop(self):
        try:
            value, metadata = yield self.client.get(self.path + path)
        except NoNodeException:
            value = default

        value = typecast(value)
        returnValue(value)

    return prop


def dictproperty(path, loads, dumps):
    masked = "_" + path.replace('/', '_')

    @property
    def prop(self):
        try:
            value = getattr(self, masked)
            return defer.success(value)
        except AttributeError:
            value = DeferredDict(self.client, self.path + path, loads, dumps)
            setattr(self, masked, value)

            d = value.load()

            @d.addCallback
            def get(metadata, value=value):
                return value

            return d

    return prop


class DeferredDict(dict):
    loaded = False

    def __init__(self, client, path, defaults, loads, dumps):
        self._defaults = defaults
        self._deferreds = []
        self._client = client
        self._path = path
        self._loads = loads
        self._dumps = dumps

    def __call__(self):
        try:
            return defer.DeferredList(self._deferreds)
        finally:
            del self._deferreds[:]

    def __getitem__(self, item):
        try:
            return dict.__getitem__(self, item)
        except KeyError:
            return self._defaults[item]

    def __setitem__(self, item, value):
        dict.__setitem__(self, item, value)
        d = self.save()
        self._deferreds.append(d)

    def load(self, watch=True):
        if watch:
            d, watch = self._client.get_and_watch(self._path)
        else:
            d = self._client.get(self._path)

        @d.addBoth
        def _get(result, *args):
            if isinstance(result, Failure):
                return

            value, metadata = result
            data = self._loads(value)
            self.clear()
            self.update(data)

        if watch:
            @d.addCallback
            def _watch(result):
                return self, watch

        return d

    def save(self):
        data = self._dumps(dict(self))
        return self._client.set_or_create(self._path, data)
