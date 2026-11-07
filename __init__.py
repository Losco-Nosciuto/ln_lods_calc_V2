# __init__.py
# LN LODs — Free Edition
# Full LOD calculation engine + Asobo Exporter integration.
# The Pro edition adds the real-time LOD Viewer / Testing Mode.

bl_info = {
    "name": "LN LODs",
    "description": ("LN LODs is a Blender addon designed to calculate interpolated "
                    "screen sizes for collections with LOD naming conventions and "
                    "automatically set LOD values for the MSFS Asobo Exporter "
                    "(Microsoft Flight Simulator 2020 and 2024). Free edition: full "
                    "calculation engine and exporter integration. The Pro edition "
                    "adds the real-time LOD Viewer."),
    "author": "Chris 'Losco Nosciuto' Da Ros",
    "version": (2, 9, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > LN LODs",
    "category": "Object"
}

import logging

from . import ln_lod_calculator
from . import ln_ui

logger = logging.getLogger(__name__)


def register():
    ln_lod_calculator.register()
    ln_ui.register()
    logger.debug("LN LODs addon registered.")


def unregister():
    ln_ui.unregister()
    ln_lod_calculator.unregister()
    logger.debug("LN LODs addon unregistered.")


if __name__ == "__main__":
    register()
