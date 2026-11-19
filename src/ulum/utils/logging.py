import logging
import os
import sys

def setup_logger(debug: bool = False) -> logging.Logger:
    level = logging.DEBUG if debug or os.environ.get("ULUM_DEBUG") == "1" else logging.INFO
    logger = logging.getLogger("ulum")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger

logger = setup_logger()
