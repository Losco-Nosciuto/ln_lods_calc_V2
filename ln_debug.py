# ln_debug.py
# Modulo di debug opzionale (puoi escluderlo dal __init__.py)
# -----------------------------------------------------------

import logging

logger = logging.getLogger(__name__)

def some_debug_function():
    """
    Esempio di funzione di debug.
    Non intacca le funzionalità principali del plugin.
    """
    logger.debug("Debug function was called - just an example.")

def register():
    """
    Se avessi operator di debug o property da registrare, lo faresti qui.
    """
    pass

def unregister():
    """
    Se avessi operator di debug o property da unregisterare, lo faresti qui.
    """
    pass
