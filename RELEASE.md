# Release checklist

## 1. Automated
- [ ] `python tests/run_all.py` passes locally and in CI. This covers lint, the paste-safety rules (ASCII-only, no file extension text), and the mock-engine tests.
- [ ] `__version__` in `world_perf_audit.py` and the top entry of `CHANGELOG.md` match.

## 2. Manual pass in Unreal 5.6
The tests use a fake engine. Before tagging, run this once in a real project, on a copy or with source control:
- [ ] Paste the script into the Output Log (Python mode). The window opens, and its title shows the new version.
- [ ] **Scan Level** on a level with sublevels. The header shows the loaded and unloaded sublevel counts, and no check errors are reported in the stats line or the Output Log.
- [ ] **Profile GPU** with the viewport in Realtime. The findings list your real pass names, and the status bar returns to normal.
- [ ] Apply one fix of each kind: a light, a texture, a Nanite enable, a post-process override, and the translucency console variable. Check the viewport, then **Revert** each one and confirm the old values are back.
- [ ] Translucency console-variable fix: `Config/DefaultScalability.ini` gets `[EffectsQuality@0..2]` entries and nothing for Epic/Cinematic; Revert removes them.
- [ ] **Profile GPU** twice with a fix in between. The pinned *Since the last profile* row appears and its numbers match `stat unit`.
- [ ] Tick **Before/after shots**, fix a light, then open **Before / After**. Both screenshots show the level viewport.
- [ ] Open a Level Sequence with shots and run **Profile Sequence**. Each shot is profiled, Sequencer ends on the worst shot, and **Stop** halfway restores the playhead.
- [ ] Fix a light on a spawnable and save the sequence. Re-open the level and play: the spawned light keeps the fix.
- [ ] **No Effect Type** fix: `/Game/PerfAudit/ET_PerfAudit_DistanceCull` is created and the FX still play near the camera.
- [ ] Revert one fix after **Save → restart the editor → re-run the tool → Revert ▾ → Revert ALL**.
- [ ] **Export…** an HTML report and open it.

## 3. Publish
- [ ] Merge to the default branch.
- [ ] Tag it with the version from `__version__`, e.g. `git tag -a v1.1.0 -m "World Performance Audit 1.1.0" && git push origin v1.1.0`.
- [ ] Create a GitHub release from the tag. Attach `world_perf_audit.py` and paste the CHANGELOG entry. Publish the file's SHA-256 so people can verify their download:
  `python -c "import hashlib;print(hashlib.sha256(open('world_perf_audit.py','rb').read()).hexdigest())"`
- [ ] Update the one-liner in the README: the new tag in the URL and the new SHA-256. Run the one-liner once to confirm the hash matches.
