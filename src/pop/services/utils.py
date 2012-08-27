from twisted.internet.defer import returnValue
from twisted.internet.defer import inlineCallbacks


from zookeeper import NoNodeException


def nodeproperty(path, default, typecast=str):
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
