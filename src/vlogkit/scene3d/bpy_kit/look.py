"""Materials, lights, world and render settings: the soft, toy-like look of the kit.

Runs inside Blender (imports bpy). Everything is procedural: no texture files, so a scene renders
the same on every machine.
"""

from __future__ import annotations

import contextlib

import bpy


def hex_rgba(color: str | tuple, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """'#e25b45' (sRGB) -> linear RGBA for Blender."""
    if isinstance(color, tuple):
        return (*color[:3], alpha) if len(color) == 3 else color
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    srgb = [int(c[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in srgb]
    return (*lin, alpha)


_MATS: dict[tuple, bpy.types.Material] = {}


def mat(
    color: str | tuple,
    rough: float = 0.55,
    metal: float = 0.0,
    sss: float = 0.0,
    emit: float = 0.0,
    spec: float = 0.35,
    name: str | None = None,
) -> bpy.types.Material:
    """A shared principled material per look (same args -> same material)."""
    key = (str(color), rough, metal, sss, emit, spec)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(name or f"m_{str(color).lstrip('#')}")
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    rgba = hex_rgba(color)
    p.inputs["Base Color"].default_value = rgba
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = spec
    if sss:
        p.inputs["Subsurface Weight"].default_value = sss
        p.inputs["Subsurface Radius"].default_value = (0.9, 0.45, 0.3)
        p.inputs["Subsurface Scale"].default_value = 0.04
    if emit:
        p.inputs["Emission Color"].default_value = rgba
        p.inputs["Emission Strength"].default_value = emit
    m.diffuse_color = rgba  # viewport / workbench
    _MATS[key] = m
    return m


def reset_cache() -> None:
    _MATS.clear()
    _PBR.clear()


def setup_render(
    width: int,
    height: int,
    fps: float,
    engine: str = "eevee",
    samples: int = 48,
    motion_blur: bool = True,
) -> None:
    sc = bpy.context.scene
    r = sc.render
    r.resolution_x, r.resolution_y, r.resolution_percentage = width, height, 100
    num = round(fps * 1000)
    r.fps, r.fps_base = (num // 1000, 1.0) if num % 1000 == 0 else (round(fps), round(fps) / fps)
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGB"
    r.image_settings.color_depth = "8"
    r.film_transparent = False
    r.use_motion_blur = motion_blur
    if hasattr(r, "motion_blur_shutter"):
        r.motion_blur_shutter = 0.35
    if engine == "cycles":
        r.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.device = "CPU"
        try:  # a GPU if there is one (Metal, CUDA, OptiX, HIP); CPU otherwise
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for kind in ("OPTIX", "CUDA", "METAL", "HIP", "ONEAPI"):
                try:
                    prefs.compute_device_type = kind
                except TypeError:
                    continue
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == kind
                    sc.cycles.device = "GPU"
                    break
        except (KeyError, AttributeError):
            pass
    elif engine == "workbench":
        r.engine = "BLENDER_WORKBENCH"
        sc.display.shading.light = "STUDIO"
        sc.display.shading.color_type = "MATERIAL"
    else:
        try:
            r.engine = "BLENDER_EEVEE"
        except TypeError:  # Blender 4.2-4.4 call it EEVEE Next
            r.engine = "BLENDER_EEVEE_NEXT"
        ee = sc.eevee
        ee.taa_render_samples = samples
        for attr, val in (
            ("use_shadows", True),
            ("use_raytracing", True),
            ("ray_tracing_method", "SCREEN"),
            ("fast_gi_method", "GLOBAL_ILLUMINATION"),
            ("use_fast_gi", True),
            ("shadow_ray_count", 2),
            ("shadow_step_count", 8),
            ("volumetric_tile_size", "4"),
        ):
            if hasattr(ee, attr):
                with contextlib.suppress(TypeError, ValueError):
                    setattr(ee, attr, val)
    vs = sc.view_settings
    try:
        vs.view_transform = "AgX"
        vs.look = "AgX - Punchy"
    except TypeError:
        vs.view_transform = "Filmic"
    vs.exposure = 0.0


HDRI_DIR: str = ""  # folder of the library's .hdr skies (set by the runner)
HDRIS = {  # set kind -> sky file
    "outdoor": "kloofendal_48d_partly_cloudy_puresky_2k.hdr",
    "dusk": "qwantani_dusk_2_puresky_2k.hdr",
    "interior": "brown_photostudio_02_2k.hdr",
    "studio": "studio_small_09_2k.hdr",
    "attic": "pine_attic_2k.hdr",
}


def env(kind: str, strength: float = 1.0, rotation: float = 0.0, visible: bool = True) -> bool:
    """Image-based light from a real sky (HDRI). False if the library has no such file."""
    import math
    import os

    f = HDRIS.get(kind)
    if not HDRI_DIR or not f or not os.path.exists(os.path.join(HDRI_DIR, f)):
        return False
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tex = nt.nodes.new("ShaderNodeTexEnvironment")
    tex.image = bpy.data.images.load(os.path.join(HDRI_DIR, f), check_existing=True)
    mapping = nt.nodes.new("ShaderNodeMapping")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping.inputs["Rotation"].default_value[2] = math.radians(rotation)
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    if visible:
        nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    else:  # lights the scene, but the camera sees a plain colour
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        plain = nt.nodes.new("ShaderNodeBackground")
        plain.inputs["Color"].default_value = (0.8, 0.85, 0.9, 1)
        nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
        nt.links.new(bg.outputs["Background"], mix.inputs[1])
        nt.links.new(plain.outputs["Background"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return True


def world(top: str = "#bfe3ff", bottom: str = "#fff4e6", strength: float = 1.0) -> None:
    """A soft gradient sky that also lights the scene (fills the shadows with color)."""
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    ramp.color_ramp.elements[0].color = hex_rgba(bottom)
    ramp.color_ramp.elements[1].color = hex_rgba(top)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[1].position = 0.45
    nt.links.new(coord.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def sun(
    energy: float = 3.2, angle_deg: float = 9.0, rot=(50, 8, 35), color="#fff1dc"
) -> bpy.types.Object:
    import math

    data = bpy.data.lights.new("sun", "SUN")
    data.energy = energy
    data.angle = math.radians(angle_deg)  # soft shadow edge
    data.color = hex_rgba(color)[:3]
    ob = bpy.data.objects.new("sun", data)
    ob.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.collection.objects.link(ob)
    return ob


def area(
    loc, target=(0, 0, 1), energy: float = 400, size: float = 4.0, color="#ffffff", name="area"
) -> bpy.types.Object:
    from mathutils import Vector

    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.color = hex_rgba(color)[:3]
    ob = bpy.data.objects.new(name, data)
    ob.location = loc
    d = Vector(target) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    bpy.context.collection.objects.link(ob)
    return ob


def point(
    loc, energy: float = 60, color="#ffd7a0", radius: float = 0.1, name="lamp"
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "POINT")
    data.energy = energy
    data.color = hex_rgba(color)[:3]
    data.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, data)
    ob.location = loc
    bpy.context.collection.objects.link(ob)
    return ob


TEX_DIR: str = ""  # folder of the library's PBR textures (Poly Haven, CC0), set by the runner
_PBR: dict[tuple, bpy.types.Material] = {}


def pbr(
    tex: str,
    tint: str | None = None,
    tile: float = 1.0,
    rough: float = 1.0,
    fallback: str = "#cccccc",
) -> bpy.types.Material:
    """A real surface (colour, normal and roughness maps) projected from the object's own
    coordinates (box mapping: no UVs needed), `tile` metres per repeat, tinted if asked.
    Without the library it falls back to a flat colour."""
    import os

    key = (tex, tint, tile, rough)
    if key in _PBR:
        return _PBR[key]
    diff = os.path.join(TEX_DIR, f"{tex}_diff.jpg") if TEX_DIR else ""
    if not diff or not os.path.exists(diff):
        return mat(tint or fallback, rough=0.6)
    m = bpy.data.materials.new(f"pbr_{tex}")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1 / tile)
    nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])

    def img(suffix: str, color: bool):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(
            os.path.join(TEX_DIR, f"{tex}_{suffix}.jpg"), check_existing=True
        )
        if not color:
            n.image.colorspace_settings.name = "Non-Color"
        n.projection = "BOX"
        n.projection_blend = 0.25
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n

    d = img("diff", True)
    if tint:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
        mix.inputs["Factor"].default_value = 1.0
        nt.links.new(d.outputs["Color"], mix.inputs[6])
        mix.inputs[7].default_value = hex_rgba(tint)
        nt.links.new(mix.outputs[2], p.inputs["Base Color"])
    else:
        nt.links.new(d.outputs["Color"], p.inputs["Base Color"])
    if os.path.exists(os.path.join(TEX_DIR, f"{tex}_rough.jpg")):
        r = img("rough", False)
        mathn = nt.nodes.new("ShaderNodeMath")
        mathn.operation = "MULTIPLY"
        mathn.inputs[1].default_value = rough
        nt.links.new(r.outputs["Color"], mathn.inputs[0])
        nt.links.new(mathn.outputs[0], p.inputs["Roughness"])
    if os.path.exists(os.path.join(TEX_DIR, f"{tex}_nor.jpg")):
        n = img("nor", False)
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.inputs["Strength"].default_value = 0.8
        nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], p.inputs["Normal"])
    m.diffuse_color = hex_rgba(tint or fallback)
    _PBR[key] = m
    return m
