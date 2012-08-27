from twisted.internet.defer import returnValue
from twisted.internet.defer import inlineCallbacks


from zookeeper import NoNodeException


def nodeproperty(path, default):
    @property
    @inlineCallbacks
    def prop(self):
        try:
            value, metadata = yield self.client.get(self.path + path)
        except NoNodeException:
            value = default

        returnValue(value)

    return prop
