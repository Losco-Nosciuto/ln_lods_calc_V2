# ln_debug.py
# Optional debug module (safe to exclude from __init__.py)
# -----------------------------------------------------------

import logging

logger = logging.getLogger(__name__)

def some_debug_function():
    """
    Example debug function.
    Does not affect the main functionality of the add-on.
    """
    logger.debug("Debug function was called - just an example.")

def register():
    """
    Register debug operators or properties here, if any.
    """
    pass

def unregister():
    """
    Unregister debug operators or properties here, if any.
    """
    pass
