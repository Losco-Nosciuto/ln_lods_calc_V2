# ln_ui.py
# UI definitions for the LN LODs addon

import bpy
import os
import logging
import importlib

from . import ln_lod_calculator
from . import ln_lod_screen

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


# Render preset / LOD Factor (shared by both editions: the preset changes the
# vertex-budget curves the calculator writes, so it belongs with the calculator).
#
# Official parity (lod_tools_msfs_2024/prefs.py): picking a preset STAMPS the
# single LOD Factor with the preset's value — they never stack, the factor is
# the one knob. The enum and the factor are kept in sync in both directions so
# they can never disagree: editing the factor to an exact anchor value
# (0.25 / 0.5 / 1 / 2) re-selects that preset; anything else is the Custom
# state (shown as a "Custom" button, never as a dropdown entry).

_syncing_factor = False


def _update_render_preset(self, context):
    """Stamp the LOD Factor from the picked preset and re-derive results."""
    global _syncing_factor
    if _syncing_factor:
        return
    preset = getattr(self, "lod_render_preset", ln_lod_screen.DEFAULT_RENDER_PRESET)
    self.lod_lod_factor = ln_lod_screen.RENDER_PRESETS.get(preset, 1.0)
    _recalculate_lod_results_if_present(context)


def _update_lod_factor(self, context):
    """Flip the preset when the factor lands exactly on an anchor value.

    No recalculation here: factor edits are continuous (slider), and a full
    vertex-count scan per event would freeze the UI. Results refresh at the
    next Calculate / Refresh LOD Viewer List, like the Screen Space Margin.
    """
    global _syncing_factor
    preset = ln_lod_screen.preset_for_factor(self.lod_lod_factor)
    if preset is None or self.lod_render_preset == preset:
        return
    _syncing_factor = True
    try:
        self.lod_render_preset = preset
    finally:
        _syncing_factor = False


def _recalculate_lod_results_if_present(context):
    """Re-runs the calculation when results already exist.

    Picking a preset changes the per-preset vertex-budget curves, so existing
    `lod_results` (and therefore the viewer thresholds + the exporter writes)
    would otherwise go stale. Only direct data writes here — no bpy.ops
    (safe inside a property update callback).
    """
    scene = getattr(context, "scene", None)
    if scene is None or not getattr(scene, "lod_results", None):
        return
    try:
        lod_data = ln_lod_calculator.count_vertices_in_lod_collections(context)
        scene.lod_results.clear()
        if lod_data:
            for name, vertex_count, screen_size in lod_data:
                entry = scene.lod_results.add()
                entry.name = name
                entry.vertex_count = vertex_count
                entry.screen_size = screen_size
    except Exception as exc:
        logger.warning(f"Render preset changed but LOD results re-calculation failed: {exc}")


def draw_render_preset_row(layout, scene):
    """Shared Render Preset row (calculator + viewer panels).

    - Anchor LOD Factor (0.25/0.5/1/2): the 4-item preset dropdown plus a gear
      button that opens the LOD Factor popup (the factor is an advanced
      override, hidden behind the gear — official prefs.py/panels.py layout).
    - Non-anchor factor (Custom): the dropdown is REPLACED by a "Custom" button
      that opens the same popup; a Custom entry never appears in the dropdown.

    Fails safe to nothing when the props are absent (should not happen — they
    are registered with this module — but keeps the panel drawable).
    """
    if not hasattr(scene, "lod_render_preset"):
        return
    row = layout.row(align=True)
    row.label(text="Render Preset")
    if ln_lod_screen.preset_for_factor(scene.lod_lod_factor) is not None:
        row.prop(scene, "lod_render_preset", text="")
        if hasattr(bpy.types, "LN_OT_RenderSettings"):
            row.operator(
                "ln_lods.render_settings", icon="PREFERENCES", text="", emboss=False
            )
    else:
        factor = scene.lod_lod_factor
        if hasattr(bpy.types, "LN_OT_RenderSettings"):
            row.operator(
                "ln_lods.render_settings",
                text=f"Custom (x{factor:.3g})",
                icon="TRIA_DOWN",
            )
        else:
            row.label(text=f"Custom (x{factor:.3g})")


class LN_OT_RenderSettings(bpy.types.Operator):
    """LOD Factor settings popup (advanced — normally set by the Render Preset)"""
    bl_idname = "ln_lods.render_settings"
    bl_label = "LOD Render Settings"
    bl_description = "LOD Factor (advanced — normally set by the Render Preset)"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self)

    def draw(self, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        row = layout.row()
        row.alignment = "RIGHT"
        row.operator("ln_lods.render_settings_reset", text="Reset", icon="RECOVER_LAST")
        layout.prop(scene, "lod_render_preset", text="Render Preset")
        layout.prop(scene, "lod_lod_factor")


class LN_OT_RenderSettingsReset(bpy.types.Operator):
    """Reset render settings to defaults (High preset, LOD Factor 1.0)"""
    bl_idname = "ln_lods.render_settings_reset"
    bl_label = "Reset Render Settings"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return {"CANCELLED"}
        # default HIGH -> update handler stamps factor 1.0 + recalcs results
        scene.lod_render_preset = ln_lod_screen.DEFAULT_RENDER_PRESET
        return {"FINISHED"}


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

        draw_render_preset_row(layout, scene)
        layout.label(text="Min sizes follow the sim's per-preset curves", icon='INFO')

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
                row.label(text=f"{result.name}: {result.vertex_count} vertices, {result.screen_size:.4g}%")

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
    LN_OT_RenderSettings,
    LN_OT_RenderSettingsReset,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.lod_results = bpy.props.CollectionProperty(type=LODResultProperty)
    bpy.types.Scene.lod_render_preset = bpy.props.EnumProperty(
        name="Render Preset",
        description="The sim scales LOD min sizes per graphics preset "
                    "(stamps the LOD Factor below)",
        default=ln_lod_screen.DEFAULT_RENDER_PRESET,
        items=[
            ("LOW", "Low", "Vertex budgets x 0.25 (1/sqrt factor = 2) — lower-detail LODs appear much sooner."),
            ("MEDIUM", "Medium", "Vertex budgets x 0.5 (1/sqrt factor = 1.414) — lower-detail LODs appear sooner."),
            ("HIGH", "High", "Vertex budgets x 1.0 — default in-sim curves; recommended when authoring."),
            ("ULTRA", "Ultra", "Vertex budgets x 2.0 (1/sqrt factor = 0.707) — high-detail LODs stay far longer."),
        ],
        update=_update_render_preset,
    )
    bpy.types.Scene.lod_lod_factor = bpy.props.FloatProperty(
        name="LOD Factor",
        description="LOD Factor, affected by render presets "
                    "(Low 0.25, Medium 0.5, High 1, Ultra 2). Picking a preset "
                    "stamps this value; editing it to an anchor value re-selects "
                    "that preset, anything else is Custom (applied at the next "
                    "Calculate)",
        min=ln_lod_screen.LOD_FACTOR_MIN,
        max=ln_lod_screen.LOD_FACTOR_MAX,
        default=1.0,
        update=_update_lod_factor,
    )
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
    del bpy.types.Scene.lod_render_preset
    del bpy.types.Scene.lod_lod_factor
    del bpy.types.Scene.screen_space_margin
    del bpy.types.Scene.hide_hidden_collections
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    logger.debug("ln_ui unregistered.")
