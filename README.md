# World Performance Audit

A single-file Python tool for **Unreal Engine 5.6**. It scans the open level for setups that cost performance, measures the real frame with Unreal's GPU profiler, and gives you a **Fix** button on each finding. Every fix can be reverted.

![World Performance Audit](docs/screenshot.png)

- **Scan Level:** 43 checks covering lighting & shadows, Nanite/LODs, WPO, culling, textures, shader cost, Niagara, post process, scene captures, animation, and motion vectors / TSR ghosting. Findings are ranked by an estimated cost score.
- **Profile GPU:** records 120 frames with the CSV profiler. It tells you whether you're GPU-, game-thread- or render-thread-bound, lists the expensive passes, and links each one to the scan findings that reduce it.
- **Fix / Fix Selected / Fix Safe / Fix All Shown:** no popups. A ⚠ next to Fix means *this might change the look* (amber) or *behaviour* (purple).
- **Revert:** every fix records the old values in `Saved/PerfAudit/fix_journal.json`, so you can revert one fix or all of them at any time, even after saving or restarting.

## Requirements
- Unreal Engine 5.6, with the **Python Editor Script Plugin** and **Editor Scripting Utilities** plugins enabled.
- Qt for Python for the UI. On first launch the tool offers to install **PySide6-Essentials** into a per-user folder outside your project: `%LOCALAPPDATA%\UnrealWorldPerfAudit\py311\site-packages`. That needs internet access. PyQt6, PySide2 and PyQt5 also work if one is already installed. Without Qt the tool runs in text mode (Output Log + HTML report).

## Run it
**A. Paste:** open *Window → Output Log*, set the dropdown next to the input box to **Python** (not *Cmd*, not *Python (REPL)*), paste the whole `world_perf_audit.py` and press Enter.

**B. One line:** paste this into the Output Log in Python mode. It downloads the v1.0.0 release, **checks its SHA-256** and only then runs it:
```python
import urllib.request as u, hashlib as h; s = u.urlopen("https://raw.githubusercontent.com/PhiLLAnt89/PhiLL/v1.0.0/world_perf_audit." + "py").read(); assert h.sha256(s).hexdigest() == "99acfa40d398795b72ec2a6e4b1d1d86a20ef5746e52d3ebf35731993221d80c", "checksum mismatch - not running it"; exec(s.decode("utf-8"), {"__name__": "__main__"})
```
**C. File:** *Tools → Execute Python Script…* and pick `world_perf_audit.py`.

**D. Module:** copy the file to `<Project>/Content/Python/` and run `import world_perf_audit; world_perf_audit.show()`.

