# -*- coding: utf-8 -*-
"""
Parent Actors  -  Unreal Engine 5.6 editor tool (single Python script, Qt UI)
==============================================================================

Attach actors (meshes, lights, blueprints... anything with a root component)
under a parent actor: like dragging them onto it in the Outliner, for many
actors at once, with the reasons shown when Unreal can't attach one. (The
Outliner's refusals are copied: BSP brushes, landscape, Child Actor Component
actors, loops, other levels. Class-specific editor rules that Python can't see
are not.)

PANEL
-----
1. Select the parent (level viewport or Outliner) and click "Set selected as
   parent". It stays set while you select other things.
2. Select the children and click "Add selected" (repeat to add more).
3. Click "Attach to parent". One Ctrl+Z undoes the whole attach.

Quick: select the children, Ctrl+click the parent LAST, then click "Attach
selection under the last selected". With two actors selected, the first goes
under the second.

HOW TO RUN  (needs the "Python Editor Script Plugin")
----------
A) Paste: Window > Output Log, set the dropdown left of the input box to
   "Python", paste this whole script, press Enter.
B) File:  Tools > Execute Python Script... and pick this file.
C) Module: put it in <Project>/Content/Python/ and run
      import parent_actors; parent_actors.show()

NOTE: this script never spells out the Python file extension on purpose: when
code is pasted into the Output Log, Unreal treats text containing it as a file
path ("Could not load Python file").

Without Qt (PySide6) it runs in text mode (Output Log, Python):
   parent_actors.attach_selected()     # all selected actors under the last selected one
   parent_actors.detach_selected()     # detach the selected actors (they keep their place)
   parent_actors.set_parent(); parent_actors.add_children(); parent_actors.attach_children()
"""

_BEFORE_PASTE = dict(globals())      # pasted into the Output Log: what its shared namespace held before this script

import importlib
import os
import subprocess
import sys
import types

try:
    import unreal
except ImportError:          # imported outside Unreal (tests use a fake module)
    unreal = None

__version__ = "1.0.0"
TOOL_NAME = "Parent Actors"
WINDOW_OBJECT_NAME = "ParentActorsWindow"

CONFIG = {
    "keep_world": True,       # True: children stay where they are. False: they snap onto the parent (or its socket)
    "match_mobility": True,   # a Static child under a Movable/Stationary parent gets the parent's mobility
                              # (Unreal refuses to attach it otherwise)
}

# the actors the panel works on (also used by the text-mode functions)
STATE = {"parent": None, "children": []}


# =============================================================================
# Unreal helpers
# =============================================================================
def _log(msg):
    if unreal is not None:
        unreal.log("[ParentActors] " + msg)


def _warn(msg):
    if unreal is not None:
        unreal.log_warning("[ParentActors] " + msg)


def _actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def selected_actors():
    """The selected level actors, in the order they were selected."""
    try:
        return [a for a in (_actor_sub().get_selected_level_actors() or []) if a is not None]
    except Exception as exc:
        _warn("Couldn't read the selection: %s" % exc)
        return []


def select_actors(actors):
    try:
        _actor_sub().set_selected_level_actors([a for a in actors if alive(a)])
    except Exception as exc:
        _warn("Couldn't select: %s" % exc)


def alive(a):
    if a is None:
        return False
    try:
        return bool(unreal.SystemLibrary.is_valid(a))
    except Exception:
        return False


def label(a):
    if not alive(a):
        return "(missing)"
    try:
        return str(a.get_actor_label())
    except Exception:
        try:
            return str(a.get_name())
        except Exception:
            return "?"


def _key(a):
    try:
        return str(a.get_path_name())
    except Exception:
        return str(id(a))


def same(a, b):
    return a is not None and b is not None and (a is b or _key(a) == _key(b))


def root_of(a):
    """The actor's root component (what gets attached), or None."""
    for get in (lambda: a.root_component, lambda: a.get_editor_property("root_component"),
                lambda: a.get_root_component()):
        try:
            r = get()
            if r is not None:
                return r
        except Exception:
            pass
    return None


def attach_point_of(parent):
    """The component children get attached to: the parent's default attach component (usually its root)."""
    try:
        c = parent.get_default_attach_component()
        if c is not None:
            return c
    except Exception:
        pass
    return root_of(parent)


def parent_of(a):
    try:
        return a.get_attach_parent_actor()
    except Exception:
        return None


def _socket_of(a):
    r = root_of(a)
    try:
        name = str(r.get_attach_socket_name()) if r is not None else ""
    except Exception:
        name = ""
    return "" if name == "None" else name


def _mobility(comp):
    try:
        return comp.get_editor_property("mobility")
    except Exception:
        try:
            return comp.mobility
        except Exception:
            return None


