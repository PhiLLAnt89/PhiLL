# Changelog

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

