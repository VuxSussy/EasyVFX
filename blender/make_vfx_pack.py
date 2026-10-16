"""EasyVFX texture/mesh pack generator for Blender (4.2+ / 5.x).

Renders high-quality VFX textures and flipbooks with Blender shader nodes
(noise, voronoi, gradients) through Cycles, builds UV-mapped slash meshes, and
exports everything as one FBX that Roblox Studio's 3D Importer can import in a
single step (textures are embedded).

Run on your own Blender:
    blender -b -P make_vfx_pack.py -- --out ./EasyVFX_Pack
or as a Python module:
    python make_vfx_pack.py --out ./EasyVFX_Pack      (needs `pip install bpy`)

Every texture is WHITE with the shape stored in alpha, so Roblox can tint it with
any Color and make it glow with LightEmission = 1.
"""

import math
import os
import sys

import bpy
import numpy as np

# --------------------------------------------------------------------------- args


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else argv[1:]
    out = "EasyVFX_Pack"
    samples = 24
    only = None
    i = 0
    while i < len(argv):
        if argv[i] == "--out":
            out = argv[i + 1]
            i += 1
        elif argv[i] == "--samples":
            samples = int(argv[i + 1])
            i += 1
        elif argv[i] == "--only":
            only = set(argv[i + 1].split(","))
            i += 1
        i += 1
    return os.path.abspath(out), samples, only


OUT, SAMPLES, ONLY = parse_args()
TEX_DIR = os.path.join(OUT, "textures")
TMP_DIR = os.path.join(OUT, "_frames")


# --------------------------------------------------------------------------- scene


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = SAMPLES
    scene.cycles.use_denoising = False
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.render.filter_size = 1.2
    return scene


