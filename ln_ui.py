# ln_ui.py
# UI definitions for the LN LODs addon

import bpy
import os
import logging
import importlib

from . import ln_lod_calculator

logger = logging.getLogger(__name__)

ADDON_DIR = os.path.dirname(__file__)
README_PATH = os.path.join(ADDON_DIR, "ReadMe.txt")

KNOWN_EXPORTER_MODULES = [
    "MSFS_Multi_Exporter",
    "msfs_multi_exporter",
    "io_scene_gltf2_msfs_2024",
]

def check_exporter_status(context) -> tuple:
    """
    Checks if an MSFS Asobo Exporter addon is available.

    Returns (status, module_name) where status is one of:
      - "ENABLED"        -- installed and enabled in preferences
      - "DISABLED"       -- installed (importable) but not enabled
      - "NOT_INSTALLED"  -- no known exporter module found
    """
    prefs = context.preferences.addons
    for mod in KNOWN_EXPORTER_MODULES:
        if mod in prefs:
            return ("ENABLED", mod)
    for mod in KNOWN_EXPORTER_MODULES:
        try:
            importlib.import_module(mod)
            return ("DISABLED", mod)
        except ImportError:
            continue
    return ("NOT_INSTALLED", None)


# UI Classes and Operators

class LNLODsPanel(bpy.types.Panel):
    bl_label = "LN LODs"
    bl_idname = "VIEW3D_PT_ln_lods"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LN LODs"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        status, _ = check_exporter_status(context)
        if status == "NOT_INSTALLED":
            row = layout.row()
            row.alert = True
            row.label(text="MSFS Exporter addon not found", icon='ERROR')
            row = layout.row()
            row.alert = True
            row.label(text="Install it to use Set LOD Values", icon='BLANK1')
        elif status == "DISABLED":
            row = layout.row()
            row.alert = True
            row.label(text="MSFS Exporter addon is disabled", icon='ERROR')
            row = layout.row()
            row.alert = True
            row.label(text="Enable it in Edit > Preferences > Add-ons", icon='BLANK1')

        layout.operator("object.calculate_lod_screen_sizes", text="Calculate LOD Sizes")

        layout.label(text="LOD Results:")
        for result in scene.lod_results:
            row = layout.row()
            if result.vertex_count == 0:
                row.alert = True
                row.label(text=f"{result.name}: Empty (0 vertices)", icon='INFO')
            elif result.screen_size < 0:
                row.alert = True
                row.label(text=f"{result.name}: Vertex Count out of range ({result.vertex_count} vertices)")
            else:
                row.label(text=f"{result.name}: {result.vertex_count} vertices, {result.screen_size:.2f}%")

        layout.separator()
        layout.operator("object.clear_lod_data", text="Clear Data")
        layout.prop(scene, "hide_hidden_collections", text="Hide Hidden Collections")
        layout.prop(scene, "screen_space_margin", text="Screen Space Margin (%)")
        layout.operator("object.set_lod_values", text="Set LOD Values in Asobo Exporter")
        layout.operator("object.open_readme", text="Open README")


class OpenReadmeOperator(bpy.types.Operator):
    """Opens the README file for the addon."""
    bl_idname = "object.open_readme"
    bl_label = "Open README"

    def execute(self, context):
        if os.path.exists(README_PATH):
            bpy.ops.wm.path_open(filepath=README_PATH)
            logger.debug("Opened README file.")
        else:
            self.report({'ERROR'}, "README file not found.")
            logger.error("README file not found.")
        return {'FINISHED'}


class CalculateLODScreenSizesOperator(bpy.types.Operator):
    """Calculate and display LOD screen space sizes for each LOD collection."""
    bl_idname = "object.calculate_lod_screen_sizes"
    bl_label = "Calculate LOD Screen Sizes"

    def execute(self, context):
        scene = context.scene
        scene.lod_results.clear()
        lod_data = ln_lod_calculator.count_vertices_in_lod_collections(context)
        logger.debug(f"LOD Data: {lod_data}")

        if lod_data:
            for name, vertex_count, screen_size in lod_data:
                entry = scene.lod_results.add()
                entry.name = name
                entry.vertex_count = vertex_count
                entry.screen_size = screen_size

            self.report({'INFO'}, "LOD screen sizes calculated.")
            logger.info("LOD screen sizes calculated successfully.")
        else:
            self.report({'ERROR'}, "No Valid LOD Collections Found.")
            logger.error("No Valid LOD Collections Found.")

        return {'FINISHED'}


class ClearLODDataOperator(bpy.types.Operator):
    """Purges calculated data from the scene"""
    bl_idname = "object.clear_lod_data"
    bl_label = "Clear LOD Data"

    def execute(self, context):
        ln_lod_calculator.clear_lod_results()
        try:
            context.scene.lod_viewer_groups.clear()
        except Exception:
            pass
        self.report({'INFO'}, "LOD data cleared.")
        logger.info("LOD data cleared.")
        return {'FINISHED'}


class SetLODValuesOperator(bpy.types.Operator):
    """Sends the calculated data (+% Margin) to MSFS2020/2024 Exporter"""
    bl_idname = "object.set_lod_values"
    bl_label = "Set LOD Values in Asobo Exporter"

    def execute(self, context):
        status, _ = check_exporter_status(context)
        if status != "ENABLED":
            self.report({'ERROR'}, "Cannot set LOD values: MSFS Exporter addon not found or disabled.")
            return {'CANCELLED'}
        ln_lod_calculator.set_lod_values()
        self.report({'INFO'}, "LOD values set in Asobo Exporter.")
        logger.info("LOD values set in Asobo Exporter.")
        return {'FINISHED'}


class LODResultProperty(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    vertex_count: bpy.props.IntProperty(name="Vertex Count")
    screen_size: bpy.props.FloatProperty(name="Screen Size (%)")


class OpenReadmePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        layout = self.layout
        layout.operator("object.open_readme", text="Open README")


classes = (
    LNLODsPanel,
    OpenReadmeOperator,
    CalculateLODScreenSizesOperator,
    ClearLODDataOperator,
    SetLODValuesOperator,
    LODResultProperty,
    OpenReadmePreferences,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lod_results = bpy.props.CollectionProperty(type=LODResultProperty)
    bpy.types.Scene.screen_space_margin = bpy.props.FloatProperty(
        name="Screen Space Margin",
        description="Percentage margin to adjust screen space size (0-100%)",
        default=2.0,
        min=0.0,
        max=100.0
    )
    bpy.types.Scene.hide_hidden_collections = bpy.props.BoolProperty(
        name="Hide Hidden Collections",
        description="If enabled, collections hidden in the viewport are excluded from LOD calculations",
        default=False
    )
    logger.debug("ln_ui registered.")

def unregister():
    del bpy.types.Scene.lod_results
    del bpy.types.Scene.screen_space_margin
    del bpy.types.Scene.hide_hidden_collections
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    logger.debug("ln_ui unregistered.")
