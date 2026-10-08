"""PySide6 6.12.0 frees Python's None (it drops a reference each time a Qt call returns an empty value); on
Python 3.11, which Unreal 5.6 embeds, that aborts the process. Checks: the PySide6 installed here doesn't do it, and
all three tools refuse to load a 6.12 PySide6, explain it, and only ever install a version below it."""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
import unreal as U  # noqa: E402  (mock)
from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402
import PySide6  # noqa: E402

# --- the Qt binding the tests run with keeps None's reference count -------------------------------------------------
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
item = QtGui.QStandardItem("x")
role = QtCore.Qt.ItemDataRole.UserRole + 7
for _ in range(50):
    item.data(role)                       # first calls set things up (and may keep references to None)
before = sys.getrefcount(None)
for _ in range(2000):
    item.data(role)
drift = sys.getrefcount(None) - before
assert drift > -100, "PySide6 %s loses references to None (%d): keep QT_SPEC below it" % (PySide6.__version__, drift)
print("PySide6 %s: None refcount stable" % PySide6.__version__)

# --- every tool pins the installer and guards the loader --------------------------------------------------------------
for name in ("world_perf_audit", "snow_painter", "parent_actors"):
    src = open(os.path.join(ROOT, name + "." + "py"), encoding="utf-8").read()
    assert 'QT_SPEC = "PySide6-Essentials>=6.5,<6.12"' in src and "QT_SPEC]" in src, name
    assert "bad = _bad_pyside6()" in src and "qt is None and _QT_BAD" in src, name
    assert '"PySide6-Essentials>=6.5,<7"' not in src, name

import parent_actors as P  # noqa: E402
import snow_painter as S  # noqa: E402
import world_perf_audit as W  # noqa: E402

# --- detection: only 6.12.x, only before Python 3.12 -----------------------------------------------------------------
real_importlib, real_sys = P.importlib, P.sys


def fake_pyside(version, folder):
    mod = types.SimpleNamespace(__version__=version, __file__=os.path.join(folder, "PySide6", "__init__"))
    return types.SimpleNamespace(import_module=lambda n: mod if n == "PySide6" else real_importlib.import_module(n))


P.importlib = fake_pyside("6.12.0", "/x/site-packages")
assert P._bad_pyside6() == ("6.12.0", os.path.abspath("/x/site-packages"))
P.importlib = fake_pyside("6.11.2", "/x/site-packages")
assert P._bad_pyside6() is None
P.importlib = fake_pyside("6.12.0", "/x/site-packages")
P.sys = types.SimpleNamespace(version_info=(3, 12, 0))
assert P._bad_pyside6() is None, "Python 3.12+ has an immortal None: 6.12 is fine there"
P.importlib, P.sys = real_importlib, real_sys
print("detection: OK")

# --- a 6.12 PySide6 is not loaded; the panel explains and offers the fix -----------------------------------------
messages = []
real_show_message = U.EditorDialog.show_message
U.EditorDialog.show_message = staticmethod(lambda title, text, kind=None: messages.append(text) or U.AppReturnType.NO)
for mod in (P, S, W):
    mod._QT, mod._QT_BAD[:] = None, []
    real_bad = mod._bad_pyside6
    calls = []
    real_text = getattr(mod, "run_text_mode", None)
    if real_text is not None:
        mod.run_text_mode = lambda: calls.append("text")
    # in the tools' own folder: offer to replace it
    mod._bad_pyside6 = lambda mod=mod: ("6.12.0", mod._deps_dir())
    del messages[:]
    assert mod._load_qt() is None and mod._QT_BAD == [("6.12.0", mod._deps_dir())], mod.__name__
    assert mod.show() is None
    assert len(messages) == 1 and "PySide6 6.12.0" in messages[0] and "Yes: replace it with PySide6 6.11" in messages[0]
    if real_text is not None:
        assert calls == ["text"], "declined: World Perf Audit falls back to text mode"
    # somewhere else (e.g. Unreal's own site-packages): the exact downgrade command, no install into our folder
    mod._QT, mod._QT_BAD[:] = None, []
    mod._bad_pyside6 = lambda: ("6.12.0", "/opt/UE/Python/site-packages")
    del messages[:]
    assert mod.show() is None and len(messages) == 1
    assert "Downgrade it" in messages[0] and '"PySide6-Essentials>=6.5,<6.12"' in messages[0], messages[0]
    mod._bad_pyside6 = real_bad
    if real_text is not None:
        mod.run_text_mode = real_text
    mod._QT, mod._QT_BAD[:] = None, []
U.EditorDialog.show_message = real_show_message
print("refused + explained: OK")

# --- the installer asks pip for a version below 6.12 -----------------------------------------------------------------
for mod in (P, S, W):
    seen = []
    real_run = mod.subprocess.run
    mod.subprocess.run = lambda cmd, **kw: seen.append(cmd) or types.SimpleNamespace(returncode=0, stdout=b"")
    try:
        mod.install_pyside6()
    finally:
        mod.subprocess.run = real_run
    assert seen and seen[0][-1] == "PySide6-Essentials>=6.5,<6.12", (mod.__name__, seen)
print("QT GUARD OK")