def _mobility_rank(m):
    for i, n in enumerate(("STATIC", "STATIONARY", "MOVABLE")):
        if m == getattr(unreal.ComponentMobility, n):
            return i
    return 2


def _mobility_name(m):
    return ("Static", "Stationary", "Movable")[_mobility_rank(m)] if m is not None else "?"


def is_under(a, b):
    """True when a is attached (directly or further down) under b."""
    seen = set()
    p = parent_of(a)
    while p is not None and _key(p) not in seen:
        if same(p, b):
            return True
        seen.add(_key(p))
        p = parent_of(p)
    return False


def _level_name(a):
    try:
        return str(a.get_outer().get_path_name())
    except Exception:
        return ""


def _short(level_path):
    # "/Game/Maps/Cave.Cave:PersistentLevel" -> "Cave"
    return level_path.split(":")[0].rsplit("/", 1)[-1].split(".")[0]


def sockets_of(a):
    """Socket names on the parent's root component (a static mesh's sockets, a skeleton's bones...)."""
    r = attach_point_of(a) if alive(a) else None
    try:
        return [str(n) for n in (r.get_all_socket_names() or [])] if r is not None else []
    except Exception:
        return []


def describe(a):
    """One line for the panel: label, class, mobility and current parent."""
    if not alive(a):
        return "(missing: deleted, or its level was unloaded)"
    try:
        cls = str(a.get_class().get_name())
    except Exception:
        cls = "Actor"
    r = root_of(a)
    text = "%s   (%s, %s)" % (label(a), cls, _mobility_name(_mobility(r)) if r is not None else "no root")
    p = parent_of(a)
    if p is not None:
        text += "   - under %s" % label(p)
    return text


def _cac_owner(a):
    """The actor whose Child Actor Component spawned a (Unreal re-attaches such actors there), or None."""
    try:
        return a.get_parent_actor() if a.is_child_actor() else None
    except Exception:
        return None


def _editor_refusal(child, parent):
    """Cases the Outliner refuses (UEditorEngine::CanParentActors) that the attach call itself doesn't check."""
    brush, volume = getattr(unreal, "Brush", None), getattr(unreal, "Volume", None)
    if brush is not None:
        for a, who in ((child, "it is"), (parent, "the parent is")):
            if isinstance(a, brush) and not (volume is not None and isinstance(a, volume)):
                return "%s a BSP brush: Unreal doesn't attach BSP brushes (the Outliner refuses it too)" % who
    for name in ("LandscapeProxy", "LandscapeSplineActor", "LandscapeGizmoActor"):
        cls = getattr(unreal, name, None)
        if cls is not None and isinstance(child, cls):
            return "landscape actors can't be attached to other actors"
    owner = _cac_owner(child)
    if owner is not None:
        return ("it is spawned by a Child Actor Component of %s: Unreal puts it back there "
                "(change it in that Blueprint)" % label(owner))
    return ""


def _attached_here(child, parent, socket):
    """Is child already attached to the parent's attach component, at that socket?"""
    r = root_of(child)
    try:
        ap = r.get_attach_parent()
        here = ap is not None and same(ap, attach_point_of(parent))
    except Exception:
        here = same(parent_of(child), parent)
    return here and _socket_of(child) == (socket or "")


def check(child, parent, match_mobility=None, socket="", keep_world=True):
    """Can child be attached under parent? Returns (status, message, new_mobility):
    status "ok", "skip" (nothing to do) or "error"; new_mobility is the mobility the child will get (or None).
    An "ok" with the message "resnap" means: already attached, but it should snap onto the parent again."""
    match = CONFIG["match_mobility"] if match_mobility is None else match_mobility
    if not alive(child):
        return "error", "it no longer exists (deleted, or its level was unloaded)", None
    if not alive(parent):
        return "error", "the parent no longer exists (deleted, or its level was unloaded)", None
    if same(child, parent):
        return "skip", "it is the parent itself", None
    croot, proot = root_of(child), attach_point_of(parent)
    if croot is None:
        return "error", "it has no root component, so it can't be attached", None
    if proot is None:
        return "error", "the parent has no root component", None
    why = _editor_refusal(child, parent)
    if why:
        return "error", why, None
    if is_under(parent, child):
        return "error", "the parent is attached under it (that would make a loop)", None
    lc, lp = _level_name(child), _level_name(parent)
    if lc and lp and lc != lp:
        return "error", "it is in a different level than the parent (%s vs %s)" % (_short(lc), _short(lp)), None
    if _attached_here(child, parent, socket):
        if keep_world:
            return "skip", "already attached to it", None
        return "ok", "resnap", None          # Unreal ignores an attach to the same place, so detach + attach
    cm, pm = _mobility(croot), _mobility(proot)
    new_mob = None
    if cm is not None and pm is not None and _mobility_rank(cm) == 0 and _mobility_rank(pm) > 0:
        # Unreal refuses to attach a Static component under a non-Static one ("AttachTo: ... Aborting.")
        if not match:
            return "error", "it is %s but the parent is %s: Unreal won't attach it (tick Match mobility)" % (
                _mobility_name(cm), _mobility_name(pm)), None
        new_mob = pm
    return "ok", "", new_mob


