# ln_lod_screen.py
# Pure MSFS screen-space math for the LN LODs LOD Viewer / calculator.
# ---------------------------------------------------------------
# No bpy import on purpose: this module is importable (and unit-tested with
# pytest) outside Blender.
#
# Two screen-space models are supported, selected per scene by the user:
#
#   MSFS2024 (default) — reproduces the official MSFS 2024 behaviour, i.e. the
#     Asobo `lod_tools_msfs_2024` Blender plug-in geometry-node chain:
#
#         ratio   = radius * lod_factor / (max(distance, 0.001) * tan(fov_y / 2))
#         percent = min(ratio, 10.0) * 100        -> 0 .. 1000 %
#
#     The vertical FOV is the LIVE viewport FOV (perspective: 2*atan(1/m[1][1])
#     from region_3d.window_matrix; orthographic: a fake 1° FOV).
#     Note: 2024 native content does NOT clamp to 1000 % on entering the
#     bounding sphere — the projected size keeps following the formula, so
#     1000 % is only reached close to the sphere centre. Confirmed by Asobo
#     (DevSupport "Bounding Sphere Issue / LODs / Screen Size", EPellissier):
#     the "1000 % from the sphere surface" rule is MSFS 2020 behaviour, which
#     2024 only reproduces for backwards-compatible 2020 packages.
#
#   MSFS2020 (legacy) — the historical LN LODs formula, kept ONLY for comparing
#     backwards-compatible 2020 content:
#
#         percent = min(radius / max(distance, 0.001) * 1000, 1000)
#
#     FOV-independent (it implicitly assumes a ~11.4° vertical FOV, i.e.
#     tan(fov/2) = 0.1, which is why it over-reports by tan(fov/2)/0.1 at any
#     realistic viewport) and clamped to 1000 % as soon as the camera reaches
#     the bounding-sphere surface.
#
# Ground truth (local SDK, read at C:\MSFS 2024 SDK):
#   - GN node group `.Get Vertical Screen Ratio` / `.Get_Bounding_Sphere_Distance`
#     in `lod_tools_msfs_2024/datafiles/assets/nodes/lod_viewer-3_3_0.blend`
#     (percent cap 1000 %; distance floored at 0.001; LOD Factor floored at
#     0.01 in the constants group).
#   - `lod_tools_msfs_2024/lod_limits.py` — official closed-form vertex-count
#     curve (0..1000 verts -> 0 %, 1000..2500 -> 1 %, linear 2500..250000 ->
#     100 %, sqrt/parabolic above 100 %).
#   - `lod_tools_msfs_2024/lod_camera.py` — viewport FOV extraction.
#   - `lod_tools_msfs_2024/bounding_volume.py` — the plug-in's bounding sphere
#     convention: AABB centre, radius = half the AABB diagonal.
#   - `lod_tools_msfs_2024/prefs.py` — render presets stamp a single LOD Factor.
#
# Reconciliation rule: where the SDK documentation and the official plug-in
# disagree, the plug-in (newer) is ground truth.

import math

# Vertical FOV used when no live viewport is available (background mode /
# region_data is None): the official GN constants-group default, 65°.
DEFAULT_FOV_Y = 1.13446  # radians ~= 65°

# Orthographic viewport fake FOV (official lod_camera._ORTHO_FAKE_FOV).
ORTHO_FAKE_FOV = math.radians(1.0)

# Screen-size ratio cap: MIN(ratio, 10.0) * 100 -> 1000 (%).
MAX_RATIO = 10.0
MAX_SCREEN_SIZE_PERCENT = MAX_RATIO * 100.0

# Distance floor (official GN: MAX(distance, 0.001)) against div-by-zero.
DISTANCE_FLOOR = 0.001

# Official curve constants (lod_limits.py: tw_Lod_* / Default_*).
MS0_MAX_VERTEX_COUNT = 1000        # <= -> 0%
MS1_MAX_VERTEX_COUNT = 2500        # <= -> 1% (min size floor at 1%)
MS100_MAX_VERTEX_COUNT = 250000    # -> 100%
DEFAULT_LAST_LOD_MIN_RATIO = 0.001          # 0.1% last-LOD floor
DEFAULT_SECOND_TO_LAST_LOD_MIN_RATIO = 0.01  # 1% second-to-last-LOD floor
EMPTY_LAST_LOD_FACTOR = 0.01  # empty last LOD: 0.1% * 0.01 = 0.001% floor
CURVE_POWER_LINEAR = 1
CURVE_POWER_ABOVE_100 = 2
FLOAT_EPS = 1e-6

# Official render presets (prefs.py RenderPreset): picking a preset *stamps*
# the single LOD Factor with its value (they never stack).
RENDER_PRESETS = {"LOW": 0.25, "MEDIUM": 0.5, "HIGH": 1.0, "ULTRA": 2.0}
DEFAULT_RENDER_PRESET = "HIGH"
LOD_FACTOR_MIN = 0.01
LOD_FACTOR_MAX = 2.0

