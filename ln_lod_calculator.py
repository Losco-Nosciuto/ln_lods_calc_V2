# ln_lod_calculator.py
# Contains LOD calculation and logic functions
# -----------------------------------------------------------

import bpy
import math
import re
import logging
from bisect import bisect_left
from typing import List

logger = logging.getLogger(__name__)

# Predefined data mapping vertex counts to screen-size values (Asobo SDK spec, July 2025)
# Linear part 0-100%, parabolic (power=0.5) above 100%.
DATA = {
    150: 0,
    250000: 100,
    302524: 110,
    390763: 125,
    497474: 141,
    563110: 150,
    767080: 175,
    1002498: 200,
    1269600: 225,
    1568200: 250,
    2000000: 282.25,
    2260000: 300,
    2413600: 310,
    2653000: 325,
    3000000: 345.53,
    3078300: 350,
    3534700: 375,
    4000000: 398.87,
    4022700: 400,
    4542400: 425,
    5093500: 450,
    5676100: 475,
    6000000: 488.35,
    6290400: 500,
    6995737: 525,
    7000000: 527.5,
    7613700: 550,
    8000000: 563.80,
    8322700: 575,
    9000000: 597.95,
    9063000: 600,
    9835000: 625,
    10000000: 630.25,
    10638900: 650,
    11473000: 675,
    12341000: 700,
    13239000: 725,
    14169000: 750,
    15130000: 775,
    16123000: 800,
    17148000: 825,
    18204000: 850,
    19292000: 875,
    20411000: 900,
    21561000: 925,
    22745000: 950,
    23955000: 975,
    25204540: 1000
}

# Ensure sorted order for interpolation
VERTEX_COUNTS = sorted(DATA.keys())
HIGH_VALUES   = [DATA[k] for k in VERTEX_COUNTS]

def interpolate_screen_size(vertex_count: int) -> float:
    """
    Returns the interpolated screen size percentage following the Asobo LOD curve:
    linear for 0-100%, parabolic (power=0.5) for values above 100%.
    Clamped to MSFS engine limits: 0% minimum, 1000% maximum.
    """
    if vertex_count <= VERTEX_COUNTS[0]:
        return HIGH_VALUES[0]
    if vertex_count >= VERTEX_COUNTS[-1]:
        return HIGH_VALUES[-1]

    idx = bisect_left(VERTEX_COUNTS, vertex_count)
    x0, x1 = VERTEX_COUNTS[idx - 1], VERTEX_COUNTS[idx]
    y0, y1 = HIGH_VALUES[idx - 1], HIGH_VALUES[idx]
    t = (vertex_count - x0) / (x1 - x0)

    if y0 <= 100:
        return y0 + t * (y1 - y0)

    y_sq = y0 * y0 + t * (y1 * y1 - y0 * y0)
    return math.sqrt(y_sq)

