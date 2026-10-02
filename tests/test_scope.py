"""Scan scope: Level Instance actors, unloaded sublevels, dedupe."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
import unreal as U
# persistent actor
a = U.Actor("Sun"); a.add(U.PointLightComponent("Big", attenuation_radius=20000.0))
# a light only reachable through the world iterator (e.g. inside a Level Instance)
li = U.Actor("LI_Camp_Light"); li.add(U.PointLightComponent("CampLight", attenuation_radius=30000.0))
U.EXTRA_WORLD_ACTORS[:] = [li, U.WorldSettings("WorldSettings")]
U.EditorActorSubsystem.actors = [a, a]       # duplicate on purpose: must be deduped
U.LOADED_LEVELS[:] = [U._Level("PersistentLevel", path="/Game/Maps/PL_Vignette_Site19_primary_default"),
                      U._Level("PersistentLevel", path="/Game/Maps/SL_Site19_Lighting")]
U.LevelStreaming("LS_Lighting", pkg="/Game/Maps/SL_Site19_Lighting").loaded = U.LOADED_LEVELS[1]
U.LevelStreaming("LS_FX", pkg="/Game/Maps/SL_Site19_FX")          # NOT loaded
import world_perf_audit as W
acts = W._get_actors()
print("actors:", [x.get_actor_label() for x in acts])
assert [x.get_actor_label() for x in acts] == ["Sun", "LI_Camp_Light"], "dedupe + world-iterator actors + no WorldSettings"
iss = W.scan()
radius = [i.obj for i in iss if i.check == "light_radius"]
print("light issues:", radius)
assert "LI_Camp_Light > CampLight" not in radius, "Level Instance contents get no actor-level fixes"
assert "LI_Camp_Light" in W._READONLY_ACTORS.__repr__() or any("LI_Camp_Light" in p for p in W._READONLY_ACTORS)
sc = W._STATE["scope"]
print("scope:", W._scope_text(sc))
assert sc["levels_unloaded"] == ["SL_Site19_FX"] and len(sc["levels_loaded"]) == 2
W.print_report()
from PySide6 import QtWidgets
win = W.show(); win.on_scan(); QtWidgets.QApplication.processEvents()
print("header:", win.lbl_scanned.text()[:140])
print("status:", win.lbl_status.text())
assert "NOT loaded" in win.lbl_scanned.text() and "SL_Site19_FX" in win.lbl_scanned.toolTip()
print("SCOPE OK")
