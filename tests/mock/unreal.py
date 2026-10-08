"""Minimal fake of the Unreal Python API used by the tests (not a real engine binding)."""
import os
import tempfile

_LOG = []
SET_CALLS = []


def log(m): _LOG.append(("log", m)); print("LOG:", m[:200])
def log_warning(m): _LOG.append(("warn", m)); print("WARN:", m[:2000])
def log_error(m): _LOG.append(("err", m)); print("ERR:", m)


# ---------------------------------------------------------------- enums
class _EnumVal(object):
    def __init__(self, cls, name, value):
        self._cls, self.name, self.value = cls, name, value

    def __repr__(self):
        return "<%s.%s: %d>" % (self._cls, self.name, self.value)

    def __eq__(self, o):
        return isinstance(o, _EnumVal) and o._cls == self._cls and o.name == self.name

    def __hash__(self):
        return hash((self._cls, self.name))


def _enum(name, *members):
    cls = type(name, (_EnumVal,), {})
    for i, m in enumerate(members):
        setattr(cls, m, cls(name, m, i))
    return cls


BlendMode = _enum("BlendMode", "BLEND_OPAQUE", "BLEND_MASKED", "BLEND_TRANSLUCENT", "BLEND_ADDITIVE")
ComponentMobility = _enum("ComponentMobility", "STATIC", "STATIONARY", "MOVABLE")
AttachmentRule = _enum("AttachmentRule", "KEEP_RELATIVE", "KEEP_WORLD", "SNAP_TO_TARGET")
DetachmentRule = _enum("DetachmentRule", "KEEP_RELATIVE", "KEEP_WORLD")
NiagaraRendererMotionVectorSetting = _enum("NiagaraRendererMotionVectorSetting", "AUTO_DETECT", "PRECISE", "APPROXIMATE", "DISABLE")
MaterialProperty = _enum("MaterialProperty", "MP_WORLD_POSITION_OFFSET", "MP_BASE_COLOR", "MP_OPACITY",
                         "MP_EMISSIVE_COLOR", "MP_ROUGHNESS")
TranslucencyLightingMode = _enum("TranslucencyLightingMode", "TLM_VOLUMETRIC_NON_DIRECTIONAL", "TLM_VOLUMETRIC_PER_VERTEX_DIRECTIONAL", "TLM_SURFACE_PER_PIXEL_LIGHTING")
MaterialShadingModel = _enum("MaterialShadingModel", "MSM_UNLIT", "MSM_DEFAULT_LIT")
TextureMipGenSettings = _enum("TextureMipGenSettings", "TMGS_FROM_TEXTURE_GROUP", "TMGS_NO_MIPMAPS")
TextureCompressionSettings = _enum("TextureCompressionSettings", "TC_DEFAULT", "TC_HDR", "TC_HDR_COMPRESSED", "TC_VECTOR_DISPLACEMENTMAP")
TextureGroup = _enum("TextureGroup", "TEXTUREGROUP_WORLD", "TEXTUREGROUP_UI")
TexturePowerOfTwoSetting = _enum("TexturePowerOfTwoSetting", "NONE", "PAD_TO_POWER_OF_TWO", "STRETCH_TO_POWER_OF_TWO")
CollisionTraceFlag = _enum("CollisionTraceFlag", "CTF_USE_DEFAULT", "CTF_USE_SIMPLE_AS_COMPLEX", "CTF_USE_COMPLEX_AS_SIMPLE")
CollisionEnabled = _enum("CollisionEnabled", "NO_COLLISION", "QUERY_AND_PHYSICS")
VisibilityBasedAnimTickOption = _enum("VisibilityBasedAnimTickOption", "ALWAYS_TICK_POSE_AND_REFRESH_BONES", "ALWAYS_TICK_POSE", "ONLY_TICK_MONTAGES_WHEN_NOT_RENDERED", "ONLY_TICK_POSE_WHEN_RENDERED")
BloomMethod = _enum("BloomMethod", "BM_SOG", "BM_FFT")
AppMsgType = _enum("AppMsgType", "OK", "YES_NO", "YES_NO_CANCEL")
AppReturnType = _enum("AppReturnType", "NO", "YES", "CANCEL")
ShadowCacheInvalidationBehavior = _enum("ShadowCacheInvalidationBehavior", "AUTO", "ALWAYS", "RIGID", "STATIC")
NiagaraScalabilityUpdateFrequency = _enum("NiagaraScalabilityUpdateFrequency", "SPAWN_ONLY", "LOW", "MEDIUM", "HIGH", "CONTINUOUS")
NiagaraCullReaction = _enum("NiagaraCullReaction", "DEACTIVATE", "DEACTIVATE_IMMEDIATE", "DEACTIVATE_RESUME", "DEACTIVATE_IMMEDIATE_RESUME")


class PropertyAccessChangeNotifyMode:
    DEFAULT, NEVER, ALWAYS = 0, 1, 2


# ---------------------------------------------------------------- objects
_ALL = []


