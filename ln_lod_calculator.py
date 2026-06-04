# ln_lod_calculator.py
# Contiene funzioni di calcolo e logica LOD
# -----------------------------------------------------------

import bpy
import math
import re
import logging
import numpy as np

# Initialize logging
logger = logging.getLogger(__name__)

# Predefined Data for Vertex Count and High Column
# Range 0-100% è ora perfettamente lineare
# Range >100% aggiornato tramite l'indagine in-sim
DATA = {
    0: 0,
    25000: 10,
    50000: 20,
    75000: 30,
    100000: 40,
    125000: 50,
    150000: 60,
    175000: 70,
    200000: 80,
    225000: 90,
    250000: 100,
    302524: 110,
    390763: 125,
    497474: 141,
    563110: 150,
    767080: 175,
    1002498: 200,
    1269600: 225,
    1568200: 250,
    2260000: 300,
    2413600: 310,
    2653000: 325,
    3078300: 350,
    3534700: 375,
    4022700: 400,
    4542400: 425,
    5093500: 450,
    5676100: 475,
    6290400: 500,
    6995737: 525,
    7613700: 550,
    8322700: 575,
    9063000: 600,
    9835000: 625,
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

VERTEX_COUNTS = list(DATA.keys())
HIGH_VALUES   = list(DATA.values())

def catmull_rom(t, p0, p1, p2, p3):
    c1 = 2.0 * p1
    c2 = p2 - p0
    c3 = (2.0 * p0) - (5.0 * p1) + (4.0 * p2) - p3
    c4 = (-p0) + (3.0 * p1) - (3.0 * p2) + p3
    return 0.5 * (c1 + (c2 * t) + (c3 * t * t) + (c4 * t * t * t))

def interpolate_screen_size(vertex_count):
    if vertex_count <= VERTEX_COUNTS[0]:
        return HIGH_VALUES[0]
    elif vertex_count >= VERTEX_COUNTS[-1]:
        return HIGH_VALUES[-1]

    for i in range(len(VERTEX_COUNTS) - 1):
        x0, x1 = VERTEX_COUNTS[i], VERTEX_COUNTS[i+1]
        if x0 <= vertex_count <= x1:
            t = (vertex_count - x0) / (x1 - x0)
            y0, y1 = HIGH_VALUES[i], HIGH_VALUES[i+1]

            p0 = HIGH_VALUES[i - 1] if i > 0 else y0
            p3 = HIGH_VALUES[i + 2] if i + 2 < len(HIGH_VALUES) else y1

            return catmull_rom(t, p0, y0, y1, p3)
    return 0

# --------------------------------------------------------------------
# VETTORIZZAZIONE DEL CALCOLO DEI VERTICI TRAMITE NUMPY
# --------------------------------------------------------------------
def get_triangulated_vertex_count(obj):
    """
    Sostituisce il lento ciclo python in favore di NumPy.
    Aggiornato per Blender 4.1+ (corner_normals).
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(depsgraph)

    mesh = obj_eval.to_mesh()
    try:
        mesh.calc_loop_triangles()
        num_triangles = len(mesh.loop_triangles)
        if num_triangles == 0:
            return 0
            
        # Estraiamo gli indici dei loop che formano triangoli
        loop_indices = np.empty(num_triangles * 3, dtype=np.int32)
        mesh.loop_triangles.foreach_get("loops", loop_indices)
        
        num_loops = len(mesh.loops)
        vertex_indices = np.empty(num_loops, dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", vertex_indices)
        
        # Coordinate dei vertici
        num_vertices = len(mesh.vertices)
        verts_co = np.empty(num_vertices * 3, dtype=np.float32)
        mesh.vertices.foreach_get("co", verts_co)
        verts_co.shape = (num_vertices, 3)
        
        loop_verts_co = verts_co[vertex_indices]

        # Normali (Gestione compatibilità pre e post Blender 4.1)
        normals = np.empty(num_loops * 3, dtype=np.float32)
        if hasattr(mesh, "corner_normals"):
            # API per Blender 4.1, 4.2+
            mesh.corner_normals.foreach_get("vector", normals)
        elif hasattr(mesh, "calc_normals_split"):
            # Fallback (Blender <= 4.0)
            mesh.calc_normals_split()
            mesh.loops.foreach_get("normal", normals)
        normals.shape = (num_loops, 3)
        
        # Creiamo un array in cui impileremo tutte le proprietà del loop
        attributes = [loop_verts_co, normals]
        
        # UVs
        for uv_layer in mesh.uv_layers:
            uvs = np.empty(num_loops * 2, dtype=np.float32)
            uv_layer.data.foreach_get("uv", uvs)
            uvs.shape = (num_loops, 2)
            attributes.append(uvs)
            
        # Vertex Colors (Gestione compatibilità pre e post Blender 3.3)
        color_layers_data = []
        if hasattr(mesh, "color_attributes") and len(mesh.color_attributes) > 0:
            color_layers_data = mesh.color_attributes
        elif hasattr(mesh, "vertex_colors") and len(mesh.vertex_colors) > 0:
            color_layers_data = mesh.vertex_colors
            
        for col_layer in color_layers_data:
            cols = np.empty(num_loops * 4, dtype=np.float32)
            col_layer.data.foreach_get("color", cols)
            cols.shape = (num_loops, 4)
            attributes.append(cols)
            
        # Tangenti
        if len(mesh.uv_layers) > 0:
            try:
                mesh.calc_tangents()
                tangents = np.empty(num_loops * 3, dtype=np.float32)
                mesh.loops.foreach_get("tangent", tangents)
                tangents.shape = (num_loops, 3)
                
                bitangent_signs = np.empty(num_loops, dtype=np.float32)
                mesh.loops.foreach_get("bitangent_sign", bitangent_signs)
                bitangent_signs.shape = (num_loops, 1)
                
                attributes.append(tangents)
                attributes.append(bitangent_signs)
            except RuntimeError:
                logger.warning(f"Cannot calculate tangents for {obj.name}, skipping.")
                pass
                
        # "Incolliamo" tutte le colonne assieme e preleviamo solo i loop triangolati
        stacked = np.hstack(attributes)
        tri_loops = stacked[loop_indices]
        
        # Arrotondiamo per simulare la tolleranza `round(val, 5)` dell'algoritmo manuale 
        # e usiamo `unique` per escludere i glTF vertex duplicati
        tri_loops = np.round(tri_loops, decimals=5)
        unique_vertices = np.unique(tri_loops, axis=0)
        
        return len(unique_vertices)

    finally:
        obj_eval.to_mesh_clear()


def find_layer_collection(layer_coll: bpy.types.LayerCollection, coll: bpy.types.Collection):
    if layer_coll.collection == coll:
        return layer_coll

    for child in layer_coll.children:
        found = find_layer_collection(child, coll)
        if found is not None:
            return found

    return None
        
def count_vertices_in_lod_collections():
    logger.debug("=== Checking collections for valid LODs ===")
    results = []
    valid_collections_found = False
    
    scene = bpy.context.scene
    hide_hidden = getattr(scene, "hide_hidden_collections", False)  
    
    root_layer_collection = bpy.context.view_layer.layer_collection
    lod_pattern = re.compile(r"_LOD\d+$")

    max_vertex_limit = VERTEX_COUNTS[-1]

    for collection in bpy.data.collections:
        collection_name = collection.name.strip()
        
        if hide_hidden:
            layer_coll = find_layer_collection(root_layer_collection, collection)
            if layer_coll is not None and not layer_coll.visible_get():
                logger.debug(f"Skipping hidden child-of-hidden collection: {collection_name}")
                continue                
        logger.debug(f"Checking collection: {collection_name}")

        if lod_pattern.search(collection_name):
            logger.debug(f"Matched LOD collection: {collection_name}")
            valid_collections_found = True
            total_vertices = 0

            for obj in collection.objects:
                if obj.type == 'MESH':
                    mesh_vertex_count = get_triangulated_vertex_count(obj)
                    total_vertices += mesh_vertex_count

            if total_vertices > max_vertex_limit:
                results.append((collection.name, total_vertices, -1.0))
                logger.error(f"Vertex Count out of range for collection: {collection_name}")
            else:
                interpolated_size = interpolate_screen_size(total_vertices)
                results.append((collection.name, total_vertices, interpolated_size))
                logger.debug(f"Interpolated Screen Size for {collection_name}: {interpolated_size:.2f}%")
        else:
            logger.debug(f"Collection did not match LOD pattern: {collection_name}")

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
        logger.debug("No MSFS LOD groups found.")
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
                            raw_value = math.ceil(screen_size + (screen_size * increment))

                            if increment != 0.0 and raw_value < 1 and screen_size > 0:
                                raw_value = 1

                            lod.lod_value = raw_value
                            logger.debug(
                                f"    Updated LOD Value: {lod.lod_value} for {collection_name}"
                            )
                        else:
                            logger.debug(
                                f"    Vertex Count out of range for {collection_name}, skipping update."
                            )
                        break
                else:
                    logger.debug(f"    No matching data found for collection: {collection_name}")

def register():
    pass

def unregister():
    pass