def _rules(keep_world):
    A = unreal.AttachmentRule
    if keep_world:
        return A.KEEP_WORLD, A.KEEP_WORLD, A.KEEP_WORLD
    return A.SNAP_TO_TARGET, A.SNAP_TO_TARGET, A.KEEP_WORLD     # snap position + rotation, keep the scale


def _unique(actors):
    out, seen = [], set()
    for a in actors:
        if a is not None and _key(a) not in seen:
            seen.add(_key(a))
            out.append(a)
    return out


def _below(comp):
    """Every component attached under comp: the actor's own sub-components and other actors attached to it."""
    try:
        return [d for d in (comp.get_children_components(True) or []) if d is not None]
    except Exception:
        return []


def _raise_mobility(child, root, mob):
    """Give root (and everything attached under it that is less mobile) the mobility mob, recorded for undo.
    Returns [(component, old mobility)]. Unreal itself spreads Movable down the hierarchy without recording it,
    and doesn't spread Stationary at all (a Static component under a Stationary one would drop off on reload)."""
    rank, saved = _mobility_rank(mob), []
    for comp in [root] + _below(root):
        m = _mobility(comp)
        if m is None or _mobility_rank(m) >= rank:
            continue
        comp.modify()
        try:
            owner = comp.get_owner()
            if owner is not None and not same(owner, child):
                owner.modify()                 # another actor attached under the child: its package gets saved
        except Exception:
            pass
        saved.append((comp, m))
    for comp, _m in saved:
        comp.set_mobility(mob)
    return saved


def _restore_mobility(saved):
    for comp, m in reversed(saved):
        try:
            comp.set_mobility(m)
        except Exception:
            pass


def attach(children, parent, keep_world=None, socket="", match_mobility=None):
    """Attach children under parent, in one undo step. Returns [(actor, status, message)], status "attached",
    "skip" or "error". keep_world False snaps them onto the parent (or socket)."""
    keep = CONFIG["keep_world"] if keep_world is None else keep_world
    socket = "" if socket in (None, "None", "(none)") else str(socket)
    results, todo = [], []
    for c in _unique(children):
        status, msg, mob = check(c, parent, match_mobility, socket, keep)
        if status == "ok":
            todo.append((c, mob, msg == "resnap"))
        else:
            results.append((c, status, msg))
    if todo:
        lr, rr, sr = _rules(keep)
        D = unreal.DetachmentRule
        title = "Attach %d actor%s to %s" % (len(todo), "" if len(todo) == 1 else "s", label(parent))
        with unreal.ScopedEditorTransaction(title):
            for obj in (parent, attach_point_of(parent)):
                try:
                    obj.modify()
                except Exception:
                    pass
            for c, mob, resnap in todo:
                root = root_of(c)
                was = parent_of(c)
                saved = []
                try:
                    c.modify()
                    root.modify()
                    if was is not None:
                        was.modify()
                    note = ""
                    if mob is not None:
                        saved = _raise_mobility(c, root, mob)
                        extra = len(saved) - 1
                        note = " (made %s to match the parent%s)" % (_mobility_name(mob), (
                            ", with %d component%s attached under it" % (extra, "" if extra == 1 else "s"))
                            if extra > 0 else "")
                    if resnap:
                        c.detach_from_actor(D.KEEP_WORLD, D.KEEP_WORLD, D.KEEP_WORLD)
                    ok = c.attach_to_actor(parent, socket, lr, rr, sr, False)
                    if ok is False or not same(parent_of(c), parent):
                        _restore_mobility(saved)
                        results.append((c, "error", "Unreal refused the attach (see the warnings above in the Output Log)"))
                    else:
                        results.append((c, "attached", "%s %s%s%s" % (
                            "snapped onto" if resnap else "under", label(parent),
                            (" at socket %s" % socket) if socket else "", note)))
                except Exception as exc:
                    _restore_mobility(saved)
                    results.append((c, "error", "attach failed: %s" % exc))
    for c, status, msg in results:
        line = "%s: %s" % (label(c), msg) if status != "attached" else "%s -> %s" % (label(c), msg)
        (_warn if status == "error" else _log)(line)
    return results