class Vector(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class Rotator(object):
    def __init__(self, pitch=0.0, yaw=0.0, roll=0.0):
        self.pitch, self.yaw, self.roll = pitch, yaw, roll


class _Class(object):
    def __init__(self, n): self.n = n
    def get_name(self): return self.n


class _Struct(object):
    _defaults = {}

    def __init__(self, **kw):
        self._p = dict(self._defaults)
        self._p.update(kw)

    def get_editor_property(self, n):
        if n not in self._p:
            raise AttributeError(n)
        return self._p[n]

    def set_editor_property(self, n, v, mode=None):
        self._p[n] = v

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self.get_editor_property(n)


class Object(object):
    _defaults = {}

    def __init__(self, name="Obj", outer=None, path=None, **props):
        self._name, self._outer, self._path = name, outer, path
        self._p = {}
        for klass in reversed(type(self).__mro__):
            self._p.update(getattr(klass, "_defaults", {}))
        self._p.update(props)
        self.modified = 0
        _ALL.append(self)

    def get_name(self): return self._name
    def get_fname(self): return self._name
    def get_class(self): return _Class(type(self).__name__)
    def get_outer(self): return self._outer

    def get_outermost(self):
        o = self
        while o._outer is not None:
            o = o._outer
        return _Package(o._path or ("/Game/Mock/" + o._name))

    def get_path_name(self):
        if self._outer is not None:
            return self._outer.get_path_name() + ":" + self._name
        return (self._path or ("/Game/Mock/" + self._name)) + "." + self._name

    dirtied = 0
    def modify(self, always_mark_dirty=True):
        self.modified += 1
        self.dirtied += 1 if always_mark_dirty else 0

    def get_typed_outer(self, cls):
        o = self._outer
        while o is not None and not isinstance(o, cls):
            o = o._outer
        return o

    def get_editor_property(self, n):
        if n not in self._p:
            raise Exception("no property %s on %s" % (n, type(self).__name__))
        return self._p[n]

    def set_editor_property(self, n, v, mode=None):
        if n not in self._p:
            raise Exception("no property %s on %s" % (n, type(self).__name__))
        SET_CALLS.append((self._name, n, v))
        self._p[n] = v


def _obj_getattr(self, n):
    if n.startswith("_"):
        raise AttributeError(n)
    p = self.__dict__.get("_p", {})
    if n in p:
        return p[n]
    raise AttributeError(n)


Object.__getattr__ = _obj_getattr


class _Package(object):
    def __init__(self, n): self.n = n
    def get_name(self): return self.n


class Actor(Object):
    _defaults = {"hidden": False, "tags": []}
    destroyed = False
    folder = ""
    hidden_in_game = False

    def __init__(self, label="Actor", loc=None, rot=None, scale=None, **kw):
        Object.__init__(self, label, **kw)
        self.label = label
        self.comps = []
        self.loc, self.rot, self.scale = loc or Vector(), rot or Rotator(), scale or Vector(1, 1, 1)

    def add(self, comp):
        comp._owner = self
        comp._outer = self
        self.comps.append(comp)
        return comp

    def get_actor_label(self): return self.label
    def set_actor_label(self, label): self.label = label
    def set_folder_path(self, p): self.folder = p
    def set_actor_hidden_in_game(self, b): self.hidden_in_game = b
    def get_components_by_class(self, cls): return [c for c in self.comps if isinstance(c, cls)]
    def get_component_by_class(self, cls): return next(iter(self.get_components_by_class(cls)), None)
    def get_actor_location(self): return self.loc
    def get_actor_rotation(self): return self.rot
    def get_actor_scale3d(self): return self.scale

    # --- attachment (like the engine: K2_AttachToActor / K2_DetachFromActor) ---
    _attach = None              # (parent actor, socket name)
    attach_log = []             # every successful attach: (child, parent, socket, location rule)

    def get_root_component(self): return self.comps[0] if self.comps else None
    root_component = property(get_root_component)
    def _default_attach_component(self): return self.get_root_component()   # not exposed to Python in UE
    def get_attach_parent_actor(self): return self._attach[0] if self._attach else None

    def attach_to_actor(self, parent, socket_name, location_rule, rotation_rule, scale_rule, weld_simulated_bodies):
        mine, theirs = self.get_root_component(), parent._default_attach_component()
        if mine is None or theirs is None:
            return False
        if (mine.get_editor_property("mobility") == ComponentMobility.STATIC
                and theirs.get_editor_property("mobility") != ComponentMobility.STATIC):
            log_warning("AttachTo: '%s' is not static , cannot attach '%s' which is static to it. Aborting."
                        % (theirs.get_name(), mine.get_name()))
            return False
        p = parent
        while p is not None:
            if p is self:
                log_warning("AttachTo: would form a cycle")
                return False
            p = p.get_attach_parent_actor()
        if location_rule == AttachmentRule.SNAP_TO_TARGET:
            self.loc = Vector(parent.loc.x, parent.loc.y, parent.loc.z)
        self._attach = (parent, str(socket_name or ""))
        Actor.attach_log.append((self, parent, str(socket_name or ""), location_rule))
        return True

    def detach_from_actor(self, location_rule=None, rotation_rule=None, scale_rule=None):
        self._attach = None

    _cac = None                 # the actor whose Child Actor Component spawned this one
    def is_child_actor(self): return self._cac is not None
    def get_parent_actor(self): return self._cac


class Pawn(Actor): pass


class CameraActor(Actor):
    """Like the engine: root is a SceneComponent, children attach to the CameraComponent (comps[1])."""
    def _default_attach_component(self): return self.comps[1] if len(self.comps) > 1 else self.get_root_component()


class Brush(Actor): pass
class Volume(Brush): pass
class LandscapeProxy(Actor): pass
class CullDistanceVolume(Actor): pass


class ActorComponent(Object):
    _defaults = {"hidden_in_game": False, "mobility": ComponentMobility.MOVABLE}
    _owner = None
    radius = 100.0
    loc = Vector()

    def get_owner(self): return self._owner
    def is_visible(self): return True
    def get_world_location(self): return self.loc
    sockets = ()
    def get_attach_parent(self):
        o = self._owner
        if o is not None and o._attach and o.get_root_component() is self:
            return o._attach[0]._default_attach_component()
        return None
    def get_attach_socket_name(self):
        o = self._owner
        return (o._attach[1] or "None") if (o is not None and o._attach and o.get_root_component() is self) else "None"
    def get_all_socket_names(self): return list(self.sockets)

    def set_relative_location_and_rotation(self, new_location, new_rotation, sweep, teleport):
        o = self._owner
        if o is not None and o._attach and o.get_root_component() is self:
            p = o._attach[0].loc
            o.loc = Vector(p.x + new_location.x, p.y + new_location.y, p.z + new_location.z)
        return None

    def get_children_components(self, include_all_descendants=True):
        """Like the engine: the owner's other components (under its root) + roots of actors attached to it."""
        o, out = self._owner, []
        if o is None or o.get_root_component() is not self:
            return out
        out += o.comps[1:]
        for a in EditorActorSubsystem.actors:
            r = a.get_root_component() if a._attach and a._attach[0] is o else None
            if r is not None:
                out.append(r)
                if include_all_descendants:
                    out += r.get_children_components(True)
        return out

    def set_mobility(self, m):
        self.set_editor_property("mobility", m)
        if m == ComponentMobility.MOVABLE:              # the engine spreads Movable down, without Modify()
            for c in self.get_children_components(False):
                c.set_editor_property("mobility", m)
                c.set_mobility(m)


class SceneComponent(ActorComponent): pass


class PrimitiveComponent(SceneComponent):
    _defaults = {"cast_shadow": True, "ld_max_draw_distance": 0.0, "affect_distance_field_lighting": True,
                 "shadow_cache_invalidation_behavior": ShadowCacheInvalidationBehavior.AUTO}
    mats = ()
    overlap = False
    def get_num_materials(self): return len(self.mats)
    def get_material(self, i): return self.mats[i]
    def set_cast_shadow(self, b): self.set_editor_property("cast_shadow", b)
    def set_cull_distance(self, d): self.set_editor_property("ld_max_draw_distance", d)
    def is_simulating_physics(self): return False
    def get_generate_overlap_events(self): return self.overlap
    def set_generate_overlap_events(self, b): self.overlap = b
    def get_collision_enabled(self): return CollisionEnabled.QUERY_AND_PHYSICS
    def set_material(self, i, m):
        self.__dict__.setdefault("override_materials", {})[i] = m


class MeshComponent(PrimitiveComponent): pass


class StaticMeshComponent(MeshComponent):
    instance_colors = None    # what Mesh Paint writes: (r, g, b, a) per asset vertex
    _defaults = {"static_mesh": None, "evaluate_world_position_offset": True,
                 "world_position_offset_disable_distance": 0}
    def set_world_position_offset_disable_distance(self, d):
        self.set_editor_property("world_position_offset_disable_distance", d)


class InstancedStaticMeshComponent(StaticMeshComponent):
    _defaults = {"instance_end_cull_distance": 0, "instance_start_cull_distance": 0}
    count = 0
    def get_instance_count(self): return self.count
    def set_cull_distances(self, s, e):
        self.set_editor_property("instance_start_cull_distance", s)
        self.set_editor_property("instance_end_cull_distance", e)


class HierarchicalInstancedStaticMeshComponent(InstancedStaticMeshComponent): pass
class FoliageInstancedStaticMeshComponent(HierarchicalInstancedStaticMeshComponent): pass


class SkinnedMeshComponent(MeshComponent): pass


class SkeletalMeshComponent(SkinnedMeshComponent):
    _defaults = {"visibility_based_anim_tick_option": VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE,
                 "enable_update_rate_optimizations": True, "skeletal_mesh_asset": None}
    def get_skeletal_mesh_asset(self): return self.get_editor_property("skeletal_mesh_asset")


class LightComponentBase(SceneComponent):
    _defaults = {"cast_shadows": True, "affects_world": True, "intensity": 5000.0, "cast_volumetric_shadow": False,
                 "volumetric_scattering_intensity": 1.0, "light_function_material": None, "contact_shadow_length": 0.0, "max_draw_distance": 0.0,
                 "max_distance_fade_range": 0.0}


class LightComponent(LightComponentBase): pass


class LocalLightComponent(LightComponent):
    _defaults = {"attenuation_radius": 1000.0}
    def set_attenuation_radius(self, r): self.set_editor_property("attenuation_radius", r)


class PointLightComponent(LocalLightComponent): pass


class DirectionalLightComponent(LightComponent):
    _defaults = {"dynamic_shadow_cascades": 3}


class SkyLightComponent(LightComponentBase):
    _defaults = {"real_time_capture": False}
    def recapture_sky(self): pass


class ExponentialHeightFogComponent(SceneComponent):
    _defaults = {"enable_volumetric_fog": False}


class SkyAtmosphereComponent(SceneComponent): pass
class VolumetricCloudComponent(SceneComponent): pass


class DecalComponent(PrimitiveComponent):
    _defaults = {"fade_screen_size": 0.01, "decal_material": None}


class SceneCaptureComponent(SceneComponent):
    _defaults = {"capture_every_frame": True}


class SceneCaptureComponent2D(SceneCaptureComponent): pass
class PlanarReflectionComponent(SceneCaptureComponent): pass


class ParticleSystemComponent(PrimitiveComponent):
    _defaults = {"template": None}


class NiagaraComponent(PrimitiveComponent):
    _defaults = {"asset": None}
    reinit = 0
    def get_asset(self): return self.get_editor_property("asset")
    def reinitialize_system(self): self.reinit += 1


class StaticMeshActor(Actor):
    def __init__(self, label, mesh, **kw):
        Actor.__init__(self, label, **kw)
        self.add(StaticMeshComponent("StaticMeshComponent0", static_mesh=mesh, mobility=ComponentMobility.STATIC))
        self._p["static_mesh_component"] = self.comps[0]


class PostProcessVolume(Actor):
    _defaults = {"enabled": True, "unbound": True, "settings": None}


# assets
class MaterialInterface(Object):
    def get_base_material(self): return self


class Material(MaterialInterface):
    _defaults = {"blend_mode": BlendMode.BLEND_OPAQUE, "output_translucent_velocity": False,
                 "translucency_lighting_mode": TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL,
                 "shading_model": MaterialShadingModel.MSM_DEFAULT_LIT}
    wpo = False
    ps = 150
    textures = ()


class MaterialInstance(MaterialInterface):
    _defaults = {"base_property_overrides": None}
    parent = None
    def get_base_material(self): return self.parent


class MaterialInstanceConstant(MaterialInstance): pass


class StaticMesh(Object):
    _defaults = {"static_materials": [], "body_setup": None}
    tris = 1000
    lods = 1
    geo = ([], [])          # (positions, triangles) for Geometry Script copies
    colors = None           # asset vertex colors (r, g, b, a) per vertex
    def set_material(self, i, m):
        self.__dict__.setdefault("materials", {})[i] = m
    def get_num_triangles(self, lod): return self.tris
    def get_num_lods(self): return self.lods


class SkeletalMesh(Object):
    lods = 1
    verts = 1000
    def get_lod_num(self): return self.lods


class Texture(Object): pass


class Texture2D(Texture):
    _defaults = {"never_stream": False, "mip_gen_settings": TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP,
                 "compression_settings": TextureCompressionSettings.TC_DEFAULT,
                 "lod_group": TextureGroup.TEXTUREGROUP_WORLD, "max_texture_size": 0,
                 "virtual_texture_streaming": False, "power_of_two_mode": TexturePowerOfTwoSetting.NONE}
    w = h = 1024
    def blueprint_get_size_x(self): return self.w
    def blueprint_get_size_y(self): return self.h


class NiagaraSystem(Object):
    _defaults = {"effect_type": None}


class NiagaraSystemScalabilitySettings(_Struct):
    _defaults = {"cull_by_distance": False, "max_distance": 0.0}


class NiagaraSystemScalabilitySettingsArray(_Struct):
    _defaults = {"settings": []}


_DEFAULT_CULL = NiagaraCullReaction.DEACTIVATE_IMMEDIATE


class NiagaraEffectType(Object):
    def __init__(self, *a, **kw):
        Object.__init__(self, *a, **kw)
        self._p.setdefault("update_frequency", NiagaraScalabilityUpdateFrequency.SPAWN_ONLY)
        self._p.setdefault("cull_reaction", _DEFAULT_CULL)
        self._p.setdefault("system_scalability_settings", NiagaraSystemScalabilitySettingsArray(
            settings=[NiagaraSystemScalabilitySettings()]))


class NiagaraEffectTypeFactoryNew(Object): pass


class NiagaraEmitter(Object): pass


class NiagaraRendererProperties(Object):
    _defaults = {"motion_vector_setting": NiagaraRendererMotionVectorSetting.AUTO_DETECT}


class NiagaraSpriteRendererProperties(NiagaraRendererProperties):
    _defaults = {"material": None}


class NiagaraMeshRendererProperties(NiagaraRendererProperties):
    _defaults = {"meshes": [], "override_materials": False}


class NiagaraRibbonRendererProperties(NiagaraRendererProperties):
    _defaults = {"material": None}


class NiagaraLightRendererProperties(NiagaraRendererProperties): pass


class FoliageType_InstancedStaticMesh(Object):
    _defaults = {"mesh": None, "cull_distance": None, "affect_distance_field_lighting": True}


# structs
class MeshNaniteSettings(_Struct):
    _defaults = {"enabled": False}


class MeshBuildSettings(_Struct):
    _defaults = {"distance_field_resolution_scale": 1.0}


class StaticMaterial(_Struct): pass
class BodySetup(Object):
    _defaults = {"collision_trace_flag": CollisionTraceFlag.CTF_USE_DEFAULT}


class NiagaraMeshRendererMeshProperties(_Struct): pass


class PostProcessSettings(_Struct):
    _defaults = {"override_lumen_final_gather_quality": False, "lumen_final_gather_quality": 1.0,
                 "override_bloom_method": False, "bloom_method": BloomMethod.BM_SOG,
                 "weighted_blendables": None}


class WeightedBlendables(_Struct): pass
class WeightedBlendable(_Struct): pass
class Int32Interval(_Struct): pass
class StaticMeshReductionOptions(_Struct): pass
class StaticMeshReductionSettings(_Struct): pass


class MaterialStatistics(_Struct): pass


# ---------------------------------------------------------------- libraries
class SystemLibrary(object):
    CVARS = {"r.Velocity.EnableVertexDeformation": 0, "r.VelocityOutputPass": 1, "r.Nanite.ProjectEnabled": 1,
             "r.Shadow.Virtual.Enable": 1, "r.AllowStaticLighting": 1, "sg.ShadowQuality": 3, "sg.EffectsQuality": 3,
             "r.DynamicGlobalIlluminationMethod": 1, "r.GenerateMeshDistanceFields": 1, "r.Streaming.PoolSize": 1000}
    commands = []

    @staticmethod
    def get_console_variable_int_value(n): return int(SystemLibrary.CVARS.get(n, 0))

    @staticmethod
    def get_console_variable_float_value(n): return float(SystemLibrary.CVARS.get(n, 0))

    @staticmethod
    def get_component_bounds(c): return (Vector(), Vector(), c.radius)

    @staticmethod
    def is_valid(obj): return obj is not None and not getattr(obj, "destroyed", False)

    CSV_TEXT = None
    pending_shots = []      # screenshots requested, written on the next tick (like the engine's next frame)

    @staticmethod
    def execute_console_command(w, cmd):
        SystemLibrary.commands.append(cmd)
        parts = cmd.split()
        if len(parts) == 2 and parts[0].lower().startswith("r."):
            try:
                SystemLibrary.CVARS[parts[0]] = float(parts[1])
            except ValueError:
                pass
        if cmd.startswith("HighResShot"):
            SystemLibrary.pending_shots.append(None)
        if cmd.lower().startswith("csvprofile frames") and SystemLibrary.CSV_TEXT:
            d = os.path.join(_TMP, "Saved", "Profiling", "CSV")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "Profile(20261002_153000).csv"), "w") as f:
                f.write(SystemLibrary.CSV_TEXT)


