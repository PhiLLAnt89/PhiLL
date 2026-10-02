"""Security regression tests: tampered journal, console/ini injection, forged log lines, CSV formulas, pip flags."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
import world_perf_audit as W

INI = os.path.join(U._TMP, "Config", "DefaultEngine.ini")


def revert_entry(changes):
    entry = {"id": "x%d" % len(changes), "time": "9999", "title": "t", "obj": "o", "changes": changes, "reverted": False}
    return W._revert_changes(entry["changes"])


# --- 1. tampered journal: nothing outside the allowlists is replayed ------------------------------------
calls = []
U.PythonScriptLibrary = type("PythonScriptLibrary", (U.Object,), {
    "execute_python_command": lambda self, c: calls.append(c)})
evil_obj = U.PythonScriptLibrary("Default__PythonScriptLibrary", path="/Script/PythonScriptPlugin")
before_cmds = list(U.SystemLibrary.commands)
ini_before = open(INI).read()
errs = revert_entry([
    {"k": "call", "path": evil_obj.get_path_name(), "setter": "execute_python_command",
     "old": [{"t": "py", "v": "import os"}]},
    {"k": "call", "path": big.get_path_name(), "setter": "destroy_component", "old": []},
    {"k": "cvar", "name": "py", "old": "import os"},
    {"k": "cvar", "name": "r.VolumetricFog.GridPixelSize", "old": "8 | quit"},
    {"k": "ini", "file": "../Content/Python/init_unreal", "section": "0", "key": "import os", "old": "1"},
    {"k": "ini", "section": "/Script/Engine.RendererSettings", "key": "r.Velocity.EnableVertexDeformation",
     "old": "1\n[Evil]\nx=1"},
    {"k": "prop", "path": big.get_path_name(), "prop": "attenuation_radius", "old": {"t": "py", "v": "1e9; rm"}},
    {"k": "prop", "path": big.get_path_name(), "prop": "some_other_prop", "old": {"t": "py", "v": 1}},
    {"k": "prop", "path": big.get_path_name(), "prop": "mobility", "old": {"t": "enum", "e": "SystemLibrary", "v": "X"}},
    {"k": "struct", "path": ppv.get_path_name(), "prop": "settings", "field": "weighted_blendables", "old": {"t": "py", "v": None}},
    {"k": "prop", "path": evil_obj.get_path_name(), "prop": "attenuation_radius", "old": {"t": "py", "v": 1.0}},
    "not a dict",
])
assert not calls, "journal must never call arbitrary methods"
assert U.SystemLibrary.commands == before_cmds, "journal must never run unexpected console commands"
assert open(INI).read() == ini_before, "journal must never write unexpected ini content"
assert not os.path.exists(os.path.join(U._TMP, "Content")), "no path traversal"
assert big.get_editor_property("attenuation_radius") == 16000.0
assert len(errs) == 12, (len(errs), errs)
print("journal allowlists: OK (%d rejected)" % len(errs))

# --- 2. console / ini input validation ----------------------------------------------------------------------
for bad in ("r.X 1 | quit", "py import os", "r.X 1;exit", 'r.X "a b"', "csvprofile frames=10\nquit"):
    try:
        W._run_console(bad)
        raise AssertionError("accepted: %r" % bad)
    except RuntimeError:
        pass
W._run_console("r.VolumetricFog.GridPixelSize 16")
for section, key, value, name in (("SystemSettings", "a\nb", "1", "DefaultEngine.ini"),
                                  ("SystemSettings", "r.X", "1\n[Evil]", "DefaultEngine.ini"),
                                  ("SystemSettings", "r.X", "1", "../../evil.ini"),
                                  ("Sys]\n[Evil", "r.X", "1", "DefaultEngine.ini")):
    try:
        W._set_project_ini(section, key, value, name)
        raise AssertionError("accepted ini write %r %r %r %r" % (section, key, value, name))
    except RuntimeError:
        pass
# a vertical tab inside a committed line is one line for Unreal: the rewrite must keep it one line
with open(INI, "a") as fh:
    fh.write("[/Script/Engine.Hidden]\nComment=a\x0b[Injected]\x0bKey=1\n")
W._set_project_ini("SystemSettings", "r.VolumetricFog.GridSizeZ", "64")
assert "\n[Injected]" not in open(INI).read(), "rewrite must not turn \\x0b into new lines"
os.chmod(INI, 0o444)
try:
    W._set_project_ini("SystemSettings", "r.VolumetricFog.GridSizeZ", "32")
    raise AssertionError("wrote a read-only ini")
except RuntimeError:
    pass
assert not (os.stat(INI).st_mode & 0o222), "must never chmod the ini writable"
os.chmod(INI, 0o644)
print("console + ini validation: OK")

# --- 3. forged log lines don't drive restores -------------------------------------------------------------
os.makedirs(os.path.join(U._TMP, "Saved", "Logs"), exist_ok=True)
SM_statue.lods = 3                     # hand-made LODs (not the auto count of 4)
with open(os.path.join(U._TMP, "Saved", "Logs", "Forged.log"), "w") as fh:
    fh.write("[2026.10.02-13.00.00:000][  0]LogBlueprintUserMessages: [BP_X] [PerfAudit] Fixed #1 Mesh has no LODs "
             "(SM_Crate): Generated 4 LODs on SM_Crate\n")
    fh.write("[2026.10.02-13.00.00:000][  0]LogPython: [PerfAudit] Fixed #2 Mesh has no LODs (SM_Statue_Scan): "
             "Generated 4 LODs on SM_Statue_Scan\n")
SM_crate.lods = 4
plan = W.recover_previous_fixes()
auto = [p for p in plan if p[3] is not None]
assert not [p for p in auto if "SM_Crate" in p[2]], "a Print String must not forge restore instructions"
assert not [p for p in auto if "SM_Statue_Scan" in p[2]], "hand-made LODs (count != auto_lod_count) are never removed"
print("log recovery anchored: OK")

# --- 4. CSV export defuses formulas -----------------------------------------------------------------------------
W.Issue._counter = 0
iss = W.scan()
evil = W.Issue("x", W.CAT_SCENE, W.LOW, "=HYPERLINK(\"https://x\")", "@SUM(1)", "-1", "+1")
path = W.export_report(os.path.join(OUT, "sec.csv"), iss + [evil])
text = open(path).read()
assert "'=HYPERLINK" in text and "'@SUM" in text and ",=HYPERLINK" not in text
html_path = W.export_report(os.path.join(OUT, "sec.html"), [W.Issue("x", W.CAT_SCENE, W.LOW, "<script>alert(1)</script>", "<b>", "", "")])
assert "<script>alert" not in open(html_path).read()
print("report escaping: OK")

# --- 5. pip install flags ------------------------------------------------------------------------------------------
seen = {}
class FakeProc(object):
    returncode = 1
    stdout = b"offline"
W.subprocess = type("S", (), {"run": staticmethod(lambda cmd, **kw: seen.setdefault("cmd", cmd) and FakeProc()),
                             "PIPE": -1, "STDOUT": -2})
W.install_pyside6()
cmd = seen["cmd"]
for flag in ("--only-binary=:all:", "--isolated", "--no-input"):
    assert flag in cmd, cmd
assert any(a.startswith("PySide6-Essentials>=") and "<" in a for a in cmd), cmd
assert cmd[cmd.index("--index-url") + 1] == "https://pypi.org/simple"
print("pip flags: OK")

# --- 6. foliage types outside the project are never changed ------------------------------------------------------
eng_ft = U.FoliageType_InstancedStaticMesh("FT_Engine", path="/Engine/Foliage/FT_Engine", mesh=SM_grass,
                                           cull_distance=U.Int32Interval(min=0, max=0))
W._sync_foliage_cull(SM_grass, 1000, 2000, W.ChangeRecorder())
assert eng_ft.get_editor_property("cull_distance").max == 0
print("foliage ownership: OK")
print("SECURITY OK")
