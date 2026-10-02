"""Demo level built from the mock unreal module: one example of every problem the tool checks."""
import unreal as U  # noqa: E402  (mock)

# ------------------------------------------------------------------ build scene
def mat(name, **kw):
    m = U.Material(name)
    for k, v in kw.items():
        if k in ("wpo", "ps", "textures"):
            setattr(m, k, v)
        else:
            m._p[k] = v
    return m


def tex(name, w, h, **kw):
    t = U.Texture2D(name, **kw)
    t.w, t.h = w, h
    return t


T8K = tex("T_Cliff_8K", 8192, 8192)
T_ns = tex("T_NeverStream", 2048, 2048, never_stream=True)
T_nm = tex("T_NoMips", 1024, 1024, mip_gen_settings=U.TextureMipGenSettings.TMGS_NO_MIPMAPS)
T_hdr = tex("T_HDRI", 4096, 2048, compression_settings=U.TextureCompressionSettings.TC_HDR, max_texture_size=2048)
T_npot = tex("T_NPOT", 1000, 600)

M_rock = mat("M_Rock", ps=820, textures=(T8K, T_ns, T_nm))
M_sky = mat("M_Sky", textures=(T_hdr, T_npot))
M_foliage = mat("M_Foliage", wpo=True, blend_mode=U.BlendMode.BLEND_MASKED)
M_snow = mat("M_Snow", blend_mode=U.BlendMode.BLEND_TRANSLUCENT,
             translucency_lighting_mode=U.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING, ps=320)
M_glass = mat("M_Glass", blend_mode=U.BlendMode.BLEND_TRANSLUCENT)
M_engine = U.Material("M_EngineDefault", path="/Engine/EngineMaterials/M_EngineDefault")
MI_rock = U.MaterialInstanceConstant("MI_Rock_01")
MI_rock.parent = M_rock


def mesh(name, tris, lods=1, mats=(), nanite=False, ctas=False):
    m = U.StaticMesh(name, static_materials=[U.StaticMaterial(material_interface=x) for x in mats],
                     nanite_settings=U.MeshNaniteSettings(enabled=nanite),
                     body_setup=U.BodySetup("BodySetup", collision_trace_flag=(
                         U.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if ctas else U.CollisionTraceFlag.CTF_USE_DEFAULT)))
    m.tris, m.lods = tris, lods
    return m


SM_statue = mesh("SM_Statue_Scan", 1200000, mats=[MI_rock], ctas=True)
SM_glass = mesh("SM_GlassDome", 90000, mats=[M_glass])
SM_crate = mesh("SM_Crate", 12000, mats=[M_rock])
SM_tree = mesh("SM_Tree", 30000, lods=4, mats=[M_foliage], nanite=True)
SM_pebble = mesh("SM_Pebble", 200, lods=1, mats=[M_rock])
SM_grass = mesh("SM_Grass", 300, lods=3, mats=[M_foliage])
SM_debris = mesh("SM_Debris_Chunk", 4000, mats=[M_snow])
SM_engine = mesh("SM_EngineCube", 60000, mats=[M_engine])
SM_engine._path = "/Engine/BasicShapes/SM_EngineCube"

actors = []


def add(a):
    actors.append(a)
    return a


def sma(label, m, **kw):
    a = add(U.StaticMeshActor(label, m, **kw))
    c = a.comps[0]
    c.mats = tuple(x.material_interface for x in m.static_materials)
    return a


s = sma("Statue", SM_statue)
sma("GlassDome", SM_glass)
sma("EngineCube", SM_engine)
sky = sma("SkySphere", mesh("SM_SkySphere", 2000, lods=2, mats=[M_sky]))
sky.comps[0].radius = 1e6
for i in range(12):
    sma("Crate%d" % i, SM_crate, loc=U.Vector(i * 300, 0, 0))
# stacked duplicate
d1 = sma("Crate_Dup_A", SM_crate, loc=U.Vector(5000, 5000, 0))
d2 = sma("Crate_Dup_B", SM_crate, loc=U.Vector(5000, 5000, 0))
for i in range(45):
    a = sma("Pebble%d" % i, SM_pebble, loc=U.Vector(i * 50, 900, 0))
    a.comps[0].radius = 8.0
    a.comps[0].overlap = True