class MaterialEditingLibrary(object):
    recompiled = []
    connections = []

    @staticmethod
    def create_material_expression(mat, cls, x=0, y=0):
        e = cls(cls.__name__, outer=mat)
        mat.__dict__.setdefault("expressions", []).append(e)
        return e

    @staticmethod
    def connect_material_expressions(a, out, b, inp):
        MaterialEditingLibrary.connections.append((a, out, b, inp))
        return True

    @staticmethod
    def connect_material_property(e, out, prop):
        MaterialEditingLibrary.connections.append((e, out, prop))
        return True

    @staticmethod
    def get_material_property_input_node(m, prop): return object() if m.wpo else None

    @staticmethod
    def recompile_material(m): MaterialEditingLibrary.recompiled.append(m.get_name())

    @staticmethod
    def get_statistics(m):
        b = m.get_base_material()
        return MaterialStatistics(num_pixel_shader_instructions=b.ps, num_samplers=4)


class EditorAssetLibrary(object):
    synced = []
    deleted = []
    @staticmethod
    def sync_browser_to_objects(p): EditorAssetLibrary.synced.append(p)
    @staticmethod
    def does_asset_exist(p): return EditorAssetLibrary.load_asset(p) is not None
    @staticmethod
    def load_asset(p):
        for o in _ALL:
            if o._outer is None and o._path == p:
                return o
        return None
    @staticmethod
    def delete_asset(p):
        o = EditorAssetLibrary.load_asset(p)
        if o is not None:
            _ALL.remove(o)
            EditorAssetLibrary.deleted.append(p)
        return o is not None