## Workflow
1. **Scan Level.** Pick a category on the left and select a row to read the problem, the solution and exactly what the fix changes.
2. **Profile GPU** with the viewport visible and Realtime on (Ctrl+R). For final numbers, profile in PIE or a Standalone game; editor numbers include editor overhead.
3. Click **Fix** on single rows, or select rows and use **Fix Selected**. **Fix Safe** applies only fixes with no visual change; **Fix All Shown** applies the whole filtered list.
4. Check the viewport. Use **Revert** on anything you don't like (row button, *Revert ▾*, or *Revert ALL*).
5. **Save…** (Unreal's own Save Content dialog). Nothing is saved before this.

## Fix safety
| Label | Meaning |
|---|---|
| **Safe** | No visual change (e.g. a texture streams instead of always being resident) |
| **Visual** ⚠ | Changes the look (light radius, cull distances, Nanite/LOD rebuilds, post-process overrides…) |
| **Behaviour** ⚠ | Can change gameplay/runtime behaviour (mobility, overlap events, scene captures, animation ticking, deleting duplicate actors) |

- **Revertable:** every fix journals its old values, including asset rebuilds (Nanite on/off, generated LODs), `DefaultEngine.ini` edits and console variables. Deleted duplicate actors and generated *skeletal* LODs can only be undone with Ctrl+Z or source control; the tool says so on those rows.
- **Never touched automatically:** materials. Turning on *Output Depth and Velocity* breaks soft particles that use DepthFade. Lit particle lighting modes are also left alone.
- **Protected FX textures:** textures used by particle materials get no automatic mip / compression / power-of-two changes, which would break flipbooks and atlases.
- **Shared assets:** asset fixes change the asset for every level that uses it.
- **Fixes made by the first release:** *Revert ▾ → Undo fixes made by the previous version* rebuilds the old values from `Saved/Logs`.

## What gets scanned
The persistent level and **every loaded sublevel** (visible or hidden). That includes Level Instance contents, child actors and currently spawned Sequencer spawnables; these last three are scanned for their assets, but actor-level fixes aren't offered on them because the change wouldn't stick.

**Not scanned:** unloaded sublevels (the header lists them), unloaded World Partition regions, and actors spawned only at runtime.

## Configuration
Thresholds are in the `CONFIG` dict at the top of the script. Examples: `target_fps` (the frame budget used for GPU findings), `max_light_radius`, `high_poly_tris`, `texture_warn_size`, `profile_frames`, `wpo_disable_distance`.

## Text mode / scripting
```python
import world_perf_audit as w
w.scan(); w.print_report()            # report in the Output Log
w.fix(12); w.revert(12)               # one issue by id
w.fix_all()                           # Safe fixes only; fix_all(include_visual=True) for everything
w.revert_all()                        # everything in the journal, also from earlier sessions
w.profile_gpu(on_done=lambda issues, err: w.print_report())
w.export_report()                     # HTML (or a .csv path)
```

## Security
- **The one-liner** checks the downloaded file's SHA-256 against the value published with the release. Never run a version from a link whose hash you can't verify: GitHub serves fork commits under the original repo's URL.
- **pip install:**
  - **What gets installed:** `PySide6-Essentials>=6.5,<7`, prebuilt wheels only (`--only-binary=:all:`, so no build scripts run), straight from PyPI.
  - **pip settings are ignored:** `--isolated` means `PIP_*` environment variables and pip config files can't redirect the index.
  - **Where it goes:** a per-user folder outside the project, added to `sys.path` without running `.pth` files. Delete the folder to uninstall.
- **What the tool writes:**
  - `Config/DefaultEngine.ini`: only three console variables and one renderer key, all validated, and never if the file is read-only. Check it out of source control first.
  - `Saved/PerfAudit/` (journal, reports).
  - Assets and levels: only through Fix, only in `/Game` and the project's own plugins, and nothing is saved until you click Save.
- **The journal is untrusted on revert.** Only known properties, setters, enums, console variables and ini keys, with validated values, on project content, are replayed. Console commands are limited to `r.<name> <number>` and `csvprofile frames=<n>`.
- **Restoring the old version's fixes** only reads the old version's own `LogPython: [PerfAudit] Fixed` lines. It skips asset names that match more than one asset, and never removes LODs it didn't generate.
- **Exports and UI text:** HTML reports and Qt text escape asset and actor names, and CSV exports neutralise spreadsheet formulas.

## Tests
The tests run the whole tool, UI included (rendered offscreen), against `tests/mock/unreal.py`, a small fake of the Unreal Python API:
```
pip install PySide6-Essentials pyflakes
python tests/run_all.py
```
CI runs the same on every push (`.github/workflows/tests.yml`). The mock checks the tool's logic, not Unreal itself, so do a manual pass in the editor before each release (see [RELEASE.md](RELEASE.md)).

## Known limitations
- Written against the UE 5.6 Python API. A few calls differ between engine versions; a check that fails is skipped and reported in the Output Log, and the scan continues.
- GPU pass names come from Unreal's CSV stats. A pass the tool doesn't recognise is listed under its raw name, with a pointer to `ProfileGPU`.
- The cost score is a heuristic for ranking, not a measurement. Use **Profile GPU** for real numbers.

See [CHANGELOG.md](CHANGELOG.md).
