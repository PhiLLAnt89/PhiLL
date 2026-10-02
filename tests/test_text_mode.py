"""Text mode (no Qt), cascades check, window reuse, empty level."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)
import unreal as U
U.SystemLibrary.CVARS["r.Shadow.Virtual.Enable"] = 0
a = U.Actor("Sun"); a.add(U.DirectionalLightComponent("Sun", dynamic_shadow_cascades=6))
U.EditorActorSubsystem.actors = [a]
import world_perf_audit as W
iss = W.scan()
print([(i.check, i.obj) for i in iss])
assert any(i.check == "light_cascades" for i in iss)
W.fix_all(include_visual=True); assert a.comps[0].get_editor_property("dynamic_shadow_cascades") == 3
# text mode + reuse=False path
W.run_text_mode()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
w1 = W.show(); w2 = W.show(); assert w1 is w2
w3 = W.show(reuse=False); assert w3 is not w1
# empty level
U.EditorActorSubsystem.actors = []
print("empty scan:", len(W.scan()))
print("EXTRA OK")