class _AssetTools(object):
    created = []
    def create_asset(self, name, folder, cls, factory):
        o = cls(name, path=folder + "/" + name)
        _AssetTools.created.append(o)
        return o


class AssetToolsHelpers(object):
    @staticmethod
    def get_asset_tools(): return _AssetTools()


class AutomationLibrary(object):
    requested = []
    @staticmethod
    def take_high_res_screenshot(w, h, filename, *a, **k):
        AutomationLibrary.requested.append(filename)
        SystemLibrary.pending_shots.append(filename)
        return True


class _AD(object):
    def __init__(self, obj):
        self.obj = obj
        self.asset_class_path = _Struct(asset_name=type(obj).__name__)
    def get_asset(self): return self.obj


class _AR(object):
    def get_dependencies(self, pkg, opts):
        for o in _ALL:
            if isinstance(o, MaterialInterface) and o.get_outermost().get_name() == pkg:
                deps = [t.get_outermost().get_name() for t in getattr(o, "textures", ())]
                if isinstance(o, MaterialInstance) and o.parent:
                    deps.append(o.parent.get_outermost().get_name())
                return deps
        return []

    def get_assets_by_path(self, path, recursive=False):
        out = []
        for o in _ALL:
            if o._outer is None and not isinstance(o, (Actor, ActorComponent)) and o.get_outermost().get_name().startswith(path + "/"):
                ad = _AD(o)
                ad.asset_name = o.get_name()
                out.append(ad)
        return out

    def get_assets_by_package_name(self, pkg):
        return [_AD(o) for o in _ALL if o._outer is None and isinstance(o, (Texture, MaterialInterface))
                and o.get_outermost().get_name() == pkg]


