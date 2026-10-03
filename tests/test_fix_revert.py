"""Scan the demo level, apply every fix, revert everything, restore old-version fixes from logs, UI smoke test."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)

# ------------------------------------------------------------------ run
import json
import world_perf_audit as W  # noqa: E402

def snapshot():
    """Every property value of every mock object (to compare after revert)."""
    snap = {}
    for o in U._ALL:
        for k, v in o._p.items():
            if isinstance(v, (bool, int, float, str, U._EnumVal)) or v is None:
                snap[(o.get_path_name(), k)] = v
            elif isinstance(v, U._Struct):
                for kk, vv in v._p.items():
                    if isinstance(vv, (bool, int, float, str, U._EnumVal)):
                        snap[(o.get_path_name(), k, kk)] = vv
        for attr in ("lods", "overlap"):
            if hasattr(o, attr):
                snap[(o.get_path_name(), attr)] = getattr(o, attr)
    return snap

ini_path = os.path.join(U._TMP, "Config", "DefaultEngine.ini")
ini_before = open(ini_path).read()
before = snapshot()

issues = W.scan()
assert not W._STATE["errors"], W._STATE["errors"]
print("=== %d issues ===" % len(issues))
fs = [i for i in issues if i.check == "material_particle_forward_shading"]
assert fs and fs[0].fix is None, "forward shading must be advice-only now"
for i in issues:
    if i.fix:
        assert i.impact in (W.SAFE, W.LOOK, W.GAMEPLAY), i.title
        assert i.impact == W.SAFE or i.impact_note, ("missing impact note", i.title)
safe = [i for i in issues if i.fix and i.impact == W.SAFE]
print("safe fixes:", [(i.title, i.obj) for i in safe])

# default fix_all = SAFE only
f, x = W.fix_all()
assert f == len(safe) and x == 0, (f, x)
assert all(i.status != "fixed" for i in issues if i.fix and i.impact != W.SAFE)
# then the visual ones explicitly
f2, x2 = W.fix_all(include_visual=True)
print("visual/behaviour fixes applied:", f2, "failed:", x2)
assert x2 == 0
assert M_snow.get_editor_property("output_translucent_velocity") is False, "tool must never enable Output Velocity"
assert all(i.fix is None for i in issues if i.check == "mv_translucent_velocity")
assert not [n for (o, n, v) in U.SET_CALLS if n == "output_translucent_velocity"]
assert M_snow.get_editor_property("translucency_lighting_mode") == U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING
assert SM_statue.get_editor_property("nanite_settings").enabled and SM_glass.lods == 4
assert ppv.get_editor_property("settings").override_lumen_final_gather_quality is False
journal = json.load(open(W._journal_path()))
print("journal entries:", len(journal))
assert len(journal) == f + f2

# ---- revert one, then everything
light_issue = [i for i in issues if i.check == "light_radius"][0]
W.revert(light_issue.id)
assert big.get_editor_property("attenuation_radius") == 16000.0 and light_issue.status == "reverted"
n, errs = W.revert_all()
print("revert_all:", n, "errors:", errs)
after = snapshot()
diff = {k: (before.get(k), after.get(k)) for k in set(before) | set(after)
        if before.get(k) != after.get(k) and not (k[0].startswith("/Game/Mock/Crate_Dup_B"))}
for k, v in sorted(diff.items(), key=str):
    print("  DIFF", k, v)
expected_diff_ok = {k for k in diff if "nanite_settings" in k or k == ("/Game/Mock/SK_Crowd.SK_Crowd", "lods")  # skeletal LODs: Ctrl+Z only (by design)
                    or k[0].startswith("/Game/PerfAudit/ET_PerfAudit_DistanceCull.")}   # the created Effect Type stays
assert SM_statue.get_editor_property("nanite_settings").enabled is False
assert not [k for k in diff if k not in expected_diff_ok], "values not restored"
assert open(ini_path).read() == ini_before, "ini not restored"
assert not W.journal_entries(), "revertable entries left"
print("REVERT OK - every value back to the original")

# ---- recovery of fixes made by the OLD version (no journal) from the editor log
os.makedirs(os.path.join(U._TMP, "Saved", "Logs"), exist_ok=True)
M_snow._p["translucency_lighting_mode"] = U.TranslucencyLightingMode.TLM_VOLUMETRIC_PER_VERTEX_DIRECTIONAL
M_snow._p["output_translucent_velocity"] = True
spr = [o for o in U._ALL if isinstance(o, U.NiagaraSpriteRendererProperties)][0]
spr._p["motion_vector_setting"] = U.NiagaraRendererMotionVectorSetting.AUTO_DETECT
T_nm._p["mip_gen_settings"] = U.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP
T8K._p["max_texture_size"] = 4096
s2 = ppv.get_editor_property("settings"); s2._p["override_bloom_method"] = False
with open(os.path.join(U._TMP, "Saved", "Logs", "MyProject.log"), "w") as fh:
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #4 Particles use 'Surface ForwardShading' (M_Snow): Lighting Mode -> Volumetric PerVertex Directional\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #5 Translucent material doesn't output velocity (M_Snow): Output Velocity enabled on M_Snow\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #6 Particles write no motion vectors (NS_Snow / Snowflakes / SpriteRenderer): Motion Vector Setting -> Auto Detect\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #7 Texture has no mipmaps (T_NoMips): mip_gen_settings=TMGS_FROM_TEXTURE_GROUP\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #8 8K texture (T_Cliff_8K): max_texture_size=4096\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #9 Convolution (FFT) bloom (GlobalPPV): Override removed (back to project default)\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #10 Shadow-casting light with huge radius (Lights > BigPointLight): Attenuation radius -> 2500\n")
plan = W.recover_previous_fixes()
for p in plan:
    print("  PLAN", p[0], "|", p[2], "|", "auto" if p[3] else "manual")
done, errs = W.recover_previous_fixes(apply=True)
print("recovered", done, errs)
assert M_snow.get_editor_property("translucency_lighting_mode") == U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING
assert M_snow.get_editor_property("output_translucent_velocity") is False
assert spr.get_editor_property("motion_vector_setting") == U.NiagaraRendererMotionVectorSetting.DISABLE
assert T_nm.get_editor_property("mip_gen_settings") == U.TextureMipGenSettings.TMGS_NO_MIPMAPS
assert T8K.get_editor_property("max_texture_size") == 0
assert ppv.get_editor_property("settings").override_bloom_method is True
assert W.recover_previous_fixes()[0][3] is None or all(p[3] is None for p in W.recover_previous_fixes()), "should be idempotent"
print("RECOVERY OK")

# ------------------------------------------------------------------ UI screenshot
Issue = W.Issue
Issue._counter = 0
issues = W.scan()
W.apply_fixes([i for i in issues if i.check in ("light_radius", "tex_never_stream", "pp_expensive_settings")][:3])
from PySide6 import QtWidgets  # noqa: E402
win = W.show()
win.issues = issues
win._populate()
win.lbl_level.setText("PL_Vignette_Site19_primary_default")
win.lbl_scanned.setText("scanned 14:32:10")
win._refresh_all()
target = [i for i in issues if i.check == "mv_translucent_velocity"][0]
win._rows[target.id][0].setSelected(True)
QtWidgets.QApplication.processEvents()
win.resize(1560, 900)
QtWidgets.QApplication.processEvents()
win.grab().save(os.path.join(OUT, "ui2.png"))
# exercise filters + menus
win.cmb_fix.setCurrentIndex(2); win.txt_filter.setText("tex"); win._fill_revert_menu()
win.cmb_fix.setCurrentIndex(0); win.txt_filter.setText("")
print("UI OK")
# FX textures: no mip / compression / power-of-two auto-fix when a Niagara material samples them
fx_tex = U.Texture2D("T_SnowFlipbook", mip_gen_settings=U.TextureMipGenSettings.TMGS_NO_MIPMAPS); fx_tex.w, fx_tex.h = 1000, 1000
M_snow.textures = (fx_tex,)
W.Issue._counter = 0
iss = W.scan()
fx_issues = [i for i in iss if i.obj == "T_SnowFlipbook"]
print("FX texture issues:", [(i.title, "manual" if i.fix is None else "FIX") for i in fx_issues])
assert fx_issues and all(i.fix is None for i in fx_issues if i.check in ("tex_no_mips", "tex_npot", "tex_uncompressed"))
print("FX PROTECTION OK")
