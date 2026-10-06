# Snow Painter

A single-file Python tool for **Unreal Engine 5.6**: paint snow onto meshes with the mouse, and Geometry Script turns the paint into a real snow mesh. The snow is thick where you painted and has soft edges that dip under the surface. It only sits on faces flat enough to hold it.

## How it works
Unreal's Python can't capture mouse drags in the level viewport, so the brush is Unreal's own **Mesh Paint** mode. The tool does everything around it:

1. **Start painting:** for each selected Static Mesh actor, the tool builds an invisible *paint canvas*.
   - The canvas is a copy of the faces that can hold snow, refined to an even 8 cm grid and floating 0.4 cm above the surface.
   - Your meshes are never modified.
   - Paint precision doesn't depend on how many vertices your mesh has, and Nanite meshes work too: their full-detail source is used, simplified first if it's very dense.
2. **Paint:** in Mesh Paint mode, paint the canvas with the left mouse button; Shift erases. Painted areas glow light blue.
3. **Snow:** about half a second after you release the mouse, the snow is rebuilt from the paint into a Dynamic Mesh actor.
   - The sliders reshape it instantly, without re-reading the paint.
4. **Bake:** creates a Static Mesh asset in `/Game/SnowPainter/Baked` (Nanite optional, with collision) and an actor using it. The canvas and the preview are then removed.

## Requirements
- Unreal Engine 5.6 with these plugins enabled: **Python Editor Script Plugin**, **Geometry Script** and **Mesh Paint** (on by default).
- PySide6 for the panel. It uses the same per-user install as World Performance Audit (offered on first run). Without it, use the Python functions below.

## Run it
- **Paste:** *Window → Output Log*, Python mode, paste the whole `snow_painter.py`, press Enter.
- **File:** *Tools → Execute Python Script…*.
- **Module:** copy it to `<Project>/Content/Python/` and run `import snow_painter; snow_painter.show()`.

## Workflow
1. Select the meshes (rocks, roofs, ledges…) and click **Start painting**.
2. Switch to **Mesh Paint** mode: the mode dropdown in the toolbar, or Shift+4. Pick **Colors → Paint** and paint with the default white. The canvas is already selected.
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
Defaults are in `CONFIG` at the top of the script, for example `canvas_detail`, `canvas_max_tris`, `poll_seconds`, `asset_folder` and `snow_material`.

## What it writes
- **Assets in `/Game/SnowPainter`:**
  - `Materials/`: the canvas and default snow materials.
  - `Canvas/`: temporary; deleted on Bake, Clear and Cancel.
  - `Baked/`: your snow meshes.
- **Actors in the level, in the `SnowPainter` outliner folder:** the canvases (hidden in game) and the live snow.
- Nothing is saved until you save.

## Limitations
- **Faces that can hold snow:** the canvas covers faces up to 80° from vertical, so you can't paint walls or undersides. Snow wouldn't stay there anyway.
- **Paint precision:** set by **Canvas detail**. Very large meshes are coarsened automatically to stay under 120k canvas triangles per mesh.
- **Speed:** the snow is built in Python, so a rebuild on a big canvas takes a few tenths of a second. It runs between strokes, never during one.
- **Static Mesh actors only:** no skeletal meshes, and no instanced foliage or landscape.
- **Testing:** the tests run the whole tool against a fake of the Unreal API, so do one pass in the editor first. The calls most likely to differ between engine versions are the Geometry Script copy options and the vertex color read-back. If one fails, the Output Log says which.
