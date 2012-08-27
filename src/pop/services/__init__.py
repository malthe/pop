import venusian


def register(factory):
    def callback(scanner, name, ob):
        registry = scanner.__dict__.setdefault('registry', {})
        registry[factory.name] = factory
    venusian.attach(factory, callback)
    return factory
