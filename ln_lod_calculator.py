# ln_lod_calculator.py
# Contains LOD calculation and logic functions
# -----------------------------------------------------------
# Screen sizes are produced by the official MSFS 2024 reference model:
#
#   vertex count  ->  closed-form min-size curve   (ln_lod_screen)
#                 ->  per-render-preset curve scale (M = 1/sqrt(factor))
#                 ->  official floors + reverse monotonic cascade
#   => one minSize percentage per LOD collection (exact float, no rounding)
#
# Vertex counts come from `ln_vertex_count`, the official glTF counting port
# (per-material primitives, instancing included, tangents off) — the number the
# exporter actually writes, not Blender's raw vertex count.

import bpy
import re
import logging

from . import ln_lod_screen
from . import ln_vertex_count

logger = logging.getLogger(__name__)

# Highest vertex count that still maps inside the official curve (the 1000 %
# point of the SDK reference table). Above this the addon reports the LOD as
# "out of range" instead of writing a meaningless minSize.
MAX_VERTEX_COUNT = 25204540

LOD_COLLECTION_PATTERN = re.compile(r"_LOD\d+$", re.IGNORECASE)
LOD_GROUP_PATTERN = re.compile(r"^(.*)_LOD(\d+)$", re.IGNORECASE)


def find_layer_collection(layer_coll: bpy.types.LayerCollection, coll: bpy.types.Collection):
    """
    Recursively searches for the LayerCollection that references 'coll'.
    Returns the LayerCollection if found; otherwise, None.
    """
    if layer_coll.collection == coll:
        return layer_coll
    for child in layer_coll.children:
        found = find_layer_collection(child, coll)
        if found:
            return found
    return None


def count_vertices_in_lod_collections(context=None):
    """Scan every `_LOD<n>` collection and compute its minSize percentage.

    Returns a list of `(collection_name, vertex_count, screen_size_pct)` where
    `screen_size_pct` is -1.0 for collections above `MAX_VERTEX_COUNT`.

    Two passes, because the official floors and the monotonic cascade are
    per-group properties (a LOD's floor depends on whether it is the last or
    second-to-last member of ITS group):
      1. vertex count + raw curve size for every collection;
      2. group by name prefix, scale by the render preset, apply the official
         floors and the reverse cascade.
    """
    logger.debug("=== Checking collections for valid LODs ===")
    results = []
    valid_collections_found = False
    scene = bpy.context.scene
    hide_hidden = getattr(scene, "hide_hidden_collections", False)
    preset_factor = getattr(scene, "lod_lod_factor", 1.0)
    if not preset_factor:
        preset_factor = 1.0
    root_layer_collection = bpy.context.view_layer.layer_collection

    lod_collections = [c for c in bpy.data.collections if LOD_COLLECTION_PATTERN.search(c.name.strip())]
    total = len(lod_collections)
    wm = context.window_manager if context else None
    if wm:
        wm.progress_begin(0, total)

    depsgraph = bpy.context.evaluated_depsgraph_get()

    # Pass 1 — official vertex count + raw curve size.
    raw_entries = []  # (collection_name, vertex_count, size_pct)
    for idx, collection in enumerate(lod_collections):
        collection_name = collection.name.strip()
        if hide_hidden:
            layer_coll = find_layer_collection(root_layer_collection, collection)
            if layer_coll and not layer_coll.visible_get():
                logger.debug(f"Skipping hidden collection: {collection_name}")
                if wm:
                    wm.progress_update(idx)
                continue

        valid_collections_found = True
        total_vertices = ln_vertex_count.get_gltf_objects_vertex_count(
            list(collection.objects), depsgraph
        )
        interpolated_size = ln_lod_screen.lowest_screen_size_from_vcount(
            total_vertices
        ) * 100.0
        raw_entries.append((collection.name, total_vertices, interpolated_size))

        if wm:
            wm.progress_update(idx)

    # Pass 2 — per-group preset scaling, official floors and monotonic cascade.
    grouped = {}
    for name, vertex_count, size_pct in raw_entries:
        match = LOD_GROUP_PATTERN.match(name.strip())
        if match:
            grouped.setdefault(match.group(1), []).append(
                (int(match.group(2)), name, vertex_count, size_pct)
            )

    for members in grouped.values():
        members.sort(key=lambda item: item[0])  # ascending LOD number
        sizes = [m[3] for m in members]
        vertex_counts = [m[2] for m in members]
        sizes = ln_lod_screen.scale_screen_sizes_for_preset(sizes, preset_factor)
        floored = ln_lod_screen.apply_lod_size_floors_and_cascade(
            sizes, vertex_counts
        )
        for (_, name, vertex_count, _), new_size in zip(members, floored):
            if vertex_count > MAX_VERTEX_COUNT:
                results.append((name, vertex_count, -1.0))
                logger.error(f"Vertex Count out of range for collection: {name}")
            else:
                results.append((name, vertex_count, new_size))
                logger.debug(f"Screen Size for {name}: {new_size:.4g}%")

    if wm:
        wm.progress_end()

    if not valid_collections_found:
        logger.error("No Valid LOD Collections Found")
        return None

    logger.debug("=== Completed collection checking ===")
    return results


def clear_lod_results():
    bpy.context.scene.lod_results.clear()
    logger.debug("LOD Results cleared.")


def set_lod_values():
    """Write the calculated sizes (+Screen Space Margin) to the Asobo Exporter."""
    scene = bpy.context.scene
    lod_groups = getattr(scene, "msfs_multi_exporter_lod_groups", None)
    if not lod_groups:
        logger.error("No MSFS LOD groups found. Is the MSFS Exporter addon enabled?")
        return

    lod_data = count_vertices_in_lod_collections()
    logger.debug(f"LOD Data: {lod_data}")

    if not lod_data:
        return

    margin = scene.screen_space_margin / 100.0
    for lod_group in lod_groups:
        logger.debug(f"Processing LOD Group: {lod_group.group_name}")
        for lod in lod_group.lods:
            if lod.collection:
                collection_name = lod.collection.name
                logger.debug(f"  Matching collection: {collection_name}")
                for name, _, screen_size in lod_data:
                    if name == collection_name:
                        if screen_size >= 0:
                            # Exact float percent (official parity): no ceiling,
                            # so the sub-1% official floors (0.1% last LOD,
                            # 0.001% for an empty last LOD) survive into the
                            # exporter's lod_value.
                            lod.lod_value = screen_size * (1.0 + margin)
                            logger.debug(f"    Updated LOD Value: {lod.lod_value} for {collection_name}")
                        else:
                            logger.debug(f"    Vertex Count out of range for {collection_name}, skipping LOD update.")
                        break


def register():
    pass


def unregister():
    pass