# Per-preset vertex-budget curve multipliers — MSFS 2024 SDK docs
# `LOD_Selection_System.htm` ("Vertex Count Limits" table): the four
# graphics-preset min-size columns are the High column scaled by
# {Ultra 1/sqrt(2) ~= 0.707, High 1, Medium sqrt(2) ~= 1.414, Low 2}, which
# equals 1/sqrt(effective factor) for the official factors above. Stamped
# presets reproduce the official table exactly; custom factor values
# interpolate between the preset columns.
RENDER_PRESET_CURVE_MULTIPLIERS = {
    name: 1.0 / math.sqrt(factor) for name, factor in RENDER_PRESETS.items()
}

# Screen-space models (scene enum in ln_pro_extras).
MODEL_MSFS2024 = "MSFS2024"
MODEL_MSFS2020 = "MSFS2020"
DEFAULT_SCREEN_SPACE_MODEL = MODEL_MSFS2024
SCREEN_SPACE_MODELS = (MODEL_MSFS2024, MODEL_MSFS2020)


def effective_lod_factor(lod_factor):
    """Official constants-group floor: effective = max(lod_factor, 0.01).

    Mirrors the GN constants-group `Math MAXIMUM` (in1 = 0.01) guarding the
    `.Get Vertical Screen Ratio` LOD Factor input.
    """
    try:
        value = float(lod_factor)
    except (TypeError, ValueError):
        value = 1.0
    return max(value, LOD_FACTOR_MIN)


def preset_curve_multiplier(lod_factor):
    """Per-preset vertex-budget curve multiplier: 1 / sqrt(effective factor).

    Ultra 1/sqrt(2) ~= 0.707 (more vertices allowed at the same screen size),
    High 1, Medium sqrt(2) ~= 1.414, Low 2 (stricter budget).
    """
    return 1.0 / math.sqrt(effective_lod_factor(lod_factor))


def scale_screen_sizes_for_preset(sizes_pct, lod_factor):
    """Scale screen sizes (%) by the preset vertex-budget multiplier.

    Applied to raw curve values BEFORE the official floors/cascade so the
    engine's absolute floors (last LOD 0.1 % / 0.001 % empty, second-to-last
    1 %) are preserved regardless of graphics preset. Negative values (the
    calculator's out-of-range sentinel) pass through unchanged; positives are
    capped at MAX_SCREEN_SIZE_PERCENT.
    """
    multiplier = preset_curve_multiplier(lod_factor)
    return [
        s if s < 0.0 else min(s * multiplier, MAX_SCREEN_SIZE_PERCENT)
        for s in sizes_pct
    ]


def preset_for_factor(lod_factor):
    """Preset whose anchor factor exactly equals `lod_factor`, else None.

    Anchors are the four canonical floats 0.25/0.5/1.0/2.0, so typed values
    like `1` or `0.5` match their preset. Exact equality is deliberate — a
    slider drag landing off-anchor must show the Custom control instead of
    flickering between presets while dragging.
    """
    for preset, factor in RENDER_PRESETS.items():
        if lod_factor == factor:
            return preset
    return None


