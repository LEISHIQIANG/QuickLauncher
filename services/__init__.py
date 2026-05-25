"""Application service modules."""

import logging

_initialized = False


def init_services():
    global _initialized
    if _initialized:
        return
    _initialized = True
    logging.getLogger(__name__).debug("Service modules initialized")