class AssetRegistryHelpers(object):
    @staticmethod
    def get_asset_registry(): return _AR()


class AssetRegistryDependencyOptions(_Struct): pass


class ScopedSlowTask(object):
    def __init__(self, total, msg=""): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def make_dialog(self, b=False): pass
    def enter_progress_frame(self, n=1, msg=""): pass
    def should_cancel(self): return False


class ScopedEditorTransaction(ScopedSlowTask):
    titles = []
    def __init__(self, msg): ScopedEditorTransaction.titles.append(msg)


class EditorActorSubsystem(object):
    actors = []
    selected = []
    destroyed = []
    def get_all_level_actors(self): return list(self.actors)
    def get_selected_level_actors(self): return list(self.selected)
    def set_selected_level_actors(self, a): EditorActorSubsystem.selected = list(a)
    def destroy_actors(self, a):
        EditorActorSubsystem.destroyed += a
        for x in a:
            EditorActorSubsystem.actors.remove(x)
        return True

    def destroy_actor(self, a):
        a.destroyed = True
        if a in EditorActorSubsystem.actors:
            EditorActorSubsystem.actors.remove(a)
        EditorActorSubsystem.destroyed.append(a)
        return True

    def spawn_actor_from_object(self, obj, loc, rot=None):
        a = StaticMeshActor(obj.get_name(), obj, loc=Vector(loc.x, loc.y, loc.z))
        EditorActorSubsystem.actors.append(a)
        return a

    def spawn_actor_from_class(self, cls, loc, rot=None):
        a = cls(cls.__name__, loc=Vector(loc.x, loc.y, loc.z))
        EditorActorSubsystem.actors.append(a)
        return a


class _World(object):
    def get_name(self): return "L_MockLevel"


_THE_WORLD = _World()
EXTRA_WORLD_ACTORS = []     # actors only the raw world iterator sees (Level Instance contents, spawnables)


class UnrealEditorSubsystem(object):
    def get_editor_world(self): return _THE_WORLD


class GameplayStatics(object):
    @staticmethod
    def get_all_actors_of_class(world, cls):
        return [a for a in EditorActorSubsystem.actors + EXTRA_WORLD_ACTORS if isinstance(a, cls)]


class _Level(Object): pass


LOADED_LEVELS = []


class EditorLevelUtils(object):
    @staticmethod
    def get_levels(world): return list(LOADED_LEVELS)


class LevelStreaming(Object):
    loaded = None
    def get_loaded_level(self): return self.loaded
    def get_world_asset_package_name(self): return self._p.get("pkg", "")
    def get_outer(self): return _THE_WORLD


class StaticMeshEditorSubsystem(object):
    def get_lod_build_settings(self, mesh, lod):
        return MeshBuildSettings(distance_field_resolution_scale=getattr(mesh, "df_scale", 1.0))

    def set_lod_build_settings(self, mesh, lod, bs):
        mesh.df_scale = bs.distance_field_resolution_scale

    def set_nanite_settings(self, mesh, ns, apply):
        mesh._p["nanite_settings"] = MeshNaniteSettings(enabled=ns.enabled)

    def remove_lods(self, mesh):
        mesh.lods = 1
        return True

    def set_lods_with_notification(self, mesh, opts, apply):
        mesh.lods = len(opts.reduction_settings)
        return mesh.lods