def detach(actors):
    """Detach actors from their parents (they keep their place in the world), in one undo step."""
    results, todo = [], []
    for a in _unique(actors):
        if not alive(a):
            results.append((a, "error", "it no longer exists (deleted, or its level was unloaded)"))
        elif parent_of(a) is None:
            results.append((a, "skip", "not attached to anything"))
        elif _cac_owner(a) is not None:
            results.append((a, "error", "it is spawned by a Child Actor Component of %s: Unreal puts it back "
                                        "there (change it in that Blueprint)" % label(_cac_owner(a))))
        else:
            todo.append(a)
    if todo:
        D = unreal.DetachmentRule
        with unreal.ScopedEditorTransaction("Detach %d actor%s" % (len(todo), "" if len(todo) == 1 else "s")):
            for a in todo:
                was = parent_of(a)
                try:
                    a.modify()
                    root = root_of(a)
                    if root is not None:
                        root.modify()
                    was.modify()
                    a.detach_from_actor(D.KEEP_WORLD, D.KEEP_WORLD, D.KEEP_WORLD)
                    if parent_of(a) is None:
                        results.append((a, "detached", "detached from %s" % label(was)))
                    else:
                        results.append((a, "error", "Unreal didn't detach it"))
                except Exception as exc:
                    results.append((a, "error", "detach failed: %s" % exc))
    for a, status, msg in results:
        (_warn if status == "error" else _log)("%s: %s" % (label(a), msg))
    return results


def summary(results, verb="attached"):
    done = sum(1 for r in results if r[1] == verb)
    skipped = [r for r in results if r[1] == "skip"]
    errors = [r for r in results if r[1] == "error"]
    parts = ["%d %s" % (done, verb)]
    if skipped:
        parts.append("%d skipped" % len(skipped))
    if errors:
        parts.append("%d not: %s - %s" % (len(errors), label(errors[0][0]), errors[0][2]) if len(errors) == 1
                     else "%d failed (see the Output Log)" % len(errors))
    return ", ".join(parts) + "."


# --- text-mode functions (the panel uses the same state) ---------------------
def set_parent(actor=None):
    """Use actor (default: the selected actor; the last one if several are selected) as the parent."""
    if actor is None:
        sel = selected_actors()
        if not sel:
            _warn("Select the parent actor first.")
            return None
        actor = sel[-1]
    STATE["parent"] = actor
    STATE["children"] = [c for c in STATE["children"] if not same(c, actor)]
    _log("Parent: %s" % label(actor))
    return actor


def add_children(actors=None):
    """Add actors (default: the selection) to the children list. The parent itself is never added."""
    actors = selected_actors() if actors is None else list(actors)
    added = 0
    for a in actors:
        if same(a, STATE["parent"]) or any(same(a, c) for c in STATE["children"]):
            continue
        STATE["children"].append(a)
        added += 1
    return added


def attach_children(keep_world=None, socket="", match_mobility=None):
    if not alive(STATE["parent"]):
        _warn("Set a parent first.")
        return []
    return attach(STATE["children"], STATE["parent"], keep_world, socket, match_mobility)


def attach_selected(keep_world=None, socket="", match_mobility=None):
    """All selected actors under the LAST selected one (two selected: the first goes under the second)."""
    sel = _unique(selected_actors())
    if len(sel) < 2:
        _warn("Select the children, then Ctrl+click the parent last (at least 2 actors).")
        return []
    res = attach(sel[:-1], sel[-1], keep_world, socket, match_mobility)
    _log(summary(res))
    return res


def detach_selected():
    res = detach(selected_actors())
    _log(summary(res, "detached"))
    return res


# =============================================================================
# Qt (same per-user PySide6 install as the other tools in this repository)
# =============================================================================
_QT = None


def _deps_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "UnrealWorldPerfAudit", "py%d%d" % sys.version_info[:2], "site-packages")


def _load_qt():
    global _QT
    if _QT is not None:
        return _QT
    d = _deps_dir()
    if os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)      # appended (never shadows engine modules); no .pth files are executed
    for binding in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
        try:
            mods = [importlib.import_module("%s.%s" % (binding, m)) for m in ("QtCore", "QtGui", "QtWidgets")]
            _QT = tuple(mods)
            return _QT
        except Exception:
            continue
    return None


def install_pyside6():
    """pip-install PySide6 (Essentials) into a per-user folder, outside the project. One time only."""
    target = _deps_dir()
    if not os.path.isdir(target):
        os.makedirs(target)
    py = unreal.get_interpreter_executable_path()
    cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--upgrade",
           "--isolated", "--index-url", "https://pypi.org/simple",
           "--only-binary=:all:", "--target", target, "PySide6-Essentials>=6.5,<7"]
    _log("Installing PySide6: %s" % " ".join(cmd))
    with unreal.ScopedSlowTask(1, "Installing PySide6 for %s (one-time, ~100 MB)..." % TOOL_NAME) as task:
        task.make_dialog(False)
        task.enter_progress_frame(1)
        kw = {}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    out = proc.stdout.decode("utf-8", "replace") if proc.stdout else ""
    if proc.returncode != 0:
        _warn("pip failed (%d):\n%s" % (proc.returncode, out))
        unreal.EditorDialog.show_message(TOOL_NAME, "PySide6 install failed - see the Output Log.", unreal.AppMsgType.OK)
        return False
    importlib.invalidate_caches()
    return _load_qt() is not None


