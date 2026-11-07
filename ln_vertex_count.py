# ln_vertex_count.py
# Official MSFS 2024 glTF vertex-count semantics (parity port).
# ---------------------------------------------------------------
# Behaviourally faithful port of the official Asobo SDK LOD plug-in's vertex
# counting — `C:\MSFS 2024 SDK\Tools\Blender\addons\lod_tools_msfs_2024\vertex_count.py`
# (tangents are disabled in the official count; see the commented-out line in
# `get_gltf_vertex_count`). The `obj_utils.get_object_instances` dependency is
# inlined (`_has_instancing` / `_object_instances`); the tangent/merge path
# (`_get_loop_tangents`, `quantize_snorm`, `triangulate_mesh`,
# `prepare_*_for_tangent_compute`, `get_merged_trimesh_of_objects`) is
# intentionally NOT ported, matching the official count having tangents off.
#
# Pure test seam: `_count_unique_rows`, `_join_loop_attributes` and
# `_sum_primitive_counts` are numpy-only and unit-tested without Blender.

from __future__ import annotations

from typing import Iterator

import bpy
import numpy as np

# Rounding digit used for normal/tangent rounding (official parity)
ROUNDING_DIGIT = 4  # from builtin gltf exporter


def _get_loop_vertex_indices(mesh: bpy.types.Mesh) -> np.ndarray:
    loop_vertex_indices = np.empty(len(mesh.loops), dtype=np.uint32)
    mesh.loops.foreach_get("vertex_index", loop_vertex_indices)
    return loop_vertex_indices


# region Position


def _get_loop_positions(
    mesh: bpy.types.Mesh, loop_vertex_indices: np.ndarray | None = None
) -> np.ndarray | None:
    """Get vertex positions for each mesh loop (face corner).

    You can provide a precomputed loop-to-vertex mapping. Providing this array avoids
    allocating and populating a new loop vertex index array on each call.
    """
    positions = mesh.attributes.get("position", None)
    if not positions:
        return None
    locs = np.empty((len(mesh.vertices), 3), dtype=np.float32)
    positions.data.foreach_get("vector", np.ravel(locs))

    if loop_vertex_indices is None:
        loop_vertex_indices = _get_loop_vertex_indices(mesh)
    return locs[loop_vertex_indices]


# endregion

# region Normals


def _normalize_vecs(vectors):
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    np.divide(vectors, norms, out=vectors, where=norms != 0)


def _get_loop_normals(mesh: bpy.types.Mesh) -> np.ndarray | None:
    """Get normal for each mesh loop (face corner)."""
    # Update split normals cache
    if bpy.app.version < (4, 2, 0):
        mesh.calc_normals_split()
    normals = np.empty((len(mesh.loops), 3), dtype=np.float32)
    mesh.corner_normals.foreach_get("vector", np.ravel(normals))

    # blender gltf rounding
    normals = np.round(normals, ROUNDING_DIGIT)

    # Force normalization of normals in case some normals are not (why ?)
    _normalize_vecs(normals)
    # Replace zero normals with the unit UP vector.
    # Seems to happen sometimes with degenerate tris?
    is_zero = ~normals.any(axis=1)
    normals[is_zero, 2] = 1

    # Quantize to int8 SNORM
    # normals = quantize_snorm(normals)

    return normals


# endregion

# region UVs


def _get_loop_tex_coords(
    mesh: bpy.types.Mesh, uv_index: int
) -> np.ndarray | None:
    try:
        layer = mesh.uv_layers[uv_index]
    except IndexError:
        return None
    uvs = np.empty((len(mesh.loops), 2), dtype=np.float32)
    layer.uv.foreach_get("vector", np.ravel(uvs))

    return uvs


def _get_all_loop_tex_coords(mesh: bpy.types.Mesh) -> list[np.ndarray]:
    tex_coord_max = 0
    if mesh.uv_layers.active:
        tex_coord_max = len(mesh.uv_layers)
    tex_coords = []
    for i in range(tex_coord_max):
        tcoord = _get_loop_tex_coords(mesh, i)
        if tcoord is None:
            continue
        tex_coords.append(tcoord)

    return tex_coords


# endregion

# region Vertex Color


def _get_loop_colors(
    mesh: bpy.types.Mesh,
    name: str,
    loop_vertex_indices: np.ndarray | None = None,
) -> np.ndarray | None:
    """Get color for each loop (face corner).

    You can provide a precomputed loop-to-vertex mapping. Providing this array avoids
    allocating and populating a new loop vertex index array on each call.
    """
    attr = mesh.color_attributes.get(name, None)
    if not attr:
        return None

    if attr.domain == "POINT":
        loop_colors = np.empty((len(mesh.vertices), 4), dtype=np.float32)
    elif attr.domain == "CORNER":
        loop_colors = np.empty((len(mesh.loops), 4), dtype=np.float32)

    attr.data.foreach_get("color", np.ravel(loop_colors))

    if attr.domain == "POINT":
        if loop_vertex_indices is None:
            loop_vertex_indices = _get_loop_vertex_indices(mesh)
        loop_colors = loop_colors[loop_vertex_indices]

    return loop_colors


def _get_all_loop_colors(
    mesh: bpy.types.Mesh,
    loop_vertex_indices: np.ndarray | None = None,
) -> list[np.ndarray]:
    colors = []
    for attr in mesh.color_attributes:
        color = _get_loop_colors(mesh, attr.name, loop_vertex_indices)
        if color is None:
            continue
        colors.append(color)

    return colors


# endregion