class SkeletalMeshEditorSubsystem(object):
    def get_num_verts(self, skm, lod): return skm.verts
    def get_lod_count(self, skm): return skm.lods
    def regenerate_lod(self, skm, n, a, b):
        skm.lods = n
        return True


class AssetEditorSubsystem(object):
    def open_editor_for_assets(self, a): pass


class EditorLoadingAndSavingUtils(object):
    @staticmethod
    def save_dirty_packages_with_dialog(a, b): return True


_SUBS = {}


def get_editor_subsystem(cls):
    if cls not in _SUBS:
        _SUBS[cls] = cls()
    return _SUBS[cls]


_TMP = tempfile.mkdtemp(prefix="mockproj_")
os.makedirs(os.path.join(_TMP, "Config"))
os.makedirs(os.path.join(_TMP, "Saved"))
os.makedirs(os.path.join(_TMP, "Plugins"))
with open(os.path.join(_TMP, "Config", "DefaultEngine.ini"), "w") as f:
    f.write("[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Game/Map\n\n"
            "[/Script/Engine.RendererSettings]\nr.ReflectionMethod=1\nr.DynamicGlobalIlluminationMethod=1\n\n"
            "[/Script/Engine.Other]\nx=1\n")


os.makedirs(os.path.join(_TMP, "EngineConfig"))
with open(os.path.join(_TMP, "EngineConfig", "BaseScalability.ini"), "w") as f:      # excerpt of the engine's file
    f.write("[ShadowQuality@0]\nr.VolumetricFog=0\n\n[ShadowQuality@1]\nr.VolumetricFog.GridPixelSize=16\n"
            "r.VolumetricFog.GridSizeZ=64\n\n[ShadowQuality@2]\nr.VolumetricFog.GridPixelSize=8\n"
            "r.VolumetricFog.GridSizeZ=128\n\n[ShadowQuality@3]\nr.VolumetricFog.GridPixelSize=8\n"
            "r.VolumetricFog.GridSizeZ=128\n\n[EffectsQuality@0]\nr.SeparateTranslucencyScreenPercentage=100\n\n"
            "[EffectsQuality@3]\nr.SeparateTranslucencyScreenPercentage=100\n")


class Paths(object):
    @staticmethod
    def engine_config_dir(): return os.path.join(_TMP, "EngineConfig")
    @staticmethod
    def project_config_dir(): return os.path.join(_TMP, "Config")
    @staticmethod
    def project_saved_dir(): return os.path.join(_TMP, "Saved")
    @staticmethod
    def project_plugins_dir(): return os.path.join(_TMP, "Plugins")
    @staticmethod
    def convert_relative_path_to_full(p): return p
    @staticmethod
    def project_log_dir(): return os.path.join(_TMP, "Saved", "Logs")


def find_object(outer, path):
    for o in _ALL:
        if o.get_path_name() == path:
            return o
    return None


load_object = find_object


def ObjectIterator(cls):
    return [o for o in list(_ALL) if isinstance(o, cls)]


class EditorDialog(object):
    @staticmethod
    def show_message(*a, **k): return AppReturnType.NO


def get_interpreter_executable_path(): return "python"
def parent_external_window_to_slate(h): pass
TICKS = []


_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")
SHOT_COUNT = [0]


def flush_screenshots():
    """The engine writes requested screenshots a frame later: called from the test clock's ticks."""
    while SystemLibrary.pending_shots:
        name = SystemLibrary.pending_shots.pop(0)
        SHOT_COUNT[0] += 1
        d = os.path.join(_TMP, "Saved", "Screenshots", "WindowsEditor")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name or "HighresScreenshot%05d.png" % SHOT_COUNT[0]), "wb") as f:
            f.write(_PNG)


# ---------------------------------------------------------------- Sequencer
class MovieSceneSubTrack(Object): pass
class MovieSceneCinematicShotTrack(MovieSceneSubTrack): pass      # like the engine: a shot track IS a sub track
class MovieSceneCameraCutTrack(Object): pass


class _Section(Object):
    def __init__(self, name, start, end, sub=None):
        Object.__init__(self, name)
        self.start, self.end, self.sub = start, end, sub
    def get_start_frame(self): return self.start
    def get_end_frame(self): return self.end
    def get_shot_display_name(self): return self._name
    def get_sequence(self): return self.sub


class _Track(Object):
    def __init__(self, cls, sections):
        Object.__init__(self, cls.__name__)
        self.cls, self.sections = cls, sections
    def get_sections(self): return list(self.sections)


class _Binding(object):
    def __init__(self, template): self.template = template
    def get_object_template(self): return self.template


class LevelSequence(Object):
    def __init__(self, name, tracks=(), spawnables=(), start=0, end=0, **kw):
        Object.__init__(self, name, **kw)
        self.tracks, self.spawnables, self.start, self.end = list(tracks), list(spawnables), start, end
    def find_tracks_by_type(self, cls): return [t for t in self.tracks if issubclass(t.cls, cls)]   # subclasses too
    def get_spawnables(self): return [_Binding(t) for t in self.spawnables]
    def get_playback_start(self): return self.start
    def get_playback_end(self): return self.end


class LevelSequenceEditorBlueprintLibrary(object):
    current = None
    time = 0
    locked = False
    history = []
    @staticmethod
    def get_current_level_sequence(): return LevelSequenceEditorBlueprintLibrary.current
    @staticmethod
    def get_current_time(): return LevelSequenceEditorBlueprintLibrary.time
    @staticmethod
    def set_current_time(t):
        LevelSequenceEditorBlueprintLibrary.time = t
        LevelSequenceEditorBlueprintLibrary.history.append(t)
    @staticmethod
    def is_camera_cut_locked_to_viewport(): return LevelSequenceEditorBlueprintLibrary.locked
    @staticmethod
    def set_lock_camera_cut_to_viewport(b): LevelSequenceEditorBlueprintLibrary.locked = b
    @staticmethod
    def pause(): pass


def register_slate_post_tick_callback(fn):
    TICKS.append(fn)
    return len(TICKS)
def unregister_slate_post_tick_callback(h):
    TICKS[h - 1] = None


