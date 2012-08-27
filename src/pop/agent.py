class Agent(object):
    """An agent connects to the tree at some path."""

    def __init__(self, client, path):
        assert not path.endswith("/")

        self.client = client
        self.path = path

    def connect(self):
        return self.client.connect()

    def close(self):
        return self.client.close()
