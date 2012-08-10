import yaml

from collections import namedtuple
from UserDict import DictMixin
from cStringIO import StringIO

from twisted.internet.defer import inlineCallbacks, returnValue
from txzookeeper.utils import retry_change
from zookeeper import NoNodeException

from .exceptions import StateNotFound


class DeletedItem(namedtuple("DeletedItem", "key old")):
    """Represents deleted items when :class:`YAMLState` writes."""
    def __str__(self):
        return "Setting deleted: %r (was %.100r)" % (self.key, self.old)


class ModifiedItem(namedtuple("ModifiedItem", "key old new")):
    """Represents modified items when :class:`YAMLState` writes."""
    def __str__(self):
        return "Setting changed: %r=%.100r (was %.100r)" % \
            (self.key, self.new, self.old)


class AddedItem(namedtuple("AddedItem", "key new")):
    """Represents added items when :class:`YAMLState` writes."""
    def __str__(self):
        return "Setting changed: %r=%.100r (was unset)" % \
            (self.key, self.new)


class YAMLState(DictMixin, object):
    """Provides a dict like interface around a Zookeeper node
    containing serialised YAML data. The dict provided represents the
    local view of all node data.

    `write` writes this information into the Zookeeper node, using a
    retry until success and merges against any existing keys in ZK.

    YAMLState(client, path)

    `client`: a Zookeeper client
    `path`: the path of the Zookeeper node to manage

    The state of this object always represents the product of the
    pristine settings (from Zookeeper) and the pending writes.

    All mutation to the dict expects the use of inlineCallbacks and a
    yield. This includes set and update.
    """
    # By always updating 'self' on mutation we don't need to do any
    # special handling on data access (gets).

    def __init__(self, client, path):
        self._client = client
        self._path = path
        self._pristine_cache = None
        self._cache = {}

    def dump(self):
        stream = StringIO()
        yaml.safe_dump(self._cache, stream, default_flow_style=False)
        return stream

    @inlineCallbacks
    def read(self, required=False):
        """Read Zookeeper state.

        Read in the current Zookeeper state for this node. This
        operation should be called prior to other interactions with
        this object.

        `required`: boolean indicating if the node existence should be
        required at read time. Normally write will create the node if
        the path is possible. This allows for simplified catching of
        errors.

        """
        self._pristine_cache = {}
        self._cache = {}
        try:
            data, stat = yield self._client.get(self._path)
            data = yaml.load(data)
            if data:
                self._pristine_cache = data
                self._cache = data.copy()
        except NoNodeException:
            if required:
                raise StateNotFound(self._path)

    def _check(self):
        """Verify that sync was called for operations which expect it."""
        if self._pristine_cache is None:
            raise ValueError(
                "You must call .read() on %s instance before use." % (
                    self.__class__.__name__,))

    ## DictMixin Interface
    def keys(self):
        return self._cache.keys()

    def __getitem__(self, key):
        self._check()
        return self._cache[key]

    def __setitem__(self, key, value):
        self._check()
        self._cache[key] = value

    def __delitem__(self, key):
        self._check()
        del self._cache[key]

    @inlineCallbacks
    def write(self):
        """Write object state to Zookeeper.

        This will write the current state of the object to Zookeeper,
        taking the final merged state as the new one, and resetting
        any write buffers.
        """
        self._check()
        cache = self._cache
        pristine_cache = self._pristine_cache
        self._pristine_cache = cache.copy()

        # Used by `apply_changes` function to return the changes to
        # this scope.
        changes = []

        def apply_changes(content, stat):
            """Apply the local state to the Zookeeper node state."""
            del changes[:]
            current = yaml.load(content) if content else {}
            missing = object()
            for key in set(pristine_cache).union(cache):
                old_value = pristine_cache.get(key, missing)
                new_value = cache.get(key, missing)
                if old_value != new_value:
                    if new_value != missing:
                        current[key] = new_value
                        if old_value != missing:
                            changes.append(
                                ModifiedItem(key, old_value, new_value))
                        else:
                            changes.append(AddedItem(key, new_value))
                    elif key in current:
                        del current[key]
                        changes.append(DeletedItem(key, old_value))
            return yaml.safe_dump(current)

        # Apply the change till it takes.
        yield retry_change(self._client, self._path, apply_changes)
        returnValue(changes)


class YAMLStateNodeMixin(object):
    """Enables simpler setters/getters.

    Mixee requires ._zk_path and ._client attributes, and a ._node_missing
    method.
    """

    @inlineCallbacks
    def _get_node_value(self, key, default=None):
        node_data = YAMLState(self._client, self._zk_path)
        try:
            yield node_data.read(required=True)
        except StateNotFound:
            self._node_missing()
        returnValue(node_data.get(key, default))

    @inlineCallbacks
    def _set_node_value(self, key, value):
        node_data = YAMLState(self._client, self._zk_path)
        try:
            yield node_data.read(required=True)
        except StateNotFound:
            self._node_missing()
        node_data[key] = value
        yield node_data.write()
