"""Set up and instantiate the logger."""

import logging

logger = logging.getLogger("dm20-protocol")
logging.basicConfig(
    level=logging.DEBUG,
)