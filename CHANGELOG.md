# Changelog

## 1.1.0

### Before/after proof
- **Profile comparison:** every Profile GPU on the same level is compared with the previous one. A row pinned at the top shows the frame, GPU, game- and render-thread times and the GPU passes that changed most, and lists the fixes applied in between.
- **Take back what didn't help:** fixes whose GPU pass got no faster are listed on that row, and its **Revert** button undoes just those. Fixes made before a re-scan are still found, because the list comes from the fix journal.
- **Before/after screenshots:** tick **Before/after shots** and every batch of fixes that might change the look is wrapped in two viewport screenshots (`Saved/PerfAudit/Shots`). Select the fixed row to see thumbnails; **Before / After** opens a wipe view, single images, and a 4x difference image with the share of pixels that changed.
- GPU findings show the change since the previous profile next to each measurement.

### Game thread / render thread
- Profile GPU reads the CSV profiler's `Exclusive/GameThread/*` and `Exclusive/RenderThread/*` stats. The biggest items (animation, physics, visibility, shadow setup, draw submission, FX...) become findings, each with a Fix that applies the related scan fixes. Wait/idle stats are skipped.
- When the render thread is busy, a "what drives it" finding lists this level's primitive, instance, non-Nanite, movable, shadow-caster and scene-capture counts, with the fixes that reduce them.

### Sequencer
- **Profile Sequence:** profiles the Level Sequence open in Sequencer shot by shot (cinematic shots, else camera cuts, else equal parts). It locks the camera cut to the viewport, profiles the middle frame of each shot and adds one finding per shot under *Sequencer Shots (measured)*, linked to the fixes for that shot's most expensive passes. It then parks on the worst shot and scans there. **Stop** cancels it and puts the playhead, camera lock and profiler settings back. **Go To** on a shot jumps Sequencer to it.
- **Spawnable templates:** the open sequence's spawnable templates, including those in its shots, are scanned. Fixes on light, WPO, overlap, capture, decal and animation settings are applied to the template inside the sequence asset, so they stick on the next spawn.

### Quality-level-aware console variables
- The volumetric fog and translucency console-variable fixes are now written to `Config/DefaultScalability.ini`, only for the quality levels in `CONFIG["scalability_fix_levels"]` (default Low/Medium/High). Epic and Cinematic stay untouched.
- Levels that are already cheap enough, or where the feature is off (e.g. volumetric fog at Low), are skipped. The change is applied live only when the editor runs at one of those levels.
- Revert restores the old per-level values. Fixes made by 1.0.0 (`DefaultEngine.ini [SystemSettings]`) can still be reverted.

### New checks (48 in total)
- **WPO re-renders shadow pages every frame:** with Virtual Shadow Maps on, WPO shadow casters invalidate their cached pages every frame. Fix: *Shadow Cache Invalidation Behavior = Rigid*.
- **Nanite on the programmable raster path:** Nanite meshes with masked or WPO materials. Advice only.
- **Textures far exceed the streaming pool:** the level's textures at full resolution vs. `r.Streaming.PoolSize`. Fix applies the related texture fixes (oversized, Never Stream).
- **Dense foliage traced by Lumen:** instanced foliage with *Affect Distance Field Lighting* on while Lumen GI is used. Fix turns it off on the components and their project Foliage Types.
- **High distance-field resolution:** meshes with *Distance Field Resolution Scale* above 2. Fix sets it to 1 (rebuild, revertable).
- **No Effect Type** now has a Fix: it creates (once) `/Game/PerfAudit/ET_PerfAudit_DistanceCull` and assigns it. The Effect Type culls at 150 m, re-checks distance continuously, and culled FX resume when you come closer. Revert unassigns it; the asset stays.
- **MegaLights hint** on the direct-lighting finding when the level has many shadowed lights.

### Fixes and hardening
- Profiling runs as a cancellable job. A stopped or failed capture stops the CSV profiler and restores `r.GPUCsvStatsEnabled`. Closing the window stops a running job.
- Console allowlist: added `csvprofile stop` and `HighResShot <w>x<h>` only.
- Ini writes: only `DefaultEngine.ini` and `DefaultScalability.ini`. Journal entries for quality levels and distance-field scale are validated (section names, console variable, numbers).
- A journal with malformed entries no longer breaks the Revert menu.
- Scan, Fix and Revert wait while a capture or screenshot job runs, so measurements and row states stay consistent.

