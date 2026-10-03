"""1.1 checks: VSM invalidation, Nanite programmable raster, Effect Type create+assign, Lumen foliage, distance-field
resolution, texture streaming pool, CPU (game / render thread) findings, render-thread drivers, MegaLights hint."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "scene.py")).read())   # mock "unreal" module + demo level (U, M_snow, big, ...)
SM_statue.df_scale = 8.0
U.SystemLibrary.CVARS["r.Streaming.PoolSize"] = 100
NS_rain = U.NiagaraSystem("NS_Rain")
U.NiagaraSpriteRendererProperties("Sprite", outer=U.NiagaraEmitter("Drops", outer=NS_rain), material=M_glass)
add(U.Actor("FX_Rain")).add(U.NiagaraComponent("Niagara", asset=NS_rain))
U.EditorActorSubsystem.actors = actors
import world_perf_audit as W

issues = W.scan()
by = {}
for i in issues:
    by.setdefault(i.check, []).append(i)
print("checks with findings:", sorted(by))

# --- VSM invalidation: WPO shadow casters -> Rigid ------------------------------------------------------------
vsm = by["mesh_vsm_invalidation"]
assert {i.obj.split(" (")[0] for i in vsm} == {"SM_Tree", "SM_Grass"}, [i.obj for i in vsm]
tree = [i for i in vsm if i.obj.startswith("SM_Tree")][0]
W.apply_fixes([tree])
comp = tree.targets[0]
assert comp.get_editor_property("shadow_cache_invalidation_behavior") == U.ShadowCacheInvalidationBehavior.RIGID
W.revert_issues([tree])
assert comp.get_editor_property("shadow_cache_invalidation_behavior") == U.ShadowCacheInvalidationBehavior.AUTO
print("vsm invalidation fix/revert: OK")

# --- Nanite programmable raster: advice only --------------------------------------------------------------------
npr = by["mesh_nanite_programmable"]
assert len(npr) == 1 and npr[0].obj == "SM_Tree" and "masked" in npr[0].title and npr[0].fix is None
print("nanite programmable:", npr[0].title)

# --- Effect Type: created once, configured safely, assigned, revert keeps the asset ---------------------------
fx = {i.obj: i for i in by["vfx_no_effect_type"]}
assert set(fx) == {"NS_Snow", "NS_Rain"} and all(i.fix and i.impact == W.LOOK for i in fx.values())
W.apply_fixes([fx["NS_Snow"]])
et = NS_snow.get_editor_property("effect_type")
assert et is not None and et.get_path_name().startswith("/Game/PerfAudit/ET_PerfAudit_DistanceCull")
assert et.get_editor_property("cull_reaction") == U.NiagaraCullReaction.DEACTIVATE_IMMEDIATE_RESUME
assert et.get_editor_property("update_frequency") == U.NiagaraScalabilityUpdateFrequency.MEDIUM, "spawn-only would never resume"
st = et.get_editor_property("system_scalability_settings").settings[0]
assert st.cull_by_distance and st.max_distance == W.CONFIG["effect_type_cull_distance"]
W.apply_fixes([fx["NS_Rain"]])
assert NS_rain.get_editor_property("effect_type") is et and len(U._AssetTools.created) == 1, "the asset is reused"
W.revert_issues([fx["NS_Snow"], fx["NS_Rain"]])
assert NS_snow.get_editor_property("effect_type") is None and NS_rain.get_editor_property("effect_type") is None
# an Effect Type that can't be configured is never left behind
W.CONFIG["generated_asset_folder"] = "/Game/PerfAudit2"
saved = U.NiagaraCullReaction
U.NiagaraCullReaction = None
fx2 = [i for i in W.scan() if i.check == "vfx_no_effect_type"][0]
W.apply_fixes([fx2])
assert fx2.status == "failed" and U.EditorAssetLibrary.deleted == ["/Game/PerfAudit2/ET_PerfAudit_DistanceCull"], fx2.message
U.NiagaraCullReaction = saved
W.CONFIG["generated_asset_folder"] = "../Engine"
fx3 = [i for i in W.scan() if i.check == "vfx_no_effect_type"][0]
W.apply_fixes([fx3])
assert fx3.status == "failed" and "under /Game" in fx3.message, fx3.message
W.CONFIG["generated_asset_folder"] = "/Game/PerfAudit"
print("effect type create/assign/revert: OK")

# --- Lumen: dense foliage out of the distance-field scene --------------------------------------------------------
issues = W.scan()
lum = [i for i in issues if i.check == "lumen_foliage_df"][0]
W.apply_fixes([lum])
assert fc.get_editor_property("affect_distance_field_lighting") is False
assert ft.get_editor_property("affect_distance_field_lighting") is False, "the Foliage Type too, so it sticks"
assert "1 Foliage Type" in lum.message, lum.message
W.revert_issues([lum])
assert fc.get_editor_property("affect_distance_field_lighting") is True
assert ft.get_editor_property("affect_distance_field_lighting") is True
U.SystemLibrary.CVARS["r.DynamicGlobalIlluminationMethod"] = 0
assert not [i for i in W.scan() if i.check == "lumen_foliage_df"], "only when Lumen GI is on"
U.SystemLibrary.CVARS["r.DynamicGlobalIlluminationMethod"] = 1
print("lumen foliage: OK")

# --- distance field resolution: journal kind 'dfscale' ------------------------------------------------------------
df = [i for i in W.scan() if i.check == "mesh_df_resolution"]
assert len(df) == 1 and df[0].obj == "SM_Statue_Scan" and df[0].severity == W.MEDIUM
W.apply_fixes(df)
assert SM_statue.df_scale == 1.0 and df[0].journal["changes"][0]["k"] == "dfscale"
W.revert_issues(df)
assert SM_statue.df_scale == 8.0
print("distance field resolution: OK")

# --- texture streaming pool: grouped with the texture fixes ------------------------------------------------------
issues = W.scan()
pool = [i for i in issues if i.check == "tex_streaming_pool"][0]
assert {c.check for c in pool.children} == {"tex_oversized", "tex_never_stream"}, [c.check for c in pool.children]
assert "T_Cliff_8K" in pool.detail
W.apply_fixes([pool])
assert T8K.get_editor_property("max_texture_size") == 4096 and not T_ns.get_editor_property("never_stream")
assert pool.status == "fixed"
W.revert_issues([pool])
assert T8K.get_editor_property("max_texture_size") == 0 and T_ns.get_editor_property("never_stream")
U.SystemLibrary.CVARS["r.Streaming.PoolSize"] = 4000
assert not [i for i in W.scan() if i.check == "tex_streaming_pool"]
print("texture pool: OK")

# --- CPU findings + render-thread drivers + MegaLights --------------------------------------------------------------
W.scan()
cols = {"FrameTime": 30.0, "GameThreadTime": 29.0, "RenderThreadTime": 14.0, "GPUTime": 12.0, "GPU/Lights": 4.0,
        "Exclusive/GameThread/Animation": 6.0, "Exclusive/GameThread/EventWait": 9.0, "Exclusive/GameThread/Physics": 2.5,
        "Exclusive/RenderThread/InitViews": 5.0, "Exclusive/RenderThread/ShadowSetup": 0.5}
W.CONFIG["megalights_lights"] = 5
res = {"frames": 120, "means": cols, "path": "x.csv", "time": "12:00:00"}
gi = W.gpu_profile_issues(res, W._STATE["issues"])
cpu = {i.title.split(":")[0]: i for i in gi if i.check == "cpu_item"}
print("cpu findings:", sorted(cpu))
assert "Game thread - Animation" in cpu and "Render thread - Visibility & culling" in cpu
assert not [t for t in cpu if "EventWait" in t], "waiting is not work"
assert not [t for t in cpu if "Shadow setup" in t], "below cpu_item_min_ms"
anim = cpu["Game thread - Animation"]
assert anim.fix and {c.check for c in anim.children} <= {"anim_offscreen_tick", "anim_uro", "anim_skel_lods"}
frame = [i for i in gi if i.check == "gpu_frame"][0]
assert frame.title.startswith("Game thread-bound")
rt = [i for i in gi if i.check == "rt_drivers"][0]
assert "Shadow-casting dynamic lights" in rt.detail and rt.fix
dl = [i for i in gi if i.title.startswith("Direct lighting")][0]
assert "MegaLights" in dl.solution
print("cpu / render thread / megalights: OK")

# --- journal: the new change kinds are allowlisted and validated ---------------------------------------------------
bad = [
    {"k": "scal", "name": "r.VolumetricFog.GridPixelSize", "sections": [["SystemSettings", None]], "old": None},
    {"k": "scal", "name": "r.VolumetricFog.GridPixelSize", "sections": [["EffectsQuality@0", None]], "old": None},
    {"k": "scal", "name": "r.Evil", "sections": [["ShadowQuality@0", None]], "old": None},
    {"k": "scal", "name": "r.VolumetricFog.GridPixelSize", "sections": [["ShadowQuality@0", "1\n[X]"]], "old": None},
    {"k": "scal", "name": "r.VolumetricFog.GridPixelSize", "sections": [["ShadowQuality@0", None]], "old": "1;quit"},
    {"k": "scal", "name": "r.VolumetricFog.GridPixelSize", "sections": "ShadowQuality@0", "old": None},
    {"k": "dfscale", "path": SM_statue.get_path_name(), "old": "8"},
    {"k": "dfscale", "path": SM_statue.get_path_name(), "old": 1e9},
    {"k": "prop", "path": NS_snow.get_path_name(), "prop": "effect_type", "old": {"t": "py", "v": "x"}},
]
before_cmds = list(U.SystemLibrary.commands)
errs = W._revert_changes(bad)
assert len(errs) == len(bad), errs
assert U.SystemLibrary.commands == before_cmds and SM_statue.df_scale == 8.0
assert not os.path.exists(os.path.join(U._TMP, "Config", "DefaultScalability.ini")) or \
    "X]" not in open(os.path.join(U._TMP, "Config", "DefaultScalability.ini")).read()
for ini in ("DefaultGame.ini", "DefaultInput.ini", "../DefaultScalability.ini"):
    try:
        W._set_project_ini("ShadowQuality@0", "r.X", "1", ini)
        raise AssertionError("wrote " + ini)
    except RuntimeError:
        pass
for cmd in ("HighResShot 1280x720 | quit", "HighResShot filename=x", "HighResShot 1280x720 showui", "csvprofile stop now"):
    try:
        W._run_console(cmd)
        raise AssertionError("accepted %r" % cmd)
    except RuntimeError:
        pass
W._run_console("HighResShot 1280x720")
W._run_console("csvprofile stop")
print("journal / console allowlists: OK")
print("NEW CHECKS OK")