def _primitive_split(
    mesh: bpy.types.Mesh,
    use_materials: bool = True,
) -> dict[int, np.ndarray] | None:
    """Split mesh into primitives.

    Code from builtin gltf exporter. Buckets triangulated loops by material index.
    """
    # Calculate triangles and sort them into primitives.
    try:
        mesh.calc_loop_triangles()
        loop_indices = np.empty(len(mesh.loop_triangles) * 3, dtype=np.uint32)
        # Indices of mesh loops that make up the triangle
        mesh.loop_triangles.foreach_get("loops", loop_indices)

    except Exception:
        # For some not valid meshes, we can't get loops without errors
        # We already displayed a Warning message after validate() check, so here
        # we can return without a new one
        return None
    prim_indices = {}
    if not use_materials:  # Only for None. For placeholder and export, keep primitives
        # Put all vertices into one primitive
        prim_indices[-1] = loop_indices
    else:
        # Bucket by material index.
        tri_material_idxs = np.empty(len(mesh.loop_triangles), dtype=np.uint16)
        mesh.loop_triangles.foreach_get("material_index", tri_material_idxs)
        loop_material_idxs = np.repeat(
            tri_material_idxs, 3
        )  # material index for every loop
        unique_material_idxs = np.unique(tri_material_idxs)
        del tri_material_idxs

        for mat_i in unique_material_idxs:
            prim_indices[mat_i] = loop_indices[
                loop_material_idxs == mat_i
            ]
    return prim_indices


def _count_unique_rows(dots: np.ndarray) -> int:
    dots = np.ascontiguousarray(dots)
    row_view = dots.view(np.dtype((np.void, dots.dtype.itemsize * dots.shape[1])))
    return len(np.unique(row_view))


def _join_loop_attributes(attribs: list[np.ndarray]) -> np.ndarray:
    """Stack per-loop attribute columns into one dots matrix (pure numpy).

    Test seam: does not require Blender. Casts int to float ("safe"), matching the
    official `np.concatenate(all_attribs, axis=1, casting="safe")` step.
    """
    return np.concatenate(attribs, axis=1, casting="safe")


def _sum_primitive_counts(
    full_dots: np.ndarray, primitives: dict[int, np.ndarray]
) -> int:
    """Count unique rows per primitive (per-material loop bucket) and sum (pure numpy).

    Test seam: does not require Blender.
    """
    count = 0
    for _, loop_indices in primitives.items():
        count += _count_unique_rows(full_dots[loop_indices])
    return count


def get_gltf_vertex_count(
    mesh: bpy.types.Mesh,
) -> int:
    """Official glTF vertex count for one (evaluated) mesh.

    Attributes are concatenated per loop and unique rows are counted per material
    primitive, reproducing the glTF exporter's primitive extraction.
    """
    # Mesh must be triangulated for safe tangent compute
    # or mesh.calc_tangents can trigger
    # RuntimeError: Error: Tangent space can only be computed for tris/quads, aborting
    primitives = _primitive_split(mesh)
    if not primitives:
        return 0
    loop_vertex_indices = _get_loop_vertex_indices(mesh)
    loop_positions = _get_loop_positions(mesh, loop_vertex_indices)
    loop_normals = _get_loop_normals(mesh)
    # loop_tangents = _get_loop_tangents(trimesh)  # tangents disabled (official count)
    tex_coords = _get_all_loop_tex_coords(mesh)
    vertex_colors = _get_all_loop_colors(mesh, loop_vertex_indices)

    all_attribs = [loop_positions, loop_normals, *tex_coords, *vertex_colors]
    full_dots = _join_loop_attributes(all_attribs)

    return _sum_primitive_counts(full_dots, primitives)


# region Instancing (inline of obj_utils.get_object_instances)


def _has_instancing(obj: bpy.types.Object) -> bool:
    return getattr(obj, "instance_collection", None) or (
        getattr(obj, "instance_type", "NONE") != "NONE"
    )


def _object_instances(
    obj_eval: bpy.types.Object, depsgraph: bpy.types.Depsgraph
) -> Iterator[bpy.types.Object]:
    """Yield instances spawned by an object (collection / vert/face instancing).

    WARNING: each yielded object is a temporary depsgraph reference, only
    valid until the generator resumes (i.e. the next loop iteration).
    Do NOT store it or convert this generator to a list — use each object
    immediately inside your `for` loop before moving to the next one.
    """
    for inst in depsgraph.object_instances:
        if (
            inst.is_instance
            and inst.object
            and inst.parent == obj_eval
        ):
            yield inst.object


# endregion


def get_obj_vcount(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> int:
    """Official vertex count for one object: evaluated mesh + instanced copies."""
    vcount = 0
    obj_eval = obj.evaluated_get(depsgraph)
    mesh = None
    try:
        mesh = obj_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    except RuntimeError:
        # No Mesh data
        obj_eval.to_mesh_clear()
    if mesh:
        vcount += get_gltf_vertex_count(mesh)
    obj_eval.to_mesh_clear()

    if _has_instancing(obj_eval):
        for inst in _object_instances(obj_eval, depsgraph):
            mesh = None
            try:
                mesh = inst.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            except RuntimeError:
                # No Mesh data
                inst.to_mesh_clear()
                continue
            if mesh:
                vcount += get_gltf_vertex_count(mesh)
            inst.to_mesh_clear()
    return vcount


def get_gltf_objects_vertex_count(
    objects: Iterator[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph | None = None,
) -> int:
    """
    Calculate vertex count by reproducing gltf export steps defined in primitive_extract.py
    module (official): per-object evaluated meshes, per-material primitives, instances
    included. Sums per-object counts.
    """
    if depsgraph is None:
        depsgraph = bpy.context.evaluated_depsgraph_get()

    vcount = 0
    for obj in objects:
        vcount += get_obj_vcount(obj, depsgraph)

    return vcount