_STYLE = """
* { font-family: "Segoe UI", "Inter", "Roboto", sans-serif; font-size: 9pt; }
QWidget#ParentRoot { background: #18181b; }
QWidget { color: #e4e4e7; }
QFrame#Header { background: #111113; border-bottom: 1px solid #27272a; }
QLabel#Logo { background: #a78bfa; color: #160f2b; border-radius: 6px; font-weight: 800; font-size: 10pt; }
QLabel#Title { font-size: 13pt; font-weight: 600; color: #fafafa; }
QLabel#Muted, QLabel#Subtitle { color: #8e8e96; }
QFrame#Card { background: #1f1f23; border: 1px solid #2a2a2e; border-radius: 6px; }
QLabel#Step { color: #a78bfa; font-weight: 700; font-size: 8pt; }
QLabel#Value { color: #fafafa; font-weight: 600; }
QPushButton { background: #27272a; color: #e4e4e7; border: 1px solid #34343a; border-radius: 5px; padding: 6px 12px; }
QPushButton:hover { background: #303036; border-color: #45454d; }
QPushButton:disabled { color: #5c5c63; background: #1f1f23; border-color: #2a2a2e; }
QPushButton#Primary { background: #7c3aed; border-color: #7c3aed; color: #ffffff; font-weight: 600; }
QPushButton#Primary:hover { background: #8b5cf6; }
QPushButton#Primary:disabled { background: #2e2147; border-color: #2e2147; color: #9a8cb8; }
QListWidget { background: #111113; border: 1px solid #34343a; border-radius: 5px; padding: 2px; }
QListWidget::item { padding: 4px 6px; }
QListWidget::item:selected { background: #3b2a63; color: #ffffff; }
QComboBox { background: #111113; color: #e4e4e7; border: 1px solid #34343a; border-radius: 5px; padding: 4px 8px; }
QComboBox QAbstractItemView { background: #1f1f23; color: #e4e4e7; selection-background-color: #3b2a63; }
QCheckBox { spacing: 6px; color: #c4c4cc; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #45454d; border-radius: 3px; background: #111113; }
QCheckBox::indicator:checked { background: #7c3aed; border-color: #7c3aed; }
QFrame#StatusBar { background: #111113; border-top: 1px solid #27272a; }
QToolTip { background: #27272a; color: #e4e4e7; border: 1px solid #3f3f46; padding: 4px; }
"""

_NO_SOCKET = "(no socket)"