def aabb_half_diagonal(min_coord, max_coord):
    """Radius of the AABB half-diagonal: |max - min| * 0.5.

    The bounding-sphere convention used by the official MSFS 2024 plug-in
    (`bounding_volume.get_msfs_bounding_sphere`: centre = AABB centre,
    radius = norm(max - min) * 0.5) — and therefore by the sim's screen-size
    approximation. Accepts any 3-component sequences (Vector, tuple, list).
    """
    dx = float(max_coord[0]) - float(min_coord[0])
    dy = float(max_coord[1]) - float(min_coord[1])
    dz = float(max_coord[2]) - float(min_coord[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz) * 0.5


def viewport_vertical_fov(m11, is_perspective):
    """Vertical FOV in radians from a 3D-viewport projection-matrix Y scale.

    Official lod_camera.get_viewport_vertical_fov parity:
      - perspective -> 2 * atan(1 / m[1][1])  (m11 = window_matrix[1][1])
      - orthographic -> fake 1° FOV
      - unusable matrix (m11 <= 0) -> None (caller falls back to DEFAULT_FOV_Y).
    """
    if not is_perspective:
        return ORTHO_FAKE_FOV
    if m11 <= 0.0:
        return None
    return 2.0 * math.atan(1.0 / m11)


def screen_size_percent(radius, distance, fov_y, lod_factor=1.0,
                        model=DEFAULT_SCREEN_SPACE_MODEL):
    """Vertical screen size in percent (0..1000) for the selected model.

    MSFS2024 (default) — official GN `.Get Vertical Screen Ratio` chain:

        ratio   = radius * lod_factor / (max(distance, 0.001) * tan(fov_y / 2))
        percent = MIN(ratio, 10.0) * 100

    MSFS2020 (legacy) — the historical LN formula:

        percent = MIN(radius / max(distance, 0.001) * 1000, 1000)

    Returns 0.0 for radius <= 0, or for unusable input (fov <= 0 in the 2024
    model; a degenerate FOV simply cannot be used). Distance <= 0 is floored
    (-> 1000 % cap, parity).
    """
    if radius <= 0.0:
        return 0.0
    d = max(float(distance), DISTANCE_FLOOR)
    if model == MODEL_MSFS2020:
        ratio = float(radius) / d
        return min(ratio, 1.0) * MAX_SCREEN_SIZE_PERCENT
    if fov_y <= 0.0:
        return 0.0
    half_tan = math.tan(fov_y / 2.0)
    if half_tan == 0.0:
        return 0.0
    ratio = (float(radius) * float(lod_factor)) / (d * half_tan)
    return min(ratio, MAX_RATIO) * 100.0


def lod_switch_distance(radius, min_size_pct, fov_y, lod_factor=1.0,
                        model=DEFAULT_SCREEN_SPACE_MODEL):
    """Camera distance at which a given screen-size percent is reached.

    Inverse of `screen_size_percent`:
      - MSFS2024: d = radius * lod_factor * 100 / (min_size * tan(fov/2))
      - MSFS2020: d = radius * 1000 / min_size

    min_size_pct <= 0 -> infinity (minSize 0 keeps the LOD always eligible).
    """
    if radius <= 0.0:
        return float("inf")
    if min_size_pct <= 0.0:
        return float("inf")
    if model == MODEL_MSFS2020:
        return (float(radius) * MAX_SCREEN_SIZE_PERCENT) / float(min_size_pct)
    if fov_y <= 0.0:
        return float("inf")
    half_tan = math.tan(fov_y / 2.0)
    if half_tan == 0.0:
        return float("inf")
    return (float(radius) * float(lod_factor) * 100.0) / (
        float(min_size_pct) * half_tan
    )


def lowest_screen_size_from_vcount(v_count):
    """Official closed-form curve (lod_limits.lowest_screen_size_from_vcount).

    Returns min size in ratio units (0..1 for <= 100 %; above 1 for very dense
    meshes; multiply by 100 for percent):
        0 <= v <= 1000           -> 0
        1000 < v <= 2500         -> 0.01    (1%)
        v > 2500                 -> linear 2500..250000 (0.01..1.0),
                                    sqrt/parabolic above 100%.
    """
    if v_count <= MS0_MAX_VERTEX_COUNT:
        return 0.0
    if v_count <= MS1_MAX_VERTEX_COUNT:
        return 0.01
    value = (v_count - MS1_MAX_VERTEX_COUNT) / (
        MS100_MAX_VERTEX_COUNT - MS1_MAX_VERTEX_COUNT
    )
    power = CURVE_POWER_ABOVE_100 if value >= 1.0 else CURVE_POWER_LINEAR
    result = math.pow(value, 1.0 / power)
    return result * 0.99 + 0.01


def max_vertex_count(screen_size):
    """Official inverse (lod_limits.max_vertex_count); screen_size in ratio
    units. Returns the maximum vertex count allowed at that min size."""
    if screen_size <= 0.01 - FLOAT_EPS:
        return MS0_MAX_VERTEX_COUNT
    value = max(0.0, float(screen_size) - 0.01) / 0.99
    power = CURVE_POWER_ABOVE_100 if screen_size > 1.0 else CURVE_POWER_LINEAR
    result = math.pow(value, power)
    if value == 0.0:
        result = 0.0
    return math.floor(
        MS1_MAX_VERTEX_COUNT
        + result * (MS100_MAX_VERTEX_COUNT - MS1_MAX_VERTEX_COUNT)
        + 0.5
    )


def apply_lod_size_floors_and_cascade(sizes_pct, vertex_counts):
    """Official min-size floors + reverse monotonic cascade, in percent.

    Parity of the SDK `data_properties.compute_stats` floors followed by the
    `lod_viewer` reverse loop ("Loop lods in reverse to make sure minSizes
    are always increasing"):

      - LOD i == n-1 (last): floor = 0.1 % (0.001 % when the LOD is empty)
      - LOD i == n-2 (second-to-last): floor = 1 %
      - all other LODs: no floor
      - reverse pass: sizes[i] = max(sizes[i], sizes[i+1]) (monotonic cascade)

    `len(sizes_pct) == len(vertex_counts) == number of LOD levels in the group`
    (index 0 = LOD0, ascending by LOD number). Input lists are never mutated.
    """
    n = len(sizes_pct)
    sizes = [float(s) for s in sizes_pct]
    next_est = 0.0
    for i in range(n - 1, -1, -1):
        if i == n - 1:  # last LOD
            empty_factor = EMPTY_LAST_LOD_FACTOR if vertex_counts[i] == 0 else 1.0
            floor = DEFAULT_LAST_LOD_MIN_RATIO * empty_factor * 100.0
        elif i == n - 2:  # second-to-last LOD
            floor = DEFAULT_SECOND_TO_LAST_LOD_MIN_RATIO * 100.0
        else:
            floor = 0.0
        est = max(sizes[i], floor)
        sizes[i] = max(est, next_est)
        next_est = sizes[i]
    return sizes