def _count_unique_corners(mesh, use_tangents: bool) -> int:
    """Count unique corner attribute combinations on a triangulated mesh.

    Fast numpy path (foreach_get + np.unique) with a pure-Python fallback.
    """
    n_loops = len(mesh.loops)
    if n_loops == 0:
        return 0

    # ---- Fast numpy path ----
    try:
        import numpy as np

        # Positions - extract vertex coords, then reindex per loop via vertex_index
        vert_indices = np.empty(n_loops, dtype=np.uint32)
        mesh.loops.foreach_get('vertex_index', vert_indices)
        vert_co = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
        mesh.vertices.foreach_get('co', vert_co)
        positions = np.round(vert_co.reshape(-1, 3)[vert_indices], 5)

        # Normals
        norm_arr = np.empty(n_loops * 3, dtype=np.float64)
        mesh.loops.foreach_get('normal', norm_arr)
        normals = np.round(norm_arr.reshape(-1, 3), 5)

        # UV layers
        uv_cols = []
        for uv_layer in mesh.uv_layers:
            uv_arr = np.empty(n_loops * 2, dtype=np.float64)
            uv_layer.data.foreach_get('uv', uv_arr)
            uv_cols.append(np.round(uv_arr.reshape(-1, 2), 5))

        # Tangents and bitangent sign
        if use_tangents:
            tang_arr = np.empty(n_loops * 3, dtype=np.float64)
            mesh.loops.foreach_get('tangent', tang_arr)
            tangents = np.round(tang_arr.reshape(-1, 3), 5)
            bs_arr = np.empty(n_loops, dtype=np.float64)
            mesh.loops.foreach_get('bitangent_sign', bs_arr)
            bs = np.round(bs_arr, 5).reshape(-1, 1)
        else:
            tangents = np.zeros((n_loops, 3), dtype=np.float64)
            bs = np.zeros((n_loops, 1), dtype=np.float64)

        # Vertex colors
        color_cols = []
        for col_attr in getattr(mesh, "color_attributes", []):
            if len(col_attr.data) == n_loops:
                col_arr = np.empty(n_loops * 4, dtype=np.float64)
                col_attr.data.foreach_get('color', col_arr)
                color_cols.append(np.round(col_arr.reshape(-1, 4), 5))
        # Legacy vertex_colors fallback
        if not color_cols and hasattr(mesh, "vertex_colors"):
            for vcol in mesh.vertex_colors:
                if len(vcol.data) == n_loops:
                    col_arr = np.empty(n_loops * 4, dtype=np.float64)
                    vcol.data.foreach_get('color', col_arr)
                    color_cols.append(np.round(col_arr.reshape(-1, 4), 5))

        # Stack into one 2D array and find unique rows
        arrays = [positions, normals] + uv_cols + [tangents, bs] + color_cols
        full_data = np.hstack(arrays)
        return len(np.unique(full_data, axis=0))

    except Exception:
        pass

    # ---- Fallback: pure-Python set of tuples ----
    unique_corners = set()
    uv_layers_data = [uv.data for uv in mesh.uv_layers]
    color_layers_data = []
    if hasattr(mesh, "color_attributes") and mesh.color_attributes:
        color_layers_data = [col.data for col in mesh.color_attributes]
    elif hasattr(mesh, "vertex_colors"):
        color_layers_data = [col.data for col in mesh.vertex_colors]

    for loop_triangle in mesh.loop_triangles:
        for loop_index in loop_triangle.loops:
            loop = mesh.loops[loop_index]
            vert = mesh.vertices[loop.vertex_index]
            vx, vy, vz = round(vert.co.x, 5), round(vert.co.y, 5), round(vert.co.z, 5)
            nx, ny, nz = round(loop.normal.x, 5), round(loop.normal.y, 5), round(loop.normal.z, 5)
            all_uvs = [(round(data[loop_index].uv.x, 5), round(data[loop_index].uv.y, 5))
                       for data in uv_layers_data]
            all_cols = []
            for data in color_layers_data:
                if not data or loop_index >= len(data):
                    continue
                col = data[loop_index].color
                all_cols.append((round(col[0], 5), round(col[1], 5),
                                 round(col[2], 5), round(col[3], 5) if len(col) > 3 else 1.0))
            if use_tangents:
                tx, ty, tz = round(loop.tangent.x, 5), round(loop.tangent.y, 5), round(loop.tangent.z, 5)
                bs = round(loop.bitangent_sign, 5)
            else:
                tx = ty = tz = bs = 0.0
            corner_id = (
                vx, vy, vz, nx, ny, nz,
                *[comp for uvpair in all_uvs for comp in uvpair],
                tx, ty, tz, bs,
                *[chan for coltuple in all_cols for chan in coltuple]
            )
            unique_corners.add(corner_id)
    return len(unique_corners)