class WorldSettings(Actor): pass


# ---------------------------------------------------------------- Geometry Script (Snow Painter)
class Name(str): pass


class IntVector(object):
    def __init__(self, x=0, y=0, z=0): self.x, self.y, self.z = x, y, z


class Vector2D(object):
    def __init__(self, x=0.0, y=0.0): self.x, self.y = x, y


class LinearColor(object):
    def __init__(self, r=0.0, g=0.0, b=0.0, a=1.0): self.r, self.g, self.b, self.a = r, g, b, a


GeometryScriptOutcomePins = _enum("GeometryScriptOutcomePins", "FAILURE", "SUCCESS")
GeometryScriptLODType = _enum("GeometryScriptLODType", "MAX_AVAILABLE", "HI_RES_SOURCE_MODEL", "SOURCE_MODEL", "RENDER_DATA")


class GeometryScriptMeshReadLOD(_Struct):
    _defaults = {"lod_type": GeometryScriptLODType.MAX_AVAILABLE, "lod_index": 0}


class GeometryScriptCopyMeshFromComponentOptions(_Struct):
    _defaults = {"want_normals": True, "want_tangents": False, "want_instance_colors": False, "requested_lod": None}


class GeometryScriptSimpleMeshBuffers(_Struct):
    _defaults = {"vertices": [], "normals": [], "uv0": [], "vertex_colors": [], "triangles": [], "tri_group_i_ds": []}


class GeometryScriptSimplifyMeshOptions(_Struct): pass
class GeometryScriptUniqueAssetNameOptions(_Struct): pass


class GeometryScriptCreateNewStaticMeshAssetOptions(_Struct):
    _defaults = {"enable_nanite": False, "enable_collision": True}


class _GSList(object):
    def __init__(self, items): self.items = list(items)


class GeometryScriptVectorList(_GSList): pass
class GeometryScriptTriangleList(_GSList): pass
class GeometryScriptColorList(_GSList): pass


class DynamicMesh(Object):
    def __init__(self, *a, **kw):
        Object.__init__(self, "DynamicMesh")
        self.positions, self.tris, self.colors, self.normals, self.uvs = [], [], None, [], []

    def reset_mesh(self):
        self.positions, self.tris, self.colors, self.normals, self.uvs = [], [], None, [], []
        return self

    def get_triangle_count(self): return len(self.tris)


class DynamicMeshComponent(PrimitiveComponent):
    def __init__(self, *a, **kw):
        PrimitiveComponent.__init__(self, *a, **kw)
        self.mesh = DynamicMesh()
        self.updates = 0
    def get_dynamic_mesh(self): return self.mesh
    def notify_mesh_updated(self): self.updates += 1


class DynamicMeshActor(Actor):
    def __init__(self, label="DynamicMeshActor", **kw):
        Actor.__init__(self, label, **kw)
        comp = self.add(DynamicMeshComponent("DynamicMeshComponent"))
        self._p["dynamic_mesh_component"] = comp


class GeometryScript_List(object):
    @staticmethod
    def convert_vector_list_to_array(lst): return list(lst.items)
    @staticmethod
    def convert_triangle_list_to_array(lst): return list(lst.items)
    @staticmethod
    def convert_color_list_to_array(lst): return list(lst.items)


class GeometryScript_SceneUtils(object):
    copies = []

    @staticmethod
    def copy_mesh_from_component(comp, mesh, opts, to_world):
        sm = comp.get_editor_property("static_mesh")
        pos, tris = sm.geo
        lod = opts.requested_lod.lod_type if opts.requested_lod is not None else GeometryScriptLODType.MAX_AVAILABLE
        colors = list(sm.colors) if sm.colors else None
        if opts.want_instance_colors and lod == GeometryScriptLODType.RENDER_DATA and comp.instance_colors is not None:
            colors = list(comp.instance_colors)
        GeometryScript_SceneUtils.copies.append((comp, lod))
        o = comp.get_owner().loc if (to_world and comp.get_owner() is not None) else Vector()
        world = [(p[0] + o.x, p[1] + o.y, p[2] + o.z) for p in pos]
        if lod == GeometryScriptLODType.RENDER_DATA:      # render data: vertices split per triangle (seams)
            mesh.positions, mesh.tris, mc = [], [], []
            for t in tris:
                base = len(mesh.positions)
                for v in t:
                    mesh.positions.append(world[v])
                    if colors is not None:
                        mc.append(colors[v])
                mesh.tris.append((base, base + 1, base + 2))
            mesh.colors = mc if colors is not None else None
        else:
            mesh.positions, mesh.tris, mesh.colors = world, list(tris), colors
        return (mesh, object(), GeometryScriptOutcomePins.SUCCESS)


class EngineCrash(BaseException):
    """An engine assertion: the editor would close. BaseException, so the tool can't swallow it."""


class GeometryScript_MeshQueries(object):
    @staticmethod
    def get_num_uv_sets(mesh):
        return 1 if (mesh.uvs and len(mesh.uvs) == len(mesh.positions)) else 0

    @staticmethod
    def get_all_vertex_positions(mesh, skip_gaps=False):
        return (GeometryScriptVectorList([Vector(*p) for p in mesh.positions]), False)

    @staticmethod
    def get_all_triangle_indices(mesh, skip_gaps=False):
        return (GeometryScriptTriangleList([IntVector(*t) for t in mesh.tris]), False)


class GeometryScript_VertexColors(object):
    @staticmethod
    def get_mesh_per_vertex_colors(mesh, blend=True):
        cols = mesh.colors or []
        return (mesh, GeometryScriptColorList([LinearColor(*c) for c in cols]), mesh.colors is not None, False)


