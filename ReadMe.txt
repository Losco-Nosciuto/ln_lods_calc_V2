Copyright 2020 - 2025 Chris "Losco Nosciuto" Da Ros

# LN LODs Addon for Blender (Free Edition — Version 2.9.0)

## What It Does

LN LODs automates Level-of-Detail setup for Microsoft Flight Simulator 2020 and 2024. If you make aircraft or scenery, this tool saves you hours of manual LOD tweaking.

**In a nutshell:** name your collections `_LOD00`, `_LOD01`, etc., click a button, and the addon calculates the correct screen-size thresholds for the Asobo Exporter — calibrated to match how MSFS actually counts vertices.

**This is the Free edition.** It includes the full calculation engine and the Asobo Exporter integration. The Pro edition adds the real-time **LOD Viewer / Testing Mode**, which previews LOD transitions inside Blender before you export.

Both editions share the same core: every calculation improvement, fix or speed gain lands in both at the same time.

## Quick Start

1. Name your collections: `MyModel_LOD00`, `MyModel_LOD01`, `MyModel_LOD02`...
2. Put your mesh objects into the right collections.
3. Open the **LN LODs** tab in the 3D Viewport sidebar.
4. Click **"Calculate LOD Sizes"** — results appear with a progress bar.
5. Click **"Set LOD Values in Asobo Exporter"** — done.

That's it. The exporter will use the correct thresholds and your LODs will transition smoothly in-sim.

## Features

- **One-click calculation** — Scans all your LOD collections and computes screen sizes using the official Asobo reference curve. A progress bar keeps you informed on large scenes.
- **Accuracy you can trust** — Counts vertices the same way the exporter does: accounts for UV seams, split normals, vertex colours, and tangents. What you see is what the sim gets.
- **MSFS Exporter integration** — Writes results directly into the Asobo Multi Exporter's LOD groups. No copy-pasting.
- **Screen Space Margin** — Adds a safety buffer (2-3% recommended) to prevent LOD flickering in-sim.
- **Smart collection handling** — Optionally skip hidden collections (and their children) so they don't interfere with your calculation.
- **Smart alerts** — Empty collections are clearly flagged; collections exceeding the sim's practical range are highlighted in red so you know to optimise further.
- **Clear Data** — One button to wipe all results and start over, no restart needed.
- **Exporter status check** — If the MSFS Exporter addon is missing or disabled, you'll see a clear warning in the panel.

---

## Usage Instructions

### MSFS Multi Exporter Setup

1. Enable the **MSFS Asobo Multi Exporter** addon.
2. In the exporter's Objects tab, turn on **"Grouped By Collections"**.

### LOD Naming

Ensure your LOD collections end with `_LOD00`, `_LOD01`, `_LOD02`, etc. or `_LOD0`, `_LOD1`, `_LOD2`, etc. Examples:
- `MyModel_LOD00`
- `MyModel_LOD01`
- `MyModel_LOD02`

Place all relevant mesh objects into the respective collections for each LOD.

### Calculating LOD Values

1. Go to the **LN LODs** tab in the Blender Sidebar.
2. Click **"Calculate LOD Sizes"** to compute screen sizes for each `_LODxx` collection.
3. Review the results: collection name, vertex count, and recommended screen size %.
4. Adjust the **Screen Space Margin (%)** to account for minor discrepancies between Blender's vertex calculations and the final GLTF/Asobo pipeline. We recommend at least 2-3%.
5. Click **"Set LOD Values in Asobo Exporter"**. The plugin sends the results to the Asobo Multi Exporter, rounding up decimals to the next integer.
6. Press **"Open README"** to open this file in your system's text viewer.

### Tips

- **Start with 2-3% margin.** This small buffer prevents the sim from constantly swapping LODs at transition boundaries. You can adjust per project.
- **Check the warning banners.** If the MSFS Exporter isn't detected, the panel will tell you what's wrong.
- **Simple objects need margin too.** If your LOD value rounds to 0 but the object is visible, the margin pushes it to 1 so it doesn't disappear.
- **Use named LOD patterns consistently.** `_LOD00`, `_LOD01`, `_LOD02` or `_LOD0`, `_LOD1`, `_LOD2` both work, but don't mix styles in the same project.
- **Want to test your LODs before exporting?** That's what the Pro edition's LOD Viewer is for: it simulates MSFS LOD loading in the viewport with the exact coverage formula.

---

**NOTE: THIS IS TO MINIMIZE LOD POPPING.**
Any LOD collection with a value above `00.00%` gets automatically translated to **1** when sent to the exporter **if any Screen Space Margin is specified**.
Otherwise, it will remain 0. If you want to set 0.5 (the minimum VSS defined by Asobo) you can set it manually afterwards.
Bear that in mind when building very simple objects!

---------------------

## Support

For issues or feedback, contact **Chris "Losco Nosciuto" Da Ros** on his [Discord server](https://discord.gg/ZGMmYe3MvN).

---

## Version History

### Free Changelog

**2.9.0** — Unified core with LN LODs Pro 4.0.3
- **New calculation engine**, shared with the Pro edition — every core improvement now lands in both editions.
- **Dramatically faster** on large scenes, with a progress bar during calculation.
- **Asobo-compliant interpolation** for smoother, more reliable LOD transitions.
- **1:1 vertex count fidelity** with the MSFS exporter — what you see is what the sim gets.
- **Cleaner Asobo exporter detection** with status banners in the panel.
- More accurate "Hide Hidden Collections": hidden collections and their children are correctly excluded.
- Overall reliability and UI polish.
- **Reminder:** the LOD Viewer / Testing Mode remains a Pro-only feature.

**2.8.1**
- Blender 4.2 LTS compatibility.
- Updated ARRAY values for VSS/Vert Count.
- Slightly reworked interpolation logic.

**2.7.5**
- This free version excludes the real-time LOD Viewer module.
- Basic calculations and auto-set LOD values remain the same.
- Fixed a bug with "Hide Hidden Collections" — hidden collections and children of hidden collections are now correctly excluded.

**2.7.0**
- **Expanded Data Array** — Greatly increased reference points for more accurate mapping from vertex counts to screen space.
- **New Interpolation Method** — Replaced linear interpolation with a smoother curve for more natural LOD transitions.
- **Dynamic Vertex Limits** — Removed the fixed 2M vertex limit.
- **Boundary Handling** — Minor cleanups and improved handling at extreme values.

**2.6.0**
- Added **"Hide Hidden Collections"** to exclude hidden collections from calculations.

**2.5.0**
- **Reworked Vertex Counting Algorithm** — Now accounts for splits from multiple UVs, split normals, vertex colors, tangents. Minimizes mismatch between Blender's internal count and the sim's final vertex count.

**2.2.0**
- **Modular Plugin Structure** — Split into multiple scripts. Enables backend expansion and easier bugfixing.

**2.0.0**
- Recognises both single-digit and double-digit LOD suffixes (`_LOD0`, `_LOD01`, etc.).
- Vertex counting logic now triangulates meshes, adding 2 verts for quads, `(n-3)` for ngons.

**1.8.0**
- Replaced fixed 2% margin checkbox with a dynamic float input.
- Enhanced error handling, debug messages, UI clarity.
- Red highlighting for out-of-range collections.
- LOD collections exceeding vertex limits are included in results but marked as out of range (displayed in red).

**1.6.0** (Initial Release)
- Basic LOD screen size calculation and direct integration with Asobo Multi Exporter.

---

**Happy blending!**