def _make_window_class(QtCore, QtGui, QtWidgets):
    Qt = QtCore.Qt

    def card(step, hint):
        f = QtWidgets.QFrame()
        f.setObjectName("Card")
        lay = QtWidgets.QVBoxLayout(f)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        head = QtWidgets.QLabel(step)
        head.setObjectName("Step")
        lay.addWidget(head)
        if hint:
            h = QtWidgets.QLabel(hint)
            h.setObjectName("Muted")
            h.setWordWrap(True)
            lay.addWidget(h)
        return f, lay

    def button(text, tip, slot, primary=False):
        b = QtWidgets.QPushButton(text)
        b.setToolTip(tip)
        if primary:
            b.setObjectName("Primary")
        b.clicked.connect(slot)
        return b

    class ParentWindow(QtWidgets.QWidget):
        def __init__(self):
            super(ParentWindow, self).__init__(None)
            self.setObjectName(WINDOW_OBJECT_NAME)
            self.setWindowTitle("%s %s" % (TOOL_NAME, __version__))
            self.setStyleSheet(_STYLE)
            self.resize(470, 660)
            self._row_keys = []
            root = QtWidgets.QWidget(self)
            root.setObjectName("ParentRoot")
            outer = QtWidgets.QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(root)
            main = QtWidgets.QVBoxLayout(root)
            main.setContentsMargins(0, 0, 0, 0)
            main.setSpacing(0)

            header = QtWidgets.QFrame()
            header.setObjectName("Header")
            hl = QtWidgets.QHBoxLayout(header)
            hl.setContentsMargins(14, 10, 14, 10)
            logo = QtWidgets.QLabel("PA")
            logo.setObjectName("Logo")
            logo.setFixedSize(30, 30)
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hl.addWidget(logo)
            tl = QtWidgets.QVBoxLayout()
            tl.setSpacing(0)
            t = QtWidgets.QLabel(TOOL_NAME)
            t.setObjectName("Title")
            s = QtWidgets.QLabel("Attach actors under a parent, like dragging them onto it in the Outliner")
            s.setObjectName("Subtitle")
            s.setWordWrap(True)
            tl.addWidget(t)
            tl.addWidget(s)
            hl.addLayout(tl, 1)
            main.addWidget(header)

            body = QtWidgets.QVBoxLayout()
            body.setContentsMargins(12, 12, 12, 12)
            body.setSpacing(10)
            main.addLayout(body, 1)

            # 1 - parent
            f, lay = card("1  PARENT", "Select the parent in the level or the Outliner, then set it.")
            self.lbl_parent = QtWidgets.QLabel("No parent set")
            self.lbl_parent.setObjectName("Value")
            self.lbl_parent.setWordWrap(True)
            lay.addWidget(self.lbl_parent)
            row = QtWidgets.QHBoxLayout()
            self.btn_set_parent = button("Set selected as parent", "Use the selected actor as the parent "
                                         "(the last one, if several are selected).", self.on_set_parent, True)
            self.btn_select_parent = button("Select", "Select the parent in the level.", self.on_select_parent)
            self.btn_clear_parent = button("Clear", "Forget the parent.", self.on_clear_parent)
            row.addWidget(self.btn_set_parent, 1)
            row.addWidget(self.btn_select_parent)
            row.addWidget(self.btn_clear_parent)
            lay.addLayout(row)
            body.addWidget(f)

            # 2 - children
            f, lay = card("2  CHILDREN", "Select the actors to put under the parent and add them. "
                                         "Double-click a row to select that actor.")
            self.list = QtWidgets.QListWidget()
            self.list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.list.setMinimumHeight(170)
            self.list.itemDoubleClicked.connect(self.on_row_double_clicked)
            lay.addWidget(self.list, 1)
            row = QtWidgets.QHBoxLayout()
            self.btn_add = button("Add selected", "Add the selected actors to the list (the parent is skipped).",
                                  self.on_add, True)
            self.btn_remove = button("Remove", "Remove the highlighted rows from the list.", self.on_remove)
            self.btn_clear = button("Clear", "Empty the list.", self.on_clear_children)
            self.btn_select_children = button("Select", "Select the listed actors in the level.",
                                              self.on_select_children)
            row.addWidget(self.btn_add, 1)
            row.addWidget(self.btn_remove)
            row.addWidget(self.btn_clear)
            row.addWidget(self.btn_select_children)
            lay.addLayout(row)
            body.addWidget(f, 1)

            # 3 - attach
            f, lay = card("3  ATTACH", "")
            grid = QtWidgets.QGridLayout()
            grid.setHorizontalSpacing(8)
            grid.addWidget(QtWidgets.QLabel("Position"), 0, 0)
            self.cmb_mode = QtWidgets.QComboBox()
            self.cmb_mode.addItems(["Keep where they are", "Snap onto the parent"])
            self.cmb_mode.setToolTip("Keep: the children don't move, they just follow the parent from now on.\n"
                                     "Snap: they move onto the parent's pivot (or socket); scale is kept.")
            self.cmb_mode.setCurrentIndex(0 if CONFIG["keep_world"] else 1)
            grid.addWidget(self.cmb_mode, 0, 1)
            grid.addWidget(QtWidgets.QLabel("Socket"), 1, 0)
            self.cmb_socket = QtWidgets.QComboBox()
            self.cmb_socket.setToolTip("Sockets of the parent's root component: a Static Mesh Actor's sockets, a "
                                       "Skeletal Mesh Actor's bones and sockets.\nSockets on other components of a "
                                       "Blueprint aren't listed: Unreal attaches actors to the root.")
            grid.addWidget(self.cmb_socket, 1, 1)
            grid.setColumnStretch(1, 1)
            lay.addLayout(grid)
            self.chk_mobility = QtWidgets.QCheckBox("Match mobility")
            self.chk_mobility.setChecked(bool(CONFIG["match_mobility"]))
            self.chk_mobility.setToolTip("Unreal can't attach a Static actor under a Movable (or Stationary) one.\n"
                                         "Ticked: such a child gets the parent's mobility. Unticked: it's skipped.")
            lay.addWidget(self.chk_mobility)
            row = QtWidgets.QHBoxLayout()
            self.btn_attach = button("Attach to parent", "Attach every listed actor under the parent "
                                     "(one Ctrl+Z undoes it).", self.on_attach, True)
            self.btn_detach = button("Detach children", "Detach the listed actors from whatever they are "
                                     "attached to. They keep their place.", self.on_detach)
            row.addWidget(self.btn_attach, 1)
            row.addWidget(self.btn_detach)
            lay.addLayout(row)
            body.addWidget(f)

            # quick
            f, lay = card("QUICK", "Select the children, Ctrl+click the parent last. With two actors "
                                   "selected, the first goes under the second.")
            row = QtWidgets.QHBoxLayout()
            self.btn_quick = button("Attach selection under the last selected", "Uses the position, socket and "
                                    "mobility options above.", self.on_quick)
            self.btn_quick_detach = button("Detach selection", "Detach the selected actors from their parents.",
                                           self.on_quick_detach)
            row.addWidget(self.btn_quick, 1)
            row.addWidget(self.btn_quick_detach)
            lay.addLayout(row)
            body.addWidget(f)

            status = QtWidgets.QFrame()
            status.setObjectName("StatusBar")
            sl = QtWidgets.QHBoxLayout(status)
            sl.setContentsMargins(12, 6, 12, 6)
            self.lbl_status = QtWidgets.QLabel("Set a parent, add children, attach.")
            self.lbl_status.setObjectName("Muted")
            self.lbl_status.setWordWrap(True)
            sl.addWidget(self.lbl_status, 1)
            main.addWidget(status)
            self.refresh()

        # --- state -> widgets ------------------------------------------------
        def refresh(self):
            p = STATE["parent"]
            if p is None:
                self.lbl_parent.setText("No parent set")
            else:
                self.lbl_parent.setText(describe(p))
            keep = self.cmb_socket.currentText()
            self.cmb_socket.blockSignals(True)
            self.cmb_socket.clear()
            self.cmb_socket.addItem(_NO_SOCKET)
            self.cmb_socket.addItems(sockets_of(p))
            i = self.cmb_socket.findText(keep)
            self.cmb_socket.setCurrentIndex(i if i >= 0 else 0)
            self.cmb_socket.blockSignals(False)
            keys = {self._row_keys[i.row()] for i in self.list.selectedIndexes() if i.row() < len(self._row_keys)}
            self.list.clear()
            self._row_keys = [_key(c) for c in STATE["children"]]
            for i, c in enumerate(STATE["children"]):
                self.list.addItem(describe(c))
                if self._row_keys[i] in keys:
                    self.list.item(i).setSelected(True)
            has_p, has_c = alive(p), bool(STATE["children"])
            self.btn_select_parent.setEnabled(has_p)
            self.btn_clear_parent.setEnabled(p is not None)
            self.btn_attach.setEnabled(has_p and has_c)
            self.btn_detach.setEnabled(has_c)
            self.btn_remove.setEnabled(has_c)
            self.btn_clear.setEnabled(has_c)
            self.btn_select_children.setEnabled(has_c)
            self.cmb_socket.setEnabled(has_p)

        def status(self, text):
            self.lbl_status.setText(text)

        def changeEvent(self, ev):
            # back from the editor: names, parents and mobility may have changed in the Outliner
            try:
                if ev.type() == QtCore.QEvent.Type.ActivationChange and self.isActiveWindow():
                    self.refresh()
            except Exception:
                pass
            super(ParentWindow, self).changeEvent(ev)

        def options(self):
            sock = self.cmb_socket.currentText()
            return {"keep_world": self.cmb_mode.currentIndex() == 0,
                    "socket": "" if sock == _NO_SOCKET else sock,
                    "match_mobility": self.chk_mobility.isChecked()}

        # --- parent ------------------------------------------------------------
        def on_set_parent(self):
            sel = selected_actors()
            if not sel:
                self.status("Select the parent actor first (level viewport or Outliner).")
                return
            set_parent(sel[-1])
            self.refresh()
            self.status("Parent: %s.%s" % (label(sel[-1]), "" if len(sel) == 1 else
                                           " %d actors were selected: the last one was used." % len(sel)))

        def on_select_parent(self):
            select_actors([STATE["parent"]])

        def on_clear_parent(self):
            STATE["parent"] = None
            self.refresh()
            self.status("Parent cleared.")

        # --- children ----------------------------------------------------------
        def on_add(self):
            sel = selected_actors()
            if not sel:
                self.status("Select the actors to add first.")
                return
            n = add_children(sel)
            self.refresh()
            skipped = len(sel) - n
            self.status("Added %d actor%s.%s" % (n, "" if n == 1 else "s", (" %d skipped (the parent, or "
                                                 "already in the list)." % skipped) if skipped else ""))

        def on_remove(self):
            rows = sorted({r.row() for r in self.list.selectedIndexes()}, reverse=True)
            if not rows:
                self.status("Highlight the rows to remove.")
                return
            for r in rows:
                if r < len(STATE["children"]):
                    del STATE["children"][r]
            self.refresh()
            self.status("Removed %d." % len(rows))

        def on_clear_children(self):
            STATE["children"] = []
            self.refresh()
            self.status("List cleared.")

        def on_select_children(self):
            select_actors(STATE["children"])

        def on_row_double_clicked(self, item):
            r = self.list.row(item)
            if 0 <= r < len(STATE["children"]):
                select_actors([STATE["children"][r]])

        # --- attach / detach ---------------------------------------------------
        def on_attach(self):
            if not alive(STATE["parent"]):
                self.status("Set a parent first.")
                return
            res = attach(STATE["children"], STATE["parent"], **self.options())
            self.refresh()
            self.status(summary(res))

        def on_detach(self):
            res = detach(STATE["children"])
            self.refresh()
            self.status(summary(res, "detached"))

        def on_quick(self):
            sel = _unique(selected_actors())
            if len(sel) < 2:
                self.status("Select the children, then Ctrl+click the parent last (at least 2 actors).")
                return
            o = self.options()
            if o["socket"] and o["socket"] not in sockets_of(sel[-1]):
                o["socket"] = ""          # the socket list belongs to the panel's parent, not this one
            res = attach(sel[:-1], sel[-1], **o)
            self.refresh()
            self.status("Under %s: %s" % (label(sel[-1]), summary(res)))

        def on_quick_detach(self):
            res = detach(selected_actors())
            self.refresh()
            self.status(summary(res, "detached"))

        def closeEvent(self, ev):
            _stop_qt_tick()
            super(ParentWindow, self).closeEvent(ev)

    return ParentWindow