class GeometryScript_MeshEdits(object):
    @staticmethod
    def append_buffers_to_mesh(mesh, buf, material_id=0, defer=False):
        base = len(mesh.positions)
        mesh.positions += [(v.x, v.y, v.z) for v in buf.vertices]
        mesh.normals += [(v.x, v.y, v.z) for v in buf.normals]
        mesh.uvs += [(v.x, v.y) for v in buf.uv0]
        if buf.vertex_colors:
            mesh.colors = (mesh.colors or []) + [(c.r, c.g, c.b, c.a) for c in buf.vertex_colors]
        mesh.tris += [(t.x + base, t.y + base, t.z + base) for t in buf.triangles]
        return mesh


class GeometryScript_MeshSimplification(object):
    calls = []
    @staticmethod
    def apply_simplify_to_triangle_count(mesh, count, options=None):
        GeometryScript_MeshSimplification.calls.append(count)
        mesh.tris = mesh.tris[:count]
        return mesh


class GeometryScript_NewAssetUtils(object):
    @staticmethod
    def create_unique_new_asset_path_name(folder, base, opts=None):
        name, i = base, 0
        while EditorAssetLibrary.load_asset(folder + "/" + name) is not None:
            i += 1
            name = "%s_%d" % (base, i)
        return (folder + "/" + name, name, GeometryScriptOutcomePins.SUCCESS)

    @staticmethod
    def create_new_static_mesh_asset_from_mesh(mesh, path, opts):
        if not mesh.uvs or len(mesh.uvs) != len(mesh.positions):
            raise EngineCrash("Assertion failed: NumUVs > 0 [StaticMesh.cpp]")
        sm = StaticMesh(path.rsplit("/", 1)[1], path=path,
                        nanite_settings=MeshNaniteSettings(enabled=opts.enable_nanite))
        sm.geo = (list(mesh.positions), list(mesh.tris))
        sm.colors = list(mesh.colors) if mesh.colors else None
        sm._p["static_materials"] = [StaticMaterial(material_interface=None, material_slot_name="Slot0")]
        sm.collision = opts.enable_collision
        return (sm, GeometryScriptOutcomePins.SUCCESS)


class MaterialFactoryNew(Object): pass
class MaterialExpressionVertexColor(Object): pass


class MaterialExpressionMultiply(Object):
    _defaults = {"const_b": 1.0}


class MaterialExpressionAdd(Object):
    _defaults = {"const_b": 1.0}


class MaterialExpressionConstant3Vector(Object):
    _defaults = {"constant": None}


class MaterialExpressionConstant(Object):
    _defaults = {"r": 0.0}


class EditorUtilityLibrary(object):
    selected_assets = []
    @staticmethod
    def get_selected_assets(): return list(EditorUtilityLibrary.selected_assets)


class GeometryScript_UVs(object):
    @staticmethod
    def set_num_uv_sets(mesh, n):
        if n > 0 and not mesh.uvs:
            mesh.uvs = [(0.0, 0.0)] * len(mesh.positions)
        return mesh


# ---------------------------------------------------------------- Geometry Script spatial queries (vertical rays)
GeometryScriptSearchOutcomePins = _enum("GeometryScriptSearchOutcomePins", "FOUND", "NOT_FOUND")


class Box(object):
    def __init__(self, lo, hi): self.min, self.max = lo, hi


class GeometryScriptSpatialQueryOptions(_Struct):
    _defaults = {"max_distance": 0.0, "allow_unsafe_modified_queries": False, "winding_iso_threshold": 0.5}


class GeometryScriptRayHitResult(_Struct):
    _defaults = {"hit": False, "ray_parameter": 0.0, "hit_triangle_id": -1, "hit_position": None}


class GeometryScriptDynamicMeshBVH(object):
    """Buckets the triangles by XY cell: the tool only casts rays straight down."""
    CELL = 25.0

    def __init__(self, mesh):
        self.mesh, self.buckets = mesh, {}
        c = self.CELL
        for t, tri in enumerate(mesh.tris):
            ps = [mesh.positions[v] for v in tri]
            for i in range(int(min(p[0] for p in ps) // c), int(max(p[0] for p in ps) // c) + 1):
                for j in range(int(min(p[1] for p in ps) // c), int(max(p[1] for p in ps) // c) + 1):
                    self.buckets.setdefault((i, j), []).append(t)


class GeometryScript_MeshSpatial(object):
    rays = 0

    @staticmethod
    def build_bvh_for_mesh(mesh, debug=None):
        return (GeometryScriptDynamicMeshBVH(mesh),)

    @staticmethod
    def find_nearest_ray_intersection_with_mesh(mesh, bvh, origin, direction, options, debug=None):
        assert abs(direction.x) < 1e-9 and abs(direction.y) < 1e-9 and direction.z < 0, "mock: vertical rays only"
        GeometryScript_MeshSpatial.rays += 1
        x, y, best = origin.x, origin.y, None
        c = GeometryScriptDynamicMeshBVH.CELL
        for t in bvh.buckets.get((int(x // c), int(y // c)), []):
            (ax, ay, az), (bx, by, bz), (cx, cy, cz) = [mesh.positions[v] for v in mesh.tris[t]]
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-12:
                continue                                  # vertical triangle: a vertical ray can't hit it
            l1 = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / d
            l2 = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / d
            l3 = 1.0 - l1 - l2
            if min(l1, l2, l3) < -1e-9:
                continue
            z = l1 * az + l2 * bz + l3 * cz
            if z <= origin.z and (best is None or z > best):
                best = z
        hit = GeometryScriptRayHitResult()
        if best is None:
            return (hit, GeometryScriptSearchOutcomePins.NOT_FOUND)
        hit.set_editor_property("hit", True)
        hit.set_editor_property("ray_parameter", origin.z - best)
        hit.set_editor_property("hit_position", Vector(x, y, best))
        return (hit, GeometryScriptSearchOutcomePins.FOUND)


def _mesh_bbox(mesh):
    ps = mesh.positions
    return Box(Vector(min(p[0] for p in ps), min(p[1] for p in ps), min(p[2] for p in ps)),
               Vector(max(p[0] for p in ps), max(p[1] for p in ps), max(p[2] for p in ps)))


GeometryScript_MeshQueries.get_mesh_bounding_box = staticmethod(lambda mesh: (_mesh_bbox(mesh),))
