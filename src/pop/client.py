from txzookeeper import client
from twisted.internet.defer import inlineCallbacks, returnValue
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
