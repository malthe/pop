from txzookeeper import client
from twisted.internet.defer import inlineCallbacks, returnValue, Deferred
from zookeeper import NodeExistsException
from zookeeper import NoNodeException
from zookeeper import NotEmptyException


class ZookeeperClient(client.ZookeeperClient):
    """Adds convenience methods."""

    @inlineCallbacks
    def create_or_clear(self, path, **kwargs):
        """Create path and recursively clear contents."""

        try:
            yield self.create(path, **kwargs)
        except NodeExistsException:
            children = yield self.get_children(path)
            for name in children:
                yield self.recursive_delete(path + "/" + name)

    @inlineCallbacks
    def recursive_delete(self, path, **kwargs):
        """Recursively delete path."""

        while True:
            try:
                yield self.delete(path, **kwargs)
            except NoNodeException:
                break
            except NotEmptyException:
                children = yield self.get_children(path)
                for name in children:
                    yield self.recursive_delete(path + "/" + name)
            else:
                break

    @inlineCallbacks
    def create_multiple(self, *paths, **kwargs):
        """Create multiple paths; ignore existing."""

        for path in paths:
            try:
                yield self.create(path, **kwargs)
            except NodeExistsException:
                pass

    def set_or_create(self, path, *args, **kwargs):
        """Sets the data of a node at the given path, or creates it."""

        d = self.set(path, *args, **kwargs)

        @d.addErrback
        def _error(result):
            return self.create(path, *args, **kwargs)

        return d

    @inlineCallbacks
    def get_or_wait(self, path, name):
        """Get data of node under path, or wait for it."""

        # First, get children and watch folder.
        d, watch = self.get_children_and_watch(path)

        deferred = Deferred()
        path += "/" + name

        @watch.addCallback
        def _notify(event):
            if event.type_name == "child":
                d = self.get(path)
                d.addCallback(deferred.callback)

        # Retrieve children.
        children = yield d

        if name in children:
            watch.cancel()
            deferred = self.get(path)

        result = yield deferred
        returnValue(result)