_TICK = {"handle": None}


def _start_qt_tick(QtWidgets):
    # Windows: Unreal's message pump already drives Qt windows. Elsewhere Qt needs a nudge every frame.
    if sys.platform == "win32" or _TICK["handle"] is not None:
        return

    def _qt_tick(_dt):
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
    _TICK["handle"] = unreal.register_slate_post_tick_callback(_qt_tick)


def _stop_qt_tick():
    if _TICK["handle"] is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_TICK["handle"])
        except Exception:
            pass
        _TICK["handle"] = None


def show(reuse=True):
    """Open the panel (offers to install PySide6 if Qt is missing)."""
    qt = _load_qt()
    if qt is None:
        r = unreal.EditorDialog.show_message(
            TOOL_NAME, "The panel needs Qt for Python (PySide6), which Unreal doesn't ship.\n\n"
            "Yes: install PySide6 now (one-time, ~100 MB, into\n%s)\n"
            "No: text mode - use parent_actors.attach_selected() in the Output Log." % _deps_dir(),
            unreal.AppMsgType.YES_NO_CANCEL)
        if r == unreal.AppReturnType.YES and install_pyside6():
            qt = _load_qt()
        if qt is None:
            _log("Text mode: select the children, Ctrl+click the parent last, then run "
                 "parent_actors.attach_selected(). parent_actors.detach_selected() detaches.")
            return None
    QtCore, QtGui, QtWidgets = qt
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    keep = sys.__dict__.setdefault("_parent_actors_keep", {})
    stored = keep.get("window")
    found = [w for w in app.topLevelWidgets() if w.objectName() == WINDOW_OBJECT_NAME]
    if reuse and found:
        w = stored if any(w is stored for w in found) else found[0]
        w.refresh()
        w.show()
        w.raise_()
        w.activateWindow()
        _start_qt_tick(QtWidgets)        # closing the panel stopped it
        return w
    for w in found:
        w.close()
        w.setObjectName("")              # never found again; freed with its last reference (no Qt event loop here)
    win = _make_window_class(QtCore, QtGui, QtWidgets)()
    win.show()
    try:
        unreal.parent_external_window_to_slate(int(win.winId()))
    except Exception:
        pass
    _start_qt_tick(QtWidgets)
    keep["app"], keep["window"] = app, win
    return win