def get_triangulated_vertex_count(obj: bpy.types.Object) -> int:
    """Count unique triangulated vertices for a single object."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = obj_eval.to_mesh()
    try:
        mesh.calc_loop_triangles()
        try:
            mesh.calc_tangents()
            use_tangents = True
        except RuntimeError:
            use_tangents = False
        return _count_unique_corners(mesh, use_tangents)
    finally:
        obj_eval.to_mesh_clear()


def _cache_key(objects):
    """Build a cache key for a list of MESH objects."""
    return tuple(
        (obj.as_pointer(), obj.data.as_pointer() if obj.data else 0)
        for obj in objects if obj.type == 'MESH'
    )

def _get_cache():
    ns = bpy.app.driver_namespace
    if '_ln_vert_cache' not in ns:
        ns['_ln_vert_cache'] = {}
    return ns['_ln_vert_cache']

def _get_merged_vertex_count_bmesh(meshes, depsgraph):
    """BMesh-based merge fallback used when numpy is unavailable."""
    import bmesh
    batches = []
    all_uv_names = []
    all_color_names = []
    try:
        for obj in meshes:
            obj_eval = obj.evaluated_get(depsgraph)
            src_mesh = obj_eval.to_mesh()
            bm_src = bmesh.new()
            bm_src.from_mesh(src_mesh)
            mat = obj.matrix_world
            for v in bm_src.verts:
                v.co = mat @ v.co
            for uv in bm_src.loops.layers.uv:
                if uv.name not in all_uv_names:
                    all_uv_names.append(uv.name)
            for col in bm_src.loops.layers.color:
                if col.name not in all_color_names:
                    all_color_names.append(col.name)
            batches.append((obj_eval, src_mesh, bm_src))

        bm_merged = bmesh.new()
        for name in all_uv_names:
            bm_merged.loops.layers.uv.new(name)
        for name in all_color_names:
            bm_merged.loops.layers.color.new(name)

        for _, _, bm_src in batches:
            vert_map = [None] * len(bm_src.verts)
            for v in bm_src.verts:
                vert_map[v.index] = bm_merged.verts.new(v.co)
            bm_merged.verts.index_update()
            for face in bm_src.faces:
                verts = [vert_map[v.index] for v in face.verts]
                new_face = bm_merged.faces.new(verts)
                new_face.material_index = face.material_index
                new_face.smooth = face.smooth
                for uv_name in all_uv_names:
                    src_uv = bm_src.loops.layers.uv.get(uv_name)
                    dst_uv = bm_merged.loops.layers.uv.get(uv_name)
                    if src_uv and dst_uv:
                        for sl, dl in zip(face.loops, new_face.loops):
                            dst_uv[dl] = src_uv[sl]
                for col_name in all_color_names:
                    src_col = bm_src.loops.layers.color.get(col_name)
                    dst_col = bm_merged.loops.layers.color.get(col_name)
                    if src_col and dst_col:
                        for sl, dl in zip(face.loops, new_face.loops):
                            dst_col[dl] = src_col[sl]

        temp_mesh = bpy.data.meshes.new("__temp_merge_count__")
        try:
            bm_merged.to_mesh(temp_mesh)
            temp_mesh.calc_loop_triangles()
            try:
                temp_mesh.calc_tangents()
                use_tangents = True
            except RuntimeError:
                use_tangents = False
            return _count_unique_corners(temp_mesh, use_tangents)
        finally:
            bpy.data.meshes.remove(temp_mesh, do_unlink=True)

    finally:
        for obj_eval, src_mesh, bm_src in batches:
            bm_src.free()
            obj_eval.to_mesh_clear()
        if 'bm_merged' in locals():
            bm_merged.free()


def get_merged_vertex_count(objects: List[bpy.types.Object]) -> int:
    """
    Count unique triangulated vertices as if all MESH objects were merged into one mesh,
    matching the MSFS exporter's pre-export merge behaviour (multi_export.py:merge_objects).
    Uses numpy-vectorized foreach_get for speed; falls back to BMesh merge if numpy is
    unavailable. Results are cached by object identity.
    """
    meshes = [obj for obj in objects if obj.type == 'MESH']
    if not meshes:
        return 0

    key = _cache_key(meshes)
    cache = _get_cache()
    cached = cache.get(key)
    if cached is not None:
        return cached

    if len(meshes) == 1:
        result = get_triangulated_vertex_count(meshes[0])
        cache[key] = result
        return result

    depsgraph = bpy.context.evaluated_depsgraph_get()

    # ---- Numpy-vectorized path (no BMesh) ----
    eval_data = []
    try:
        import numpy as np

        all_uv_names = []
        all_color_names = []

        # First pass: evaluate meshes and discover layer names
        for obj in meshes:
            obj_eval = obj.evaluated_get(depsgraph)
            mesh = obj_eval.to_mesh()
            eval_data.append(None)
            try:
                mesh.calc_loop_triangles()
                try:
                    mesh.calc_tangents()
                    use_tangents = True
                except RuntimeError:
                    use_tangents = False
                for uv in mesh.uv_layers:
                    if uv.name not in all_uv_names:
                        all_uv_names.append(uv.name)
                for col in getattr(mesh, "color_attributes", []):
                    if col.name not in all_color_names:
                        all_color_names.append(col.name)
                if not all_color_names and hasattr(mesh, "vertex_colors"):
                    for vcol in mesh.vertex_colors:
                        if vcol.name not in all_color_names:
                            all_color_names.append(vcol.name)
                mat = obj.matrix_world
                R = np.array(mat.to_3x3(), dtype=np.float64)
                t = np.array(mat.translation, dtype=np.float64)
                try:
                    invR = np.linalg.inv(R)
                except np.linalg.LinAlgError:
                    invR = np.eye(3, dtype=np.float64)
                eval_data[-1] = (obj, obj_eval, mesh, use_tangents, R, t, invR)
            except Exception:
                obj_eval.to_mesh_clear()
                raise

        all_arrays = []

        # Second pass: extract and transform arrays per object
        for obj, obj_eval, mesh, use_tangents, R, t, invR in eval_data:
            n_loops = len(mesh.loops)
            if n_loops == 0:
                continue

            vert_indices = np.empty(n_loops, dtype=np.uint32)
            mesh.loops.foreach_get('vertex_index', vert_indices)

            vert_co = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
            mesh.vertices.foreach_get('co', vert_co)
            pos = vert_co.reshape(-1, 3)[vert_indices]
            pos = np.round(pos @ R.T + t, 5)

            norm_arr = np.empty(n_loops * 3, dtype=np.float64)
            mesh.loops.foreach_get('normal', norm_arr)
            n = norm_arr.reshape(-1, 3)
            n = n @ invR.T
            nn = np.linalg.norm(n, axis=1, keepdims=True)
            nn[nn == 0] = 1
            n = np.round(n / nn, 5)

            arrays_per_obj = [pos, n]

            for uv_name in all_uv_names:
                uv_layer = mesh.uv_layers.get(uv_name)
                if uv_layer:
                    uv_arr = np.empty(n_loops * 2, dtype=np.float64)
                    uv_layer.data.foreach_get('uv', uv_arr)
                    arrays_per_obj.append(np.round(uv_arr.reshape(-1, 2), 5))
                else:
                    arrays_per_obj.append(np.zeros((n_loops, 2), dtype=np.float64))

            if use_tangents:
                tang_arr = np.empty(n_loops * 3, dtype=np.float64)
                mesh.loops.foreach_get('tangent', tang_arr)
                tg = tang_arr.reshape(-1, 3)
                tg = tg @ invR.T
                tn = np.linalg.norm(tg, axis=1, keepdims=True)
                tn[tn == 0] = 1
                arrays_per_obj.append(np.round(tg / tn, 5))
            else:
                arrays_per_obj.append(np.zeros((n_loops, 3), dtype=np.float64))

            if use_tangents:
                bs_arr = np.empty(n_loops, dtype=np.float64)
                mesh.loops.foreach_get('bitangent_sign', bs_arr)
                arrays_per_obj.append(np.round(bs_arr, 5).reshape(-1, 1))
            else:
                arrays_per_obj.append(np.zeros((n_loops, 1), dtype=np.float64))

            for col_name in all_color_names:
                col_data = None
                if hasattr(mesh, "color_attributes"):
                    ca = mesh.color_attributes.get(col_name)
                    if ca is not None and len(ca.data) == n_loops:
                        col_data = ca.data
                if col_data is None and hasattr(mesh, "vertex_colors"):
                    vc = mesh.vertex_colors.get(col_name)
                    if vc is not None and len(vc.data) == n_loops:
                        col_data = vc.data
                if col_data is not None:
                    col_arr = np.empty(n_loops * 4, dtype=np.float64)
                    col_data.foreach_get('color', col_arr)
                    arrays_per_obj.append(np.round(col_arr.reshape(-1, 4), 5))
                else:
                    arrays_per_obj.append(np.zeros((n_loops, 4), dtype=np.float64))

            all_arrays.append(np.hstack(arrays_per_obj))

        if not all_arrays:
            return 0

        full_data = np.vstack(all_arrays)
        count = len(np.unique(full_data, axis=0))
        cache[key] = count
        return count

    except Exception:
        # Fallback: BMesh merge
        result = _get_merged_vertex_count_bmesh(meshes, depsgraph)
        cache[key] = result
        return result

    finally:
        for entry in eval_data:
            if entry is not None:
                _, obj_eval, mesh, *_ = entry
                try:
                    obj_eval.to_mesh_clear()
                except Exception:
                    pass

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
    logger.debug("=== Checking collections for valid LODs ===")
    results = []
    valid_collections_found = False
    scene = bpy.context.scene
    hide_hidden = getattr(scene, "hide_hidden_collections", False)
    root_layer_collection = bpy.context.view_layer.layer_collection
    lod_pattern = re.compile(r"_LOD\d+$")
    max_vertex_limit = VERTEX_COUNTS[-1]

    # Pre-count LOD collections for progress reporting
    lod_collections = [c for c in bpy.data.collections if lod_pattern.search(c.name.strip())]
    total = len(lod_collections)
    wm = context.window_manager if context else None
    if wm:
        wm.progress_begin(0, total)

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
        total_vertices = get_merged_vertex_count(list(collection.objects))
        if total_vertices > max_vertex_limit:
            results.append((collection.name, total_vertices, -1.0))
            logger.error(f"Vertex Count out of range for collection: {collection_name}")
        else:
            interpolated_size = interpolate_screen_size(total_vertices)
            results.append((collection.name, total_vertices, interpolated_size))
            logger.debug(f"Interpolated Screen Size for {collection_name}: {interpolated_size:.2f}%")

        if wm:
            wm.progress_update(idx)

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
    scene = bpy.context.scene
    lod_groups = getattr(scene, "msfs_multi_exporter_lod_groups", None)
    if not lod_groups:
        logger.error("No MSFS LOD groups found. Is the MSFS Exporter addon enabled?")
        return

    lod_data = count_vertices_in_lod_collections()
    logger.debug(f"LOD Data: {lod_data}")

    if not lod_data:
        return

    for lod_group in lod_groups:
        logger.debug(f"Processing LOD Group: {lod_group.group_name}")
        for lod in lod_group.lods:
            if lod.collection:
                collection_name = lod.collection.name
                logger.debug(f"  Matching collection: {collection_name}")
                for name, _, screen_size in lod_data:
                    if name == collection_name:
                        increment = scene.screen_space_margin / 100.0
                        if screen_size >= 0:
                            raw_value = math.ceil(screen_size + screen_size * increment)
                            if increment != 0.0 and raw_value < 1 and screen_size > 0:
                                raw_value = 1
                            lod.lod_value = raw_value
                            logger.debug(f"    Updated LOD Value: {lod.lod_value} for {collection_name}")
                        else:
                            logger.debug(f"    Vertex Count out of range for {collection_name}, skipping LOD update.")
                        break

def register():
    pass

def unregister():
    pass