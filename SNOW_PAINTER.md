# Snow Painter

A single-file Python tool for **Unreal Engine 5.6**: paint snow onto meshes with the mouse, and Geometry Script turns the paint into a real snow mesh. The snow is thick where you painted and has soft edges that dip under the surface. It only sits on faces flat enough to hold it.

## How it works
Unreal's Python can't capture mouse drags in the level viewport, so the brush is Unreal's own **Mesh Paint** mode. The tool does everything around it:

1. **Start painting:** the tool drapes an invisible *paint canvas* over each selected Static Mesh actor.
   - The canvas is a regular grid placed by casting rays straight down onto your mesh's full-detail surface. For Nanite meshes, that's the high-resolution source.
   - It floats just above the surface, a bit more where the surface is bumpy between grid points, and it never bridges cliffs.
   - It doesn't depend on how your mesh is triangulated. Your meshes are never modified.
2. **Paint:** in Mesh Paint mode, paint the canvas with the left mouse button; Shift erases. Painted areas glow light blue.
3. **Snow:** about half a second after you release the mouse, the snow is rebuilt into a Dynamic Mesh actor.
   - It's built on the real surface, with its own detail (5 cm by default) where you painted, so it stays fine even when a big mesh needs a coarser paint grid.
   - It thins out to nothing at cliff lips and mesh edges.
   - The sliders reshape it instantly, without re-reading the paint.
4. **Bake:** creates a Static Mesh asset in `/Game/SnowPainter/Baked` (Nanite optional, with collision) and an actor using it. The canvas and the preview are then removed.

## Requirements
- Unreal Engine 5.6 with these plugins enabled: **Python Editor Script Plugin**, **Geometry Script** and **Mesh Paint**. If **Mesh Paint** is missing from the mode dropdown, the plugin is off: *Edit → Plugins*, search "Mesh Paint", enable it and restart.
- PySide6 for the panel. It uses the same per-user install as World Performance Audit (offered on first run). Without it, use the Python functions below.

## Run it
- **Paste:** *Window → Output Log*, Python mode, paste the whole `snow_painter.py`, press Enter.
- **File:** *Tools → Execute Python Script…*.
- **Module:** copy it to `<Project>/Content/Python/` and run `import snow_painter; snow_painter.show()`.

## Workflow
1. Select the meshes (rocks, roofs, ledges…) and click **Start painting**.
2. Switch to **Mesh Paint** mode: open the mode dropdown at the top left of the editor (it reads *Selection Mode*, *Modeling Mode*…) and pick **Mesh Paint**. Not Modeling Mode: its Mesh tools are something else.
   - Pick **Colors** (*Vertex Color* in some versions), then the **Paint** tool.
   - Keep **Paint Color** white with the **Red** channel ticked, and paint with the left mouse button.
   - **Start painting** has already selected the canvas. If painting does nothing, select **SnowCanvas_<mesh>** in the Outliner (folder *SnowPainter*).
3. Shape the snow:

   | Slider | What it does |
   |---|---|
   | Depth | Thickness on flat ground, in cm |
   | Soft edges | Rounder edges (they also spread a little beyond the paint) |
   | Max slope | Faces steeper than this hold no snow |
   | Pile up | 0 = grow along the surface, 1 = pile up vertically |
   | Clumps / Clump size | Thickness variation |
   | Edge sink | How far the thin edge dips under the surface, to hide the seam |

4. Optionally pick your own snow material: type its path, or select it in the Content Browser and click **Use selected**. The built-in one is plain white. The snow gets top-down UVs (one tile per 2 m) and the paint amount in vertex color red, which a material can use for edge blending.
5. Use **Bake to Static Mesh**, then **Save**.
   - **Clear paint** starts over.
   - **Cancel** removes everything the tool added.
   - If you close and reopen the tool, it picks the session back up from the canvases still in the level.

## Python functions
```python
import snow_painter as sp
sp.start()                        # canvases for the selected actors
sp.set_params(depth=20, clumps=0.5)
sp.update()                       # rebuild now
sp.bake(nanite=True)              # Static Mesh assets + actors, session ends
sp.clear_paint(); sp.cancel()
```
Defaults are in `CONFIG` at the top of the script, for example `canvas_detail`, `snow_detail`, `canvas_max_points`, `poll_seconds`, `asset_folder` and `snow_material`.

## What it writes
- **Assets in `/Game/SnowPainter`:**
  - `Materials/`: the canvas and default snow materials.
  - `Canvas/`: temporary; deleted on Bake, Clear and Cancel.
  - `Baked/`: your snow meshes.
- **Actors in the level, in the `SnowPainter` outliner folder:** the canvases (hidden in game) and the live snow.
- Nothing is saved until you save.

## Limitations
- **Snow falls from above:** only what's visible from straight above can be painted, so not walls, undersides or the inside of overhangs.
- **Paint precision:** the paint grid is 10 cm by default. On big meshes it's coarsened automatically to stay under 90k points, and the panel shows the spacing; the snow keeps its own detail.
- **Start painting on a big mesh:** casts one or two rays per grid point (a few seconds on a large scan, with a progress bar).
- **Speed:** the snow is built in Python, so a rebuild on a big canvas takes a few tenths of a second. It runs between strokes, never during one.
- **Static Mesh actors only:** no skeletal meshes, and no instanced foliage or landscape.
- **Testing:** the tests run the whole tool against a fake of the Unreal API, so do one pass in the editor first. The calls most likely to differ between engine versions are the Geometry Script copy options and the vertex color read-back. If one fails, the Output Log says which.

## Changes
- **1.1.0:** the paint canvas is now a grid draped over the mesh by casting rays straight down onto its full-detail surface.
  - **What was wrong:** 1.0 built the canvas from a simplified copy of the mesh. On big or dense scans it ended up mostly buried inside the mesh, leaving scattered fragments.
  - **Snow:** now built on the real surface with its own detail, and it tapers off at cliff lips and mesh edges.
  - **Canvas material:** set on the actor as well, so the canvas can't fall back to the default gray material.
- **1.0.1:** fixed an editor crash on **Start painting** (`Assertion failed: NumUVs > 0`). The paint canvas mesh had no UV channel, which Unreal requires to build a Static Mesh. Every mesh the tool creates now gets top-down UVs, and asset creation is refused, with a message instead of a crash, if a mesh somehow has none.
- **1.0.0:** first version.