def _move_to_module(console, before, module):
    """Pasted code runs in the Output Log's namespace, which every pasted script shares. Rebind this script's
    functions to the module's own namespace (another tool pasted later can't change what they call), then give the
    console its previous names back (this script doesn't change what other pasted tools call), plus parent_actors."""
    ns = module.__dict__
    for k, v in list(ns.items()):
        if isinstance(v, types.FunctionType) and v.__globals__ is console:
            f = types.FunctionType(v.__code__, ns, v.__name__, v.__defaults__, v.__closure__)
            f.__kwdefaults__, f.__doc__ = v.__kwdefaults__, v.__doc__
            ns[k] = f
    for k in list(console):
        if k not in before:
            del console[k]
        elif console[k] is not before[k]:
            console[k] = before[k]
    console["parent_actors"] = module
    return module


if unreal is not None and not __name__.endswith("parent_actors"):
    # Pasted into the Output Log or run as a script file: register this code as the module "parent_actors" so
    # parent_actors.attach_selected() etc. work afterwards, then open the panel.
    _old = sys.modules.get("parent_actors")
    if _old is not None:                   # pasted again: keep the parent and the list
        try:
            STATE.update(_old.STATE)
        except Exception:
            pass
    _module = types.ModuleType("parent_actors")
    _module.__dict__.update(globals())
    _module.__name__ = "parent_actors"
    sys.modules["parent_actors"] = _module
    _move_to_module(globals(), _BEFORE_PASTE, _module).show(reuse=False)