for i in range(8):
    a = sma("MovableProp%d" % i, SM_crate, loc=U.Vector(i * 100, -900, 0))
    a.comps[0]._p["mobility"] = U.ComponentMobility.MOVABLE
for i in range(20):
    a = sma("Tree%d" % i, SM_tree, loc=U.Vector(i * 700, 3000, 0))
    a.comps[0].mats = (M_foliage,)

fol = add(U.Actor("InstancedFoliageActor"))
fc = fol.add(U.FoliageInstancedStaticMeshComponent("FoliageGrass", static_mesh=SM_grass))
fc.count, fc.mats = 50000, (M_foliage,)
ft = U.FoliageType_InstancedStaticMesh("FT_Grass", mesh=SM_grass, cull_distance=U.Int32Interval(min=0, max=0))

# lights
lights = add(U.Actor("Lights"))
big = lights.add(U.PointLightComponent("BigPointLight", attenuation_radius=16000.0))
for i in range(15):
    l = lights.add(U.PointLightComponent("Fill%d" % i, attenuation_radius=800.0, cast_volumetric_shadow=(i < 5)))
    l.loc = U.Vector(i * 100, 0, 0)
lights.add(U.PointLightComponent("LF_Light", light_function_material=M_rock, attenuation_radius=500.0))
for i in range(6):
    l = lights.add(U.PointLightComponent("Stationary%d" % i, mobility=U.ComponentMobility.STATIONARY,
                                         attenuation_radius=1000.0))
    l.loc = U.Vector(i * 50, 0, 0)
lights.add(U.DirectionalLightComponent("Sun", mobility=U.ComponentMobility.STATIONARY))
lights.add(U.DirectionalLightComponent("Sun_Old"))
lights.add(U.SkyLightComponent("SkyLight", real_time_capture=True))
add(U.Actor("Fog")).add(U.ExponentialHeightFogComponent("Fog", enable_volumetric_fog=True))

# niagara
NS_snow = U.NiagaraSystem("NS_Snow")
em = U.NiagaraEmitter("Snowflakes", outer=NS_snow)
U.NiagaraSpriteRendererProperties("SpriteRenderer", outer=em, material=M_snow,
                                  motion_vector_setting=U.NiagaraRendererMotionVectorSetting.DISABLE)
U.NiagaraLightRendererProperties("LightRenderer", outer=em)
em2 = U.NiagaraEmitter("Debris", outer=NS_snow)
U.NiagaraMeshRendererProperties("MeshRenderer", outer=em2,
                                meshes=[U.NiagaraMeshRendererMeshProperties(mesh=SM_debris)])
for i in range(9):
    e = U.NiagaraEmitter("Extra%d" % i, outer=NS_snow)
    U.NiagaraRibbonRendererProperties("Ribbon", outer=e, material=M_glass)
fx = add(U.Actor("FX_Snow"))
nc = fx.add(U.NiagaraComponent("Niagara", asset=NS_snow))
cas = add(U.Actor("OldSparks")).add(U.ParticleSystemComponent("PSC", template=U.Object("P_Sparks")))

# skeletal
SK_npc = U.SkeletalMesh("SK_Crowd")
SK_npc.verts = 60000
for i in range(4):
    a = add(U.Actor("CrowdNPC%d" % i))
    a.add(U.SkeletalMeshComponent("Mesh", skeletal_mesh_asset=SK_npc, enable_update_rate_optimizations=False,
                                  visibility_based_anim_tick_option=(
                                      U.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES if i == 0
                                      else U.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE)))

# post process
ppv = add(U.PostProcessVolume("GlobalPPV", settings=U.PostProcessSettings(
    override_lumen_final_gather_quality=True, lumen_final_gather_quality=4.0,
    override_bloom_method=True, bloom_method=U.BloomMethod.BM_FFT,
    weighted_blendables=U.WeightedBlendables(array=[U.WeightedBlendable(weight=1.0, object=mat("PP_Outline"))]))))
cap = add(U.Actor("SecurityCam")).add(U.SceneCaptureComponent2D("Capture"))
add(U.Actor("Mirror")).add(U.PlanarReflectionComponent("Planar"))
dec = add(U.Actor("Decals"))
for i in range(6):
    dec.add(U.DecalComponent("Decal%d" % i, fade_screen_size=0.0, decal_material=M_rock))

U.EditorActorSubsystem.actors = actors
