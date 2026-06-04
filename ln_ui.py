# ln_ui.py
# Contiene i pannelli, gli operatori, le property e l'interfaccia LN LODs
# -----------------------------------------------------------

import bpy
import os
import webbrowser
import logging

from . import ln_lod_calculator  # Importiamo funzioni dal modulo di calcolo

logger = logging.getLogger(__name__)

ADDON_DIR = os.path.dirname(__file__)
README_PATH = os.path.join(ADDON_DIR, "readme.txt")


# Classi di UI e Operator

class LNLODsPanel(bpy.types.Panel):
    bl_label = "LN LODs"
    bl_idname = "VIEW3D_PT_ln_lods"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "LN LODs"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # Button to calculate
        layout.operator("object.calculate_lod_screen_sizes", text="Calculate LOD Sizes")

        # Display the results
        layout.label(text="LOD Results:")
        for result in scene.lod_results:
            row = layout.row()
            if result.vertex_count == 0:
                row.alert = True
                row.label(text=f"{result.name}: Empty (0 vertices)", icon='INFO')
                
            elif result.screen_size < 0:
                row.alert = True
                row.label(
                    text=f"{result.name}: Vertex Count out of range ({result.vertex_count} vertices)"
                )
            else:
                row.label(
                    text=f"{result.name}: {result.vertex_count} vertices, {result.screen_size:.2f}%"
                )

        layout.separator()

        # Button to clear LOD data
        layout.operator("object.clear_lod_data", text="Clear Data")
        
        # Hidden Collections Checkbox
        layout.prop(scene, "hide_hidden_collections", text="Hide Hidden Collections")

        # Text box for screen space margin
        layout.prop(scene, "screen_space_margin", text="Screen Space Margin (%)")
        

        # Button to set LOD values in the Asobo Exporter
        layout.operator("object.set_lod_values", text="Set LOD Values in Asobo Exporter")

        # Button to open README
        layout.operator("object.open_readme", text="Open README")


class OpenReadmeOperator(bpy.types.Operator):
    """Open the README file externally."""
    bl_idname = "object.open_readme"
    bl_label = "Open README"

    def execute(self, context):
        if os.path.exists(README_PATH):
            webbrowser.open(README_PATH)
            logger.debug("Opened README file.")
        else:
            self.report({'ERROR'}, "README file not found.")
            logger.error("README file not found.")
        return {'FINISHED'}


class CalculateLODScreenSizesOperator(bpy.types.Operator):
    """Calculate interpolated screen sizes for LOD collections."""
    bl_idname = "object.calculate_lod_screen_sizes"
    bl_label = "Calculate LOD Screen Sizes"

    def execute(self, context):
        logger.debug("Execute function for CalculateLODScreenSizesOperator called.")
        scene = context.scene

        # Clear existing results
        logger.debug("Clearing existing LOD results.")
        scene.lod_results.clear()

        # Call the vertex counting function
        logger.debug("Calling ln_lod_calculator.count_vertices_in_lod_collections().")
        lod_data = ln_lod_calculator.count_vertices_in_lod_collections()

        # Debug output for lod_data
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
    """Clear all calculated LOD data."""
    bl_idname = "object.clear_lod_data"
    bl_label = "Clear LOD Data"

    def execute(self, context):
        ln_lod_calculator.clear_lod_results()
        self.report({'INFO'}, "LOD data cleared.")
        logger.info("LOD data cleared.")
        return {'FINISHED'}


class SetLODValuesOperator(bpy.types.Operator):
    """Set the calculated LOD values in the MSFS Asobo Exporter."""
    bl_idname = "object.set_lod_values"
    bl_label = "Set LOD Values in Asobo Exporter"

    def execute(self, context):
        ln_lod_calculator.set_lod_values()
        self.report({'INFO'}, "LOD values set in Asobo Exporter.")
        logger.info("LOD values set in Asobo Exporter.")
        return {'FINISHED'}


class LODResultProperty(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(name="Name")
    vertex_count: bpy.props.IntProperty(name="Vertex Count")
    screen_size: bpy.props.FloatProperty(name="Screen Size (%)")


class OpenReadmePreferences(bpy.types.AddonPreferences):
    """Addon preferences for LN LODs."""
    bl_idname = __package__  # Automatically use the addon name

    def draw(self, context):
        layout = self.layout
        layout.operator("object.open_readme", text="Open README")


def register():
    """
    Registra tutte le classi di UI e operator (compresa la property).
    Crea anche la CollectionProperty e la FloatProperty su Scene.
    """
    bpy.utils.register_class(LNLODsPanel)
    bpy.utils.register_class(OpenReadmeOperator)
    bpy.utils.register_class(CalculateLODScreenSizesOperator)
    bpy.utils.register_class(ClearLODDataOperator)
    bpy.utils.register_class(SetLODValuesOperator)
    bpy.utils.register_class(LODResultProperty)
    bpy.utils.register_class(OpenReadmePreferences)

    # Scene properties
    bpy.types.Scene.lod_results = bpy.props.CollectionProperty(type=LODResultProperty)
    bpy.types.Scene.screen_space_margin = bpy.props.FloatProperty(
        name="Screen Space Margin",
        description="Percentage margin to adjust screen space size (0-100%)",
        default=2.0,
        min=0.0,
        max=100.0
    )
    
     # Nuova property per escludere collezioni nascoste
    bpy.types.Scene.hide_hidden_collections = bpy.props.BoolProperty(
        name="Hide Hidden Collections",
        description="If enabled, any collection hidden in the viewport is excluded from LOD calculations",
        default=False
    )

    logger.debug("ln_ui registered.")


def unregister():
    """
    Elimina le classi registrate e pulisce le property su Scene.
    """
    del bpy.types.Scene.lod_results
    del bpy.types.Scene.screen_space_margin
    del bpy.types.Scene.hide_hidden_collections

    bpy.utils.unregister_class(OpenReadmePreferences)
    bpy.utils.unregister_class(LODResultProperty)
    bpy.utils.unregister_class(SetLODValuesOperator)
    bpy.utils.unregister_class(ClearLODDataOperator)
    bpy.utils.unregister_class(CalculateLODScreenSizesOperator)
    bpy.utils.unregister_class(OpenReadmeOperator)
    bpy.utils.unregister_class(LNLODsPanel)

    logger.debug("ln_ui unregistered.")