## 1.0.0 – first production release

### Features
- **Scene scan:** 43 checks over every loaded actor and the assets they use. Covered: lighting & shadows, Nanite/LODs, WPO, culling, textures, shader cost, Niagara, post-process overrides, scene captures, animation, motion vectors / TSR ghosting, and project velocity settings. Results are ranked by an estimated cost score (0–100).
- **Profile GPU:** captures frames with Unreal's CSV profiler (per-pass GPU stats on) and reports:
  - whether the frame is GPU-, game-thread- or render-thread-bound;
  - every expensive pass (shadows, Lumen, translucency, base pass, fog, post…), linked to the related scan findings;
  - draw-call and triangle counts.
- **Fix buttons on every row, applied without popups.**
  - **Fix Selected**, **Fix Safe** (only fixes with no visual change) and **Fix All Shown** for batches.
  - GPU findings apply all their related fixes at once, plus console-variable tweaks for fog and translucency.
- **Fix safety:**
  - Every fix is labelled *Safe*, *Visual* (amber ⚠) or *Behaviour* (purple ⚠), with a tooltip saying exactly what changes.
  - Old values are journaled to `Saved/PerfAudit/fix_journal.json`, so **Revert** works even after saving or restarting.
  - **Undo fixes made by the previous version** rebuilds old values from `Saved/Logs`.
- **Never touches materials automatically:** "Output Depth and Velocity" breaks soft particles that use DepthFade.
- **FX textures are protected:** textures used by Niagara materials get no automatic mip / compression / power-of-two changes.
- **Scan scope report:** Level Instance contents, child actors and spawned Sequencer spawnables are scanned for their assets. Every sublevel that is *not* loaded is listed by name.
- **UI:** PySide6/PyQt6 (PySide2/PyQt5 also work), with a header, KPI cards, category sidebar, sortable table with severity/impact badges and cost bars, detail panel, and HTML/CSV export.
- **Single file, paste-safe:** paste it into the Output Log (Python mode), run it as a script file, or import it as a module. A text mode works without Qt.

### Fixed during release review
- **Profile GPU:**
  - It waits for the capture to be finalised (stable size plus the closing metadata row), so it never reads a half-written CSV.
  - The timeout always fires, polling runs 4×/s instead of every frame, and a failing callback can't leave it stuck.
  - It reads the complete header that Unreal writes at the end of the CSV.
  - A profile measured on another level is dropped instead of being re-attached to a new scan.
  - Console-variable fixes shared by several passes are recorded once.
- **Fixes and reverts:**
  - Reverting several GPU findings that share a fix reverts it once.
  - Revert ALL also resets GPU console-variable fixes.
  - Group statuses stay correct in text mode too.
  - Go To works on several selected GPU findings.
- **Scan scope:**
  - Actor-level fixes are no longer offered on actors that aren't editable placed actors (spawnables, child actors, Level Instance contents).
  - Duplicate-actor detection is limited to visible actors in the same level and is labelled *Behaviour*.

### Security hardening
- **Fix journal:** replayed through allowlists only (properties, setters, enums, console variables, ini keys), with validated values, on project content only. A tampered `fix_journal.json` can no longer call arbitrary methods, run console commands or write files.
- **Console commands:** restricted to `r.<name> <number>` and `csvprofile frames=<n>`.
- **Ini writes:**
  - Validated: `DefaultEngine.ini` only, no path traversal, no newline or section injection.
  - Parsed with the same line breaks as Unreal, and decoded strictly.
  - A read-only file is refused instead of being made writable.
- **Restoring the old version's fixes:** only reads the old version's own `LogPython` lines, skips ambiguous asset names, and only removes auto-generated LOD counts.
- **pip:** version range pinned, prebuilt wheels only, PyPI only, pip env/config ignored. The install folder is added without running `.pth` files.
- **Output escaping:**
  - CSV export neutralises spreadsheet formulas.
  - Asset and actor names are shown as plain text in Qt labels and tooltips.
  - The Revert ALL dialog lists the actual changes.
- **Foliage types:** engine and plugin foliage types are never modified.
- **Download check:** the README one-liner verifies the file's SHA-256.

