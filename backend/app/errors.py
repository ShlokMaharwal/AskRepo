class IndexConfigurationError(ValueError):
    """The persisted index and requested runtime use incompatible embedding settings."""


class WorkCancelled(Exception):
    """A disconnected client cancelled subsequent retrieval/generation stages."""


class DemoLimitError(Exception):
    def __init__(self):
        super().__init__("Demo limit reached, try again in a minute")