class Graph:
    """Tiny helper to write shader math as code instead of dragging nodes."""

    def __init__(self, nt):
        self.nt = nt
        self.count = 0

    def _set(self, sock, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.nt.links.new(value, sock)
        else:
            sock.default_value = value

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        n.location = ((self.count % 12) * 200, -(self.count // 12) * 220)
        self.count += 1
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self._set(n.inputs[0], a)
        self._set(n.inputs[1], b)
        if len(n.inputs) > 2:
            self._set(n.inputs[2], c)
        return n.outputs[0]

    def add(self, a, b):
        return self.math("ADD", a, b)

    def sub(self, a, b):
        return self.math("SUBTRACT", a, b)

    def mul(self, a, b):
        return self.math("MULTIPLY", a, b)

    def div(self, a, b):
        return self.math("DIVIDE", a, b)

    def pow(self, a, b):
        return self.math("POWER", a, b)

    def clamp01(self, a):
        return self.math("ADD", a, 0.0, clamp=True)

    def smooth(self, x, lo, hi):
        """0 at lo, 1 at hi, smooth in between (lo may be > hi to invert)."""
        n = self.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        self._set(n.inputs["Value"], x)
        self._set(n.inputs["From Min"], lo)
        self._set(n.inputs["From Max"], hi)
        n.inputs["To Min"].default_value = 0.0
        n.inputs["To Max"].default_value = 1.0
        return n.outputs["Result"]

    def vec(self, x, y, z=0.0):
        n = self.node("ShaderNodeCombineXYZ")
        self._set(n.inputs["X"], x)
        self._set(n.inputs["Y"], y)
        self._set(n.inputs["Z"], z)
        return n.outputs[0]

    def noise(self, vector, scale=1.0, detail=4.0, roughness=0.55, distortion=0.0, w=0.0):
        n = self.node("ShaderNodeTexNoise", noise_dimensions="4D")
        self._set(n.inputs["Vector"], vector)
        self._set(n.inputs["W"], w)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = roughness
        n.inputs["Distortion"].default_value = distortion
        return n.outputs["Fac"]

    def voronoi_edge(self, vector, scale=5.0, w=0.0):
        n = self.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="DISTANCE_TO_EDGE")
        self._set(n.inputs["Vector"], vector)
        self._set(n.inputs["W"], w)
        n.inputs["Scale"].default_value = scale
        return n.outputs["Distance"]

    def uv(self):
        tc = self.node("ShaderNodeTexCoord")
        sep = self.node("ShaderNodeSeparateXYZ")
        self.nt.links.new(tc.outputs["UV"], sep.inputs[0])
        return sep.outputs["X"], sep.outputs["Y"]

    def output_alpha(self, intensity):
        """White emission whose alpha is `intensity` (straight alpha PNG)."""
        mix = self.node("ShaderNodeMixShader")
        transp = self.node("ShaderNodeBsdfTransparent")
        emit = self.node("ShaderNodeEmission")
        emit.inputs["Color"].default_value = (1, 1, 1, 1)
        emit.inputs["Strength"].default_value = 1.0
        self._set(mix.inputs["Fac"], self.clamp01(intensity))
        self.nt.links.new(transp.outputs[0], mix.inputs[1])
        self.nt.links.new(emit.outputs[0], mix.inputs[2])
        out = self.node("ShaderNodeOutputMaterial")
        self.nt.links.new(mix.outputs[0], out.inputs["Surface"])


def make_canvas(scene, width, height, build):
    """Plane filling an orthographic camera; `build(graph)` writes its shader."""
    for obj in list(scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    aspect = width / height
    bpy.ops.mesh.primitive_plane_add(size=1)
    plane = bpy.context.object
    plane.scale = (aspect, 1, 1)
    mat = bpy.data.materials.new("canvas")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    mat.node_tree.nodes.clear()
    build(Graph(mat.node_tree))
    plane.data.materials.append(mat)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(aspect, 1.0)
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (0, 0, 3)
    scene.camera = cam
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    return mat


def whiten(px):
    """Every texture is white with the shape in alpha. Cycles writes black RGB into
    transparent pixels, which Roblox's bilinear filtering and mipmaps smear into a
    dark rim around every soft edge, so force RGB to white (see
    tools/fix_texture_edges.py for colored textures)."""
    px = px.reshape(-1, 4)
    px[:, :3] = 1.0
    return px.ravel()


def render_to(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    img.pixels.foreach_set(whiten(px))
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


# --------------------------------------------------------------------------- shapes


def slash_shape(g, u, v, reveal=1.0, dissolve=0.0, seed=0.0, fibers=1.0):
    """Anime slash on (u, v): u 0 = tail .. 1 = head, v 0 = inner .. 1 = outer edge.

    Thick near the head, sharp tip, long thinning tail, bright crisp outer edge,
    fibrous streaks along the length and a frayed tail that erodes away.
    """
    # visible length grows with `reveal` (the blade "draws" itself)
    head = reveal
    un = g.div(u, max(head, 1e-3))  # 0..1 inside the revealed part
    inside = g.mul(g.smooth(u, head + 0.002, head - 0.01), g.smooth(u, 0.0, 0.02))
    # width envelope: sharp at both ends, widest around 70% toward the head
    env = g.pow(g.math("SINE", g.mul(g.pow(g.clamp01(un), 0.75), math.pi)), 0.55)
    width = g.mul(env, 0.98)
    depth = g.div(g.sub(1.0, v), g.add(width, 1e-4))  # 0 at outer edge .. 1 at inner edge
    # fibers: long thin streaks along the blade (hair-like). Each strand also gets
    # its own length (inner reach and tail end) so the edges fray strand by strand.
    fib_n = g.noise(g.vec(g.mul(u, 1.6), g.mul(depth, 55.0)), scale=1.0, detail=5.0, roughness=0.55, w=seed)
    fib = g.smooth(fib_n, 0.44, 0.68)
    strand = g.noise(g.vec(g.mul(u, 0.7), g.mul(depth, 26.0)), scale=1.0, detail=2.0, roughness=0.5, w=seed + 7.0)
    reach = g.add(0.55, g.mul(strand, 0.6))  # how far inward this strand goes
    body = g.mul(g.smooth(depth, reach, g.sub(reach, 0.3)), g.smooth(depth, -0.015, 0.01))
    # brightness: thin hot rim on the outer edge + streaky body
    rim = g.pow(g.clamp01(g.sub(1.0, depth)), 9.0)
    base = g.mul(g.pow(g.clamp01(g.sub(1.0, depth)), 0.9), 0.7)
    streaks = g.add(1.0 - 0.8 * fibers, g.mul(fib, 1.0 * fibers))
    intensity = g.add(rim, g.mul(base, streaks))
    # frayed tail + dissolve: strands end at different points; threshold rises
    # toward the tail and over time
    ero_n = g.noise(g.vec(g.mul(u, 2.2), g.mul(depth, 40.0)), scale=1.0, detail=4.0, roughness=0.6, distortion=0.3, w=seed + 3.1)
    tail = g.mul(g.smooth(un, 0.45, 0.0), 0.85)
    threshold = g.add(tail, g.mul(dissolve, 1.15))
    keep = g.smooth(ero_n, g.sub(threshold, 0.08), g.add(threshold, 0.02))
    # dissolve also eats from the tail end along the length
    sweep = g.smooth(un, g.mul(dissolve, 1.1), g.add(g.mul(dissolve, 1.1), 0.15))
    alpha = g.mul(g.mul(g.mul(body, intensity), keep), g.mul(inside, sweep))
    return alpha


def polar(g, x, y, cx, cy, a0, a1, r0, r1):
    """Maps image coords to (u, v) along an arc: u by angle a0->a1, v by radius r0->r1."""
    dx = g.sub(x, cx)
    dy = g.sub(y, cy)
    ang = g.math("ARCTAN2", dy, dx)
    rad = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
    u = g.div(g.sub(ang, a0), a1 - a0)
    v = g.div(g.sub(rad, r0), r1 - r0)
    in_range = g.mul(g.smooth(u, -0.01, 0.0), g.smooth(u, 1.01, 1.0))
    return u, v, in_range


# --------------------------------------------------------------------------- textures


def tex_slash_fiber(scene):
    def build(g):
        u, v = g.uv()
        g.output_alpha(slash_shape(g, u, v, seed=1.7))

    make_canvas(scene, 1024, 256, build)
    render_to(scene, os.path.join(TEX_DIR, "slash_fiber.png"))


def tex_slash_clean(scene):
    def build(g):
        u, v = g.uv()
        g.output_alpha(slash_shape(g, u, v, seed=5.2, fibers=0.25))

    make_canvas(scene, 1024, 256, build)
    render_to(scene, os.path.join(TEX_DIR, "slash_clean.png"))


def tex_slash_arc(scene):
    """The fibrous slash bent into a crescent on a square canvas (for flat particles)."""

    def build(g):
        x, y = g.uv()
        u, v, rng = polar(g, x, y, 0.5, 0.5, math.radians(172), math.radians(8), 0.16, 0.48)
        glow_d = g.math("ABSOLUTE", g.sub(v, 0.82))
        glow = g.mul(g.mul(g.pow(g.clamp01(g.sub(1.0, g.mul(glow_d, 3.0))), 3.0), 0.22), g.mul(rng, g.math("SINE", g.mul(g.clamp01(u), math.pi))))
        g.output_alpha(g.math("MAXIMUM", g.mul(slash_shape(g, u, v, seed=1.7), rng), glow))

    make_canvas(scene, 1024, 1024, build)
    render_to(scene, os.path.join(TEX_DIR, "slash_arc.png"))


def tex_slash_glow(scene):
    def build(g):
        u, v = g.uv()
        env = g.pow(g.math("SINE", g.mul(g.pow(u, 0.85), math.pi)), 0.8)
        center = g.sub(1.0, g.mul(env, 0.45))
        d = g.math("ABSOLUTE", g.sub(v, center))
        soft = g.pow(g.clamp01(g.sub(1.0, g.div(d, g.add(g.mul(env, 0.55), 0.02)))), 2.0)
        g.output_alpha(g.mul(g.mul(soft, env), 0.85))

    make_canvas(scene, 512, 128, build)
    render_to(scene, os.path.join(TEX_DIR, "slash_glow.png"))


def tex_slash_core(scene):
    def build(g):
        u, v = g.uv()
        env = g.pow(g.math("SINE", g.mul(g.pow(u, 0.8), math.pi)), 1.2)
        d = g.math("ABSOLUTE", g.sub(v, 0.5))
        line = g.pow(g.clamp01(g.sub(1.0, g.div(d, g.add(g.mul(env, 0.45), 0.005)))), 1.5)
        g.output_alpha(g.mul(line, env))

    make_canvas(scene, 1024, 64, build)
    render_to(scene, os.path.join(TEX_DIR, "slash_core.png"))


def tex_star(scene):
    def build(g):
        x, y = g.uv()
        dx = g.math("ABSOLUTE", g.sub(x, 0.5))
        dy = g.math("ABSOLUTE", g.sub(y, 0.5))
        r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
        # 4 sharp rays: thin where |dx|*|dy| is small, fading with distance
        ray = g.smooth(g.mul(g.mul(dx, dy), 400.0), 1.0, 0.0)
        rays = g.mul(ray, g.pow(g.clamp01(g.sub(1.0, g.mul(r, 2.05))), 1.6))
        core = g.pow(g.clamp01(g.sub(1.0, g.mul(r, 9.0))), 2.0)
        halo = g.mul(g.pow(g.clamp01(g.sub(1.0, g.mul(r, 3.2))), 3.0), 0.45)
        g.output_alpha(g.math("MAXIMUM", g.math("MAXIMUM", rays, core), halo))

    make_canvas(scene, 256, 256, build)
    render_to(scene, os.path.join(TEX_DIR, "spark_star.png"))


def tex_streak(scene):
    def build(g):
        x, y = g.uv()
        dx = g.math("ABSOLUTE", g.sub(x, 0.5))
        dy = g.math("ABSOLUTE", g.sub(y, 0.5))
        width = g.mul(g.pow(g.clamp01(g.sub(1.0, g.mul(dy, 2.0))), 1.4), 0.09)
        line = g.smooth(dx, g.add(width, 0.01), g.mul(width, 0.3))
        g.output_alpha(line)

    make_canvas(scene, 256, 256, build)
    render_to(scene, os.path.join(TEX_DIR, "spark_streak.png"))


def tex_glow(scene):
    def build(g):
        x, y = g.uv()
        dx = g.sub(x, 0.5)
        dy = g.sub(y, 0.5)
        r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
        g.output_alpha(g.pow(g.clamp01(g.sub(1.0, g.mul(r, 2.0))), 2.6))

    make_canvas(scene, 256, 256, build)
    render_to(scene, os.path.join(TEX_DIR, "glow_soft.png"))


def tex_ring(scene):
    def build(g):
        x, y = g.uv()
        dx = g.sub(x, 0.5)
        dy = g.sub(y, 0.5)
        r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
        band = g.mul(g.smooth(r, 0.36, 0.47), g.smooth(r, 0.495, 0.475))
        bright = g.add(g.pow(g.smooth(r, 0.36, 0.48), 3.0), 0.15)
        ang = g.math("ARCTAN2", dy, dx)
        n = g.noise(g.vec(g.mul(g.math("COSINE", ang), 2.0), g.mul(g.math("SINE", ang), 2.0), g.mul(r, 14.0)), scale=2.0, detail=5.0)
        breakup = g.smooth(n, 0.3, 0.6)
        g.output_alpha(g.mul(g.mul(band, bright), g.add(0.35, g.mul(breakup, 0.65))))

    make_canvas(scene, 512, 512, build)
    render_to(scene, os.path.join(TEX_DIR, "ring_wave.png"))


# --------------------------------------------------------------------------- flipbooks


def flipbook(scene, name, tile, grid, frame_builder):
    """Renders grid*grid frames (t = 0..1) and packs them into one sheet."""
    frames = grid * grid
    os.makedirs(TMP_DIR, exist_ok=True)
    paths = []
    for i in range(frames):
        t = i / (frames - 1)

        def build(g, t=t, i=i):
            frame_builder(g, t, i)

        make_canvas(scene, tile, tile, build)
        p = os.path.join(TMP_DIR, f"{name}_{i:02d}.png")
        render_to(scene, p)
        paths.append(p)
    sheet = np.zeros((tile * grid, tile * grid, 4), dtype=np.float32)
    for i, p in enumerate(paths):
        img = bpy.data.images.load(p)
        px = np.empty(tile * tile * 4, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(tile, tile, 4)  # Blender stores rows bottom-up
        row, col = divmod(i, grid)
        y0 = (grid - 1 - row) * tile
        sheet[y0 : y0 + tile, col * tile : (col + 1) * tile] = px
        bpy.data.images.remove(img)
    out = bpy.data.images.new(name, tile * grid, tile * grid, alpha=True)
    out.pixels.foreach_set(whiten(sheet.ravel()))
    out.filepath_raw = os.path.join(TEX_DIR, f"{name}.png")
    out.file_format = "PNG"
    out.save()
    bpy.data.images.remove(out)


def flip_slash(g, t, i):
    x, y = g.uv()
    u, v, rng = polar(g, x, y, 0.5, 0.5, math.radians(172), math.radians(8), 0.16, 0.48)
    reveal = min(1.0, t / 0.22)
    reveal = 1 - (1 - reveal) ** 3
    dissolve = max(0.0, (t - 0.25) / 0.75)
    g.output_alpha(g.mul(slash_shape(g, u, v, reveal=reveal, dissolve=dissolve, seed=2.3), rng))


def flip_impact(g, t, i):
    x, y = g.uv()
    dx = g.sub(x, 0.5)
    dy = g.sub(y, 0.5)
    r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
    ang = g.math("ARCTAN2", dy, dx)
    grow = 1 - (1 - min(1.0, t / 0.35)) ** 3
    # spikes: angular noise -> uneven ray lengths
    ray_len = g.add(0.18 + 0.2 * grow, g.mul(g.noise(g.vec(g.math("COSINE", ang), g.math("SINE", ang)), scale=3.0, detail=2.0, w=4.0), 0.22 * grow))
    spikes = g.voronoi_edge(g.vec(g.mul(g.math("COSINE", ang), 1.0), g.mul(g.math("SINE", ang), 1.0)), scale=9.0)
    ray = g.smooth(spikes, 0.0, 0.05 + 0.1 * (1 - t))
    inner = 0.03 + 0.25 * t
    shape = g.mul(g.smooth(r, ray_len, g.mul(ray_len, 0.6)), g.smooth(r, inner, inner + 0.04))
    spike_alpha = g.mul(shape, g.sub(1.0, g.mul(ray, 0.85)))
    core = g.mul(g.pow(g.clamp01(g.sub(1.0, g.div(r, 0.16 * (1 - t) + 0.001))), 1.5), 1.0 - t)
    n = g.noise(g.vec(g.mul(x, 6.0), g.mul(y, 6.0)), scale=1.0, detail=4.0, w=7.0)
    erode = g.smooth(n, max(0.0, t - 0.45) * 1.4, max(0.0, t - 0.45) * 1.4 + 0.1)
    g.output_alpha(g.math("MAXIMUM", g.mul(spike_alpha, erode), core))


def flip_smoke(g, t, i):
    x, y = g.uv()
    dx = g.sub(x, 0.5)
    dy = g.sub(y, 0.5)
    r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
    radius = 0.3 + 0.18 * (1 - (1 - t) ** 2)
    n = g.noise(g.vec(g.mul(x, 4.0), g.mul(y, 4.0)), scale=1.0, detail=7.0, roughness=0.6, distortion=0.3, w=t * 1.2)
    puff = g.smooth(g.add(r, g.mul(g.sub(n, 0.5), 0.25)), radius, radius * 0.55)
    density = g.smooth(n, 0.2 + t * 0.45, 0.5 + t * 0.4)
    shade = g.add(0.55, g.mul(n, 0.45))
    g.output_alpha(g.mul(g.mul(puff, density), g.mul(shade, 1.0 - 0.25 * t)))


def flip_electric(g, t, i):
    x, y = g.uv()
    dx = g.sub(x, 0.5)
    dy = g.sub(y, 0.5)
    r = g.math("SQRT", g.add(g.mul(dx, dx), g.mul(dy, dy)))
    warp = g.noise(g.vec(g.mul(x, 3.0), g.mul(y, 3.0)), scale=1.0, detail=2.0, w=i * 0.37)
    edges = g.voronoi_edge(g.vec(g.add(g.mul(x, 3.0), warp), g.add(g.mul(y, 3.0), warp)), scale=1.6, w=i * 0.29)
    bolt = g.smooth(edges, 0.035, 0.0)
    mask = g.smooth(r, 0.48, 0.3)
    g.output_alpha(g.mul(g.mul(bolt, mask), 1.0 - 0.3 * t))


# --------------------------------------------------------------------------- meshes + FBX


def image_material(name, image_path):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    img = bpy.data.images.load(image_path)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 1.0
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return mat


def arc_mesh(name, radius, width, arc_deg, segments=48, lift=0.0, twist=0.0):
    """Flat (optionally cone-lifted) crescent band. UV u runs tail->head, v inner->outer."""
    verts, faces, uvs = [], [], []
    a0 = math.radians(90 + arc_deg / 2)
    a1 = math.radians(90 - arc_deg / 2)
    for k in range(segments + 1):
        f = k / segments
        a = a0 + (a1 - a0) * f
        ca, sa = math.cos(a), math.sin(a)
        for side in (0, 1):
            r = radius - width + width * side
            y = lift * side + twist * math.sin(math.pi * f) * (side - 0.5)
            verts.append((ca * r, y, -sa * r))
            uvs.append((f, side))
    for k in range(segments):
        i = k * 2
        faces.append((i, i + 2, i + 3, i + 1))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            uv_layer.data[li].uv = uvs[mesh.loops[li].vertex_index]
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def quad(name, x):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name
    obj.rotation_euler = (math.radians(90), 0, 0)
    return obj


def build_fbx():
    reset_scene()
    for obj in list(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    fiber = image_material("EVFX_SlashFiber", os.path.join(TEX_DIR, "slash_fiber.png"))
    clean = image_material("EVFX_SlashClean", os.path.join(TEX_DIR, "slash_clean.png"))
    meshes = [
        ("EVFX_Mesh_SlashWide", arc_mesh("EVFX_Mesh_SlashWide", 5.0, 2.2, 200, lift=0.35), fiber),
        ("EVFX_Mesh_SlashThin", arc_mesh("EVFX_Mesh_SlashThin", 5.5, 1.0, 160, lift=0.15), clean),
        ("EVFX_Mesh_SpinRing", arc_mesh("EVFX_Mesh_SpinRing", 5.0, 1.8, 350, segments=72, lift=0.5), fiber),
    ]
    for _, obj, mat in meshes:
        obj.data.materials.append(mat)
    x = 14.0
    for fname in sorted(os.listdir(TEX_DIR)):
        if not fname.endswith(".png"):
            continue
        key = os.path.splitext(fname)[0]
        q = quad("EVFX_Tex_" + key, x)
        q.data.materials.append(image_material("EVFX_" + key, os.path.join(TEX_DIR, fname)))
        x += 1.5
    path = os.path.join(OUT, "EasyVFX_Pack.fbx")
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=False,
        path_mode="COPY",
        embed_textures=True,
        axis_forward="-Z",
        axis_up="Y",
        apply_scale_options="FBX_SCALE_ALL",
        mesh_smooth_type="FACE",
    )
    print("wrote", path)


# --------------------------------------------------------------------------- main


def main():
    os.makedirs(TEX_DIR, exist_ok=True)
    scene = reset_scene()
    jobs = [
        ("slash_fiber", lambda: tex_slash_fiber(scene)),
        ("slash_clean", lambda: tex_slash_clean(scene)),
        ("slash_arc", lambda: tex_slash_arc(scene)),
        ("slash_glow", lambda: tex_slash_glow(scene)),
        ("slash_core", lambda: tex_slash_core(scene)),
        ("spark_star", lambda: tex_star(scene)),
        ("spark_streak", lambda: tex_streak(scene)),
        ("glow_soft", lambda: tex_glow(scene)),
        ("ring_wave", lambda: tex_ring(scene)),
        ("flip_slash", lambda: flipbook(scene, "flip_slash", 256, 4, flip_slash)),
        ("flip_impact", lambda: flipbook(scene, "flip_impact", 256, 4, flip_impact)),
        ("flip_smoke", lambda: flipbook(scene, "flip_smoke", 256, 4, flip_smoke)),
        ("flip_electric", lambda: flipbook(scene, "flip_electric", 256, 4, flip_electric)),
    ]
    for name, job in jobs:
        if ONLY and name not in ONLY:
            continue
        print("==", name)
        job()
    if not ONLY or "fbx" in ONLY:
        build_fbx()


main()
