# __init__.py

bl_info = {
    "name": "LN LODs",
    "description": "LN LODs is a Blender addon designed to calculate interpolated screen sizes for collections with LOD naming conventions and automatically set LOD values for the MSFS Asobo Exporter.",
    "author": "Chris 'Losco Nosciuto' Da Ros",
    "version": (2, 8, 0),
    "blender": (4, 2, 2),
    "location": "View3D > Sidebar > LN LODs",
    "category": "Object"
}

import logging
import importlib

from . import ln_lod_calculator
from . import ln_ui
from . import ln_debug

importlib.reload(ln_lod_calculator)
importlib.reload(ln_ui)
importlib.reload(ln_debug)

logger = logging.getLogger(__name__)


def register():
    ln_lod_calculator.register()
    ln_ui.register()
    ln_debug.register() 
    logger.debug("LN LODs addon registered (modular version).")


def unregister():
    ln_debug.unregister()
    ln_ui.unregister()
    ln_lod_calculator.unregister()
    logger.debug("LN LODs addon unregistered (modular version).")


if __name__ == "__main__":
    register()