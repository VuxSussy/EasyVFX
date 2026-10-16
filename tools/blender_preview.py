"""Renders a tests/snapshot.luau capture in Blender (Cycles) as a Roblox-like preview.

    python blender_preview.py snap.json out_dir pack_textures_dir builtin_textures_dir
    (or: blender -b -P blender_preview.py -- <same args>)

Particles are re-simulated from the captured emitter settings (speed, drag,
acceleration, spread, lifetime, size/transparency/color sequences, rotation,
flipbooks, orientation modes) and drawn as additive quads; beams become
camera-facing ribbons along their Bezier curves; Neon parts glow; rocks are lit.

This approximates Roblox's renderer for eyeballing shapes and timing. Assumption:
for VelocityPerpendicular particles the texture's "up" is the emitter's -Z axis
(the plugin's Rotation slider exists to correct this in Studio if it differs).
"""

import json
import math
import os
import random
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
SNAP, OUT_DIR, PACK_DIR, BUILTIN_DIR = argv[:4]
CAMERA_OVERRIDE = None
if len(argv) > 4:  # "ex,ey,ez,tx,ty,tz"
    nums = [float(x) for x in argv[4].split(",")]
    CAMERA_OVERRIDE = (tuple(nums[:3]), tuple(nums[3:6]))
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 560, 380
CAMERAS = {
    "energy_blast": ((24, 9, -4), (0, 2, -13)),
    "slash": ((2, 12, 13), (0, 2, -3.5)),
    "multi_slash": ((2, 10, 14), (0, 2, -2)),
    "lightning": ((24, 15, 30), (0, 9, 0)),
    "level_up": ((18, 11, 24), (0, 6, 0)),
    "explosion": ((18, 12, 22), (0, 3, 0)),
}
DEFAULT_CAMERA = ((15, 11, 19), (0, 1.5, 0))

TEX_CACHE = {}
DIRS = {"Top": (0, 1, 0), "Bottom": (0, -1, 0), "Front": (0, 0, -1), "Back": (0, 0, 1), "Right": (1, 0, 0), "Left": (-1, 0, 0)}


# ------------------------------------------------------------------ math (Roblox Y-up)
def add(a, b):
    return [a[i] + b[i] for i in range(3)]


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def mul(a, s):
    return [x * s for x in a]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    m = math.sqrt(dot(a, a)) or 1.0
    return [x / m for x in a]


def rot_apply(cf, v):
    _, _, _, r00, r01, r02, r10, r11, r12, r20, r21, r22 = cf
    return [r00 * v[0] + r01 * v[1] + r02 * v[2], r10 * v[0] + r11 * v[1] + r12 * v[2], r20 * v[0] + r21 * v[1] + r22 * v[2]]


def rotate_about(v, axis, ang):
    axis = norm(axis)
    c, s = math.cos(ang), math.sin(ang)
    return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v) * (1 - c)))


def to_blender(p):
    # Roblox (x, y up, z) -> Blender (x, -z, y up)
    return (p[0], -p[2], p[1])


def seq_at(seq, t):
    if t <= seq[0][0]:
        return seq[0][1:] if len(seq[0]) > 2 else seq[0][1]
    for a, b in zip(seq, seq[1:]):
        if a[0] <= t <= b[0]:
            f = (t - a[0]) / max(1e-6, b[0] - a[0])
            if len(a) > 2:
                return [a[i] + (b[i] - a[i]) * f for i in range(1, len(a))]
            return a[1] + (b[1] - a[1]) * f
    last = seq[-1]
    return last[1:] if len(last) > 2 else last[1]


# ------------------------------------------------------------------ scene helpers
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    TEX_CACHE.clear()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(os.environ.get("PREVIEW_SAMPLES", "48"))
    sc.cycles.use_denoising = False
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("w")
    sc.world = world
    try:
        world.use_nodes = True
    except Exception:
        pass
    for n in world.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs[0].default_value = (0.004, 0.005, 0.008, 1)
            n.inputs[1].default_value = 1.0
    return sc


def texture_path(tex):
    if tex.startswith("pack://"):
        return os.path.join(PACK_DIR, tex[7:] + ".png")
    name = os.path.basename(tex)
    for cand in (name + ".png", name):
        p = os.path.join(BUILTIN_DIR, cand)
        if os.path.exists(p):
            return p
    return None


def particle_material(key, tex, additive):
    mkey = (key, tex, additive)
    if mkey in TEX_CACHE:
        return TEX_CACHE[mkey]
    m = bpy.data.materials.new(key)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    emit = nt.nodes.new("ShaderNodeEmission")
    transp = nt.nodes.new("ShaderNodeBsdfTransparent")
    alpha = nt.nodes.new("ShaderNodeMath")
    alpha.operation = "MULTIPLY"
    strength = nt.nodes.new("ShaderNodeAttribute")
    strength.attribute_name = "Strength"
    path = texture_path(tex) if tex else None
    if path:
        img = nt.nodes.new("ShaderNodeTexImage")
        img.image = bpy.data.images.load(path, check_existing=True)
        img.extension = "CLIP"
        nt.links.new(img.outputs["Alpha"], alpha.inputs[0])
        lum = nt.nodes.new("ShaderNodeMixRGB")
        lum.blend_type = "MULTIPLY"
        lum.inputs[0].default_value = 1.0
        nt.links.new(attr.outputs["Color"], lum.inputs[1])
        nt.links.new(img.outputs["Color"], lum.inputs[2])
        color_out = lum.outputs[0]
    else:
        alpha.inputs[0].default_value = 1.0
        color_out = attr.outputs["Color"]
    nt.links.new(attr.outputs["Alpha"], alpha.inputs[1])
    nt.links.new(color_out, emit.inputs["Color"])
    if additive:
        s = nt.nodes.new("ShaderNodeMath")
        s.operation = "MULTIPLY"
        nt.links.new(alpha.outputs[0], s.inputs[0])
        nt.links.new(strength.outputs["Fac"], s.inputs[1])
        nt.links.new(s.outputs[0], emit.inputs["Strength"])
        addsh = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(transp.outputs[0], addsh.inputs[0])
        nt.links.new(emit.outputs[0], addsh.inputs[1])
        nt.links.new(addsh.outputs[0], out.inputs["Surface"])
    else:
        nt.links.new(strength.outputs["Fac"], emit.inputs["Strength"])
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(alpha.outputs[0], mix.inputs["Fac"])
        nt.links.new(transp.outputs[0], mix.inputs[1])
        nt.links.new(emit.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    TEX_CACHE[mkey] = m
    return m


def quads_object(name, quads, material):
    """quads: list of (corners[4] roblox coords, uv[4], rgba, strength)."""
    if not quads:
        return
    verts, faces, uvs, cols, strengths = [], [], [], [], []
    for corners, uv, rgba, strength in quads:
        base = len(verts)
        for c in corners:
            verts.append(to_blender(c))
        faces.append((base, base + 1, base + 2, base + 3))
        uvs.extend(uv)
        cols.extend([rgba] * 4)
        strengths.extend([strength] * 4)
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    uvl = mesh.uv_layers.new(name="UVMap")
    col = mesh.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
    st = mesh.attributes.new("Strength", "FLOAT", "POINT")
    for i, c in enumerate(cols):
        col.data[i].color = c
        st.data[i].value = strengths[i]
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[mesh.loops[li].vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    obj.visible_shadow = False


# ------------------------------------------------------------------ simulation
def simulate_burst(b, cam_eye, cam_right, cam_up, rng):
    quads = []
    cfr = b["cframe"]
    origin = cfr[:3]
    base_dir = rot_apply(cfr, DIRS.get(b["direction"], (0, 1, 0)))
    local_x = rot_apply(cfr, (1, 0, 0))
    local_z = rot_apply(cfr, (0, 0, 1))
    grid = {"Grid2x2": 2, "Grid4x4": 4, "Grid8x8": 8}.get(b["flipbook"], 1)
    k = max(1e-4, b["drag"] * math.log(2))
    for _ in range(int(b["count"])):
        life = rng.uniform(*b["lifetime"])
        age = b["age"]
        if age > life or life <= 0:
            continue
        f = age / life
        start = list(origin)
        vol = b["volume"]
        if any(vol):
            off = [rng.uniform(-0.5, 0.5) * vol[i] for i in range(3)]
            start = add(origin, rot_apply(cfr, off))
        # spread around two axes perpendicular to the emission direction
        ref = local_x if abs(dot(local_x, base_dir)) < 0.9 else local_z
        ax1 = norm(cross(base_dir, ref))  # yaw-like axis
        ax2 = norm(cross(base_dir, ax1))
        d = rotate_about(base_dir, ax1, math.radians(rng.uniform(-b["spread"][1], b["spread"][1])))
        d = rotate_about(d, ax2, math.radians(rng.uniform(-b["spread"][0], b["spread"][0])))
        speed = rng.uniform(*b["speed"])
        decay = (1 - math.exp(-k * age)) / k if b["drag"] > 0 else age
        pos = add(add(start, mul(d, speed * decay)), mul(b["accel"], 0.5 * age * age))
        vel = add(mul(d, speed * math.exp(-k * age) if b["drag"] > 0 else speed), mul(b["accel"], age))
        size = seq_at(b["size"], f)
        squash = seq_at(b["squash"], f)
        tr = seq_at(b["transparency"], f)
        col = seq_at(b["color"], f)
        rot = math.radians(rng.uniform(*b["rotation"]) + rng.uniform(*b["rotSpeed"]) * age)
        if size <= 0.001 or tr >= 0.999:
            continue
        to_cam = norm(sub(cam_eye, pos))
        mode = b["orientation"]
        if mode == "VelocityPerpendicular":
            n = norm(vel) if dot(vel, vel) > 1e-8 else base_dir
            up = sub(mul(local_z, -1), mul(n, dot(mul(local_z, -1), n)))
            if dot(up, up) < 1e-6:
                up = sub(local_x, mul(n, dot(local_x, n)))
            up = norm(up)
            right = norm(cross(up, n))
            up, right = rotate_about(up, n, rot), rotate_about(right, n, rot)
        elif mode == "VelocityParallel":
            up = norm(vel) if dot(vel, vel) > 1e-8 else base_dir
            right = norm(cross(up, to_cam))
        else:
            right, up = cam_right, cam_up
            if mode == "FacingCameraWorldUp":
                up = [0, 1, 0]
                right = norm(cross(up, to_cam))
            else:
                axis = cross(right, up)
                right, up = rotate_about(right, axis, rot), rotate_about(up, axis, rot)
        sx = size * (1 / (1 + max(0.0, squash)) if squash >= 0 else 1 / (1 - squash * 0.5))
        sy = size * ((1 + max(0.0, squash)) if squash >= 0 else (1 - squash))
        if mode == "VelocityParallel":
            sx, sy = size / (1 + abs(squash) * 0.5), size * (1 + abs(squash))
        hx, hy = mul(right, sx / 2), mul(up, sy / 2)
        corners = [sub(sub(pos, hx), hy), sub(add(pos, hx), hy), add(add(pos, hx), hy), add(sub(pos, hx), hy)]
        frame = min(grid * grid - 1, int(f * grid * grid)) if grid > 1 else 0
        r, c = divmod(frame, grid)
        u0, u1 = c / grid, (c + 1) / grid
        v1, v0 = 1 - r / grid, 1 - (r + 1) / grid
        uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        rgba = (col[0], col[1], col[2], 1 - tr)
        strength = (b["brightness"] * 0.6 if b["lightEmission"] > 0 else 0.35) * (0.6 + 0.4 * b["lightEmission"])
        quads.append((corners, uv, rgba, strength))
    return quads


def bezier(p0, p1, p2, p3, t):
    a, bb, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t**3
    return [a * p0[i] + bb * p1[i] + c * p2[i] + d * p3[i] for i in range(3)]


def beam_quads(beam, cam_eye):
    p0, p3 = beam["p0"], beam["p3"]
    p1 = add(p0, mul(beam["a0"], beam["c0"]))
    p2 = sub(p3, mul(beam["a1"], beam["c1"]))
    n = 14
    pts = [bezier(p0, p1, p2, p3, i / n) for i in range(n + 1)]
    quads = []
    for i in range(n):
        a, b = pts[i], pts[i + 1]
        tdir = norm(sub(b, a))
        side_a = norm(cross(tdir, sub(cam_eye, a)))
        side_b = norm(cross(tdir, sub(cam_eye, b)))
        ta, tb = i / n, (i + 1) / n
        wa = (beam["w0"] + (beam["w1"] - beam["w0"]) * ta) / 2
        wb = (beam["w0"] + (beam["w1"] - beam["w0"]) * tb) / 2
        tr = (seq_at(beam["transparency"], ta) + seq_at(beam["transparency"], tb)) / 2
        col = seq_at(beam["color"], (ta + tb) / 2)
        corners = [sub(a, mul(side_a, wa)), sub(b, mul(side_b, wb)), add(b, mul(side_b, wb)), add(a, mul(side_a, wa))]
        quads.append((corners, [(0, 0), (1, 0), (1, 1), (0, 1)], (col[0], col[1], col[2], 1 - tr), beam["brightness"] * 0.7 * (0.4 + 0.6 * beam["light"])))
    return quads


def add_part(p, idx):
    cf = p["cframe"]
    size = p["size"]
    shape = p["shape"]
    loc = to_blender(cf[:3])
    if shape == "Ball":
        bpy.ops.mesh.primitive_uv_sphere_add(radius=min(size) / 2, location=loc, segments=24, ring_count=12)
    elif shape == "Cylinder":
        bpy.ops.mesh.primitive_cylinder_add(radius=min(size[1], size[2]) / 2, depth=size[0], location=loc)
    else:
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    if shape != "Ball":
        # build rotation from the Roblox matrix (columns = right, up, back)
        import mathutils

        r = cf[3:]
        right, up, back = (r[0], r[3], r[6]), (r[1], r[4], r[7]), (r[2], r[5], r[8])
        m = mathutils.Matrix((to_blender(right), to_blender(up), to_blender(back))).transposed()
        obj.rotation_euler = m.to_euler()
        if shape == "Cylinder":
            obj.rotation_euler.rotate_axis("Y", math.radians(90))
        else:
            obj.scale = (size[0], size[2], size[1])
    mat = bpy.data.materials.new("part%d" % idx)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if p["material"] in ("Neon", "ForceField"):
        emit = nt.nodes.new("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (*p["color"], 1)
        emit.inputs["Strength"].default_value = 1.3 * (1 - p["t"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        addsh = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(tr.outputs[0], addsh.inputs[0])
        nt.links.new(emit.outputs[0], addsh.inputs[1])
        nt.links.new(addsh.outputs[0], out.inputs["Surface"])
    else:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (*p["color"], 1)
        bsdf.inputs["Roughness"].default_value = 0.9
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    obj.data.materials.append(mat)
    obj.visible_shadow = False  # Roblox VFX pieces have CastShadow = false


def render_shot(shot, mode):
    sc = reset()
    eye, target = CAMERA_OVERRIDE or CAMERAS.get(shot["id"], DEFAULT_CAMERA)
    fwd = norm(sub(target, eye))
    cam_right = norm(cross(fwd, [0, 1, 0]))
    cam_up = cross(cam_right, fwd)
    # ground
    bpy.ops.mesh.primitive_plane_add(size=120, location=(0, 0, 0))
    g = bpy.context.object
    gm = bpy.data.materials.new("ground")
    gb = gm.node_tree.nodes.get("Principled BSDF") or gm.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    gb.inputs["Base Color"].default_value = (0.02, 0.022, 0.026, 1)
    gb.inputs["Roughness"].default_value = 1.0
    if not gm.node_tree.nodes.get("Material Output"):
        o = gm.node_tree.nodes.new("ShaderNodeOutputMaterial")
        gm.node_tree.links.new(gb.outputs[0], o.inputs[0])
    g.data.materials.append(gm)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 1.2
    sun.rotation_euler = (math.radians(40), math.radians(20), math.radians(30))
    sc.collection.objects.link(sun)
    rng = random.Random(7)
    for i, b in enumerate(shot["bursts"]):
        additive = b["lightEmission"] > 0.05
        mat = particle_material("p%d" % i, b["texture"], additive)
        quads_object("burst%d" % i, simulate_burst(b, eye, cam_right, cam_up, rng), mat)
    beam_mat = particle_material("beam", None, True)
    bq = []
    for beam in shot["beams"]:
        bq.extend(beam_quads(beam, eye))
    quads_object("beams", bq, beam_mat)
    for i, p in enumerate(shot["parts"]):
        add_part(p, i)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = 30
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = to_blender(eye)
    import mathutils

    direction = mathutils.Vector(to_blender(target)) - mathutils.Vector(to_blender(eye))
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    suffix = "_f%d" % shot["frame"] if CAMERA_OVERRIDE else ""
    path = os.path.join(OUT_DIR, "%s_%s%s.png" % (mode, shot["id"], suffix))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


data = json.load(open(SNAP))
for shot in data["shots"]:
    print("render", shot["id"], render_shot(shot, data["mode"]))
