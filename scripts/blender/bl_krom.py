"""bl_krom.py — общие помощники для скриптов Blender (запуск — scripts/bl_run.py, D-018).

Оси Blender правые: X, Y, Z-вверх, метры. При импорте glTF в UE ось Y меняет знак, метры → сантиметры
(проверено scripts/blender/hello_axes.py). Поэтому в осях здания из krom_plan (u — вперёд, v — вправо)
точка (u, v, z) в Blender — это (u, −v, z).

Геометрия героев строится в осях здания: помощники ниже принимают точки (u, v, z) и сами переводят их
в Blender. Каждый примитив — замкнутое тело; нормали наружу пересчитываются, порядок обхода не важен.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILD_DIR = os.path.join(REPO, "build", "blender")      # выгрузки для импорта в UE, в git не идут
PREVIEW_DIR = os.path.join(REPO, "media", "renders", "blender")
sys.path.insert(0, os.path.join(REPO, "scripts"))       # krom_plan и krom_geo — без bpy, общие с редактором UE


def reset_scene():
    """Пустая сцена в метрах (factory startup кладёт куб, камеру и свет)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.unit_settings.system = "METRIC"
    s.unit_settings.scale_length = 1.0


def material(name, rgb):
    """Материал-слот: в UE по имени слота назначается свой MI."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    return m


M = {}  # ключ krom_plan.COLORS → материал Blender; заполняет use_colors() после reset_scene()


def use_colors(colors):
    M.clear()
    M.update({k: material(k, rgb) for k, rgb in colors.items()})


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def join(objects, name):
    """Склеить объекты в один меш с именем name (так он станет одним StaticMesh в UE)."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = obj.data.name = name
    return obj


def export_glb(obj, name):
    """Выгрузить объект в build/blender/<name>.glb (Y-вверх по стандарту glTF, модификаторы применены)."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    path = os.path.join(BUILD_DIR, f"{name}.glb")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False)
    print(f"[bl_krom] export {path}")
    return path


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def render_preview(name, eye, target, size=(1280, 720), lens=35.0):
    """Превью Workbench в media/renders/blender/<name>.png: цвета материалов, тени и полость — быстро и без GPU-капризов."""
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    s = bpy.context.scene
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    s.collection.objects.link(cam)
    cam.location = eye
    cam.data.lens = lens
    cam.data.clip_end = 5000
    look_at(cam, target)
    s.camera = cam
    if s.world is None:  # без мира фон первого кадра прозрачный, следующих в той же сессии — чёрный
        s.world = bpy.data.worlds.new("Preview")
    s.world.color = (0.75, 0.8, 0.86)
    s.render.engine = "BLENDER_WORKBENCH"
    s.display.shading.light = "STUDIO"
    s.display.shading.color_type = "MATERIAL"
    s.display.shading.show_shadows = True
    s.display.shading.show_cavity = True
    s.render.resolution_x, s.render.resolution_y = size
    s.render.filepath = os.path.join(PREVIEW_DIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    print(f"[bl_krom] preview {s.render.filepath}")
    return s.render.filepath


def deg(a):
    return math.radians(a)


# ---------- геометрия в осях здания (u, v, z) ----------

def mesh(name, verts, faces, mat, smooth=False):
    """Тело из вершин (u, v, z) и граней-индексов; совпавшие вершины сливаются, нормали — наружу."""
    me = bpy.data.meshes.new(name)
    me.from_pydata([(u, -v, z) for u, v, z in verts], [], faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:
        f.smooth = smooth
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.set_sharp_from_angle(angle=math.radians(40))
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return assign(obj, mat)


def _prism_faces(n):
    return [list(range(n)), list(range(n, 2 * n))] + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]


def prism(name, poly, z0, z1, mat):
    """Вертикальная призма: многоугольник в плане [(u, v)] от z0 до z1."""
    return mesh(name, [(u, v, z0) for u, v in poly] + [(u, v, z1) for u, v in poly], _prism_faces(len(poly)), mat)


def box(name, u0, u1, v0, v1, z0, z1, mat):
    return prism(name, [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], z0, z1, mat)


def ngon(center, apothem, z, n=8):
    """Правильный n-угольник на высоте z с расстоянием до граней apothem: грани смотрят по осям u и v
    (и по диагоналям у восьмиугольника). apothem = 0 — точка на оси (вершина шатра)."""
    if apothem <= 0:
        return [(center[0], center[1], z)]
    r = apothem / math.cos(math.pi / n)
    return [(center[0] + r * math.cos(math.pi / n * (2 * k + 1)), center[1] + r * math.sin(math.pi / n * (2 * k + 1)), z)
            for k in range(n)]


def loft(name, rings, mat, smooth=False):
    """Тело через кольца [(u, v, z)] с одинаковым числом точек, снизу вверх; кольцо из одной точки — вершина.
    Торцы-многоугольники закрываются."""
    verts, idx = [], []
    for ring in rings:
        idx.append(list(range(len(verts), len(verts) + len(ring))))
        verts += ring
    faces = []
    for a, b in zip(idx, idx[1:]):
        n = max(len(a), len(b))
        for k in range(n):
            f = list(dict.fromkeys([a[k % len(a)], a[(k + 1) % len(a)], b[(k + 1) % len(b)], b[k % len(b)]]))
            if len(f) >= 3:
                faces.append(f)
    faces += [ring for ring in (idx[0], idx[-1]) if len(ring) > 2]
    return mesh(name, verts, faces, mat, smooth)


def slab(name, top, thick, mat):
    """Плита: плоский многоугольник top [(u, v, z)] и его копия ниже на thick (скат кровли, карниз)."""
    return mesh(name, list(top) + [(u, v, z - thick) for u, v, z in top], _prism_faces(len(top)), mat)


def hip_roof(name, u0, u1, v0, v1, z, rise, thick, mat):
    """Вальмовая кровля над прямоугольником (карниз на z): конёк вдоль длинной стороны, вальмы под 45° в плане."""
    h = min(u1 - u0, v1 - v0) / 2
    if u1 - u0 >= v1 - v0:
        vm = (v0 + v1) / 2
        r0, r1 = (u0 + h, vm, z + rise), (u1 - h, vm, z + rise)
    else:
        um = (u0 + u1) / 2
        r0, r1 = (um, v0 + h, z + rise), (um, v1 - h, z + rise)
    e = [(u0, v0, z), (u1, v0, z), (u1, v1, z), (u0, v1, z)]
    b = [(u, v, z - thick) for u, v, _ in e]
    faces = [[6, 7, 8, 9], [0, 1, 5, 4], [1, 2, 5], [2, 3, 4, 5], [3, 0, 4]] if u1 - u0 >= v1 - v0 else \
        [[6, 7, 8, 9], [0, 1, 4], [1, 2, 5, 4], [2, 3, 5], [3, 0, 4, 5]]
    faces += [[i, (i + 1) % 4, 6 + (i + 1) % 4, 6 + i] for i in range(4)]
    return mesh(name, e + [r0, r1] + b, faces, mat)


class Frame:
    """Плоскость фасада: точка o (u, v), единичные направление вдоль фасада t и наружная нормаль n (в плане).
    Точка фасада (s, z, d): s — вдоль фасада от o, z — высота, d — наружу от плоскости."""

    def __init__(self, o, t, n, length=0.0):
        self.o, self.t, self.n, self.length = o, t, n, length

    @classmethod
    def between(cls, a, b, inside):
        """Фасад по отрезку a → b в плане; нормаль смотрит от точки inside."""
        length = math.dist(a, b)
        t = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
        n = (-t[1], t[0])
        if (inside[0] - a[0]) * n[0] + (inside[1] - a[1]) * n[1] > 0:
            n = (-n[0], -n[1])
        return cls(a, t, n, length)

    @classmethod
    def radial(cls, center, r, angle):
        """Касательная к окружности (center, r) под углом angle (радианы от оси u к оси v)."""
        c, s = math.cos(angle), math.sin(angle)
        return cls((center[0] + r * c, center[1] + r * s), (-s, c), (c, s))

    def p(self, s, z, d=0.0):
        o, t, n = self.o, self.t, self.n
        return o[0] + s * t[0] + d * n[0], o[1] + s * t[1] + d * n[1], z


def extrude(name, frame, poly, d0, d1, mat):
    """Многоугольник [(s, z)] на фасаде frame, выдавленный по нормали от d0 до d1."""
    return mesh(name, [frame.p(s, z, d0) for s, z in poly] + [frame.p(s, z, d1) for s, z in poly],
                _prism_faces(len(poly)), mat)


def lathe(name, center, profile, mat, seg=48, closed=False, arc=None, smooth=True):
    """Тело вращения профиля [(r, z)] вокруг вертикали через center (u, v).

    closed — профиль замкнут (кольцо карниза); иначе концы профиля закрываются: r = 0 — точкой на оси,
    r > 0 — диском. arc — (a0, a1), радианы от оси u к оси v: сектор вместо полного оборота, торцы сектора
    закрываются профилем (для замкнутого профиля)."""
    full = arc is None
    angles = [2 * math.pi * k / seg for k in range(seg)] if full else \
        [arc[0] + (arc[1] - arc[0]) * k / seg for k in range(seg + 1)]
    m = len(angles)
    verts, rings = [], []
    for r, z in profile:
        if r < 1e-6:
            rings.append([len(verts)] * m)
            verts.append((center[0], center[1], z))
        else:
            rings.append(list(range(len(verts), len(verts) + m)))
            verts += [(center[0] + r * math.cos(a), center[1] + r * math.sin(a), z) for a in angles]
    faces = []
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for ra, rb in pairs:
        for k in range(m if full else m - 1):
            f = list(dict.fromkeys([ra[k], ra[(k + 1) % m], rb[(k + 1) % m], rb[k]]))  # у оси — треугольник
            if len(f) >= 3:
                faces.append(f)
    if full and not closed:
        faces += [ring[:] for ring in (rings[0], rings[-1]) if len(set(ring)) > 1]
    if not full:
        for k in (0, m - 1):
            f = list(dict.fromkeys(ring[k] for ring in rings))
            if len(f) >= 3:
                faces.append(f)
    return mesh(name, verts, faces, mat, smooth)


def cut(obj, cutters):
    """Вычесть из тела obj тела cutters (проёмы; не пересекаются между собой). cutters удаляются."""
    if not cutters:
        return obj
    c = join(cutters, f"{obj.name}_cutter") if len(cutters) > 1 else cutters[0]
    mod = obj.modifiers.new("cut", "BOOLEAN")
    mod.operation, mod.solver, mod.object = "DIFFERENCE", "MANIFOLD", c
    before = len(obj.data.polygons)
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    obj.modifiers.remove(mod)
    old, obj.data = obj.data, me
    bpy.data.meshes.remove(old)
    bpy.data.objects.remove(c)
    if len(me.polygons) <= before:
        print(f"[bl_krom] WARNING cut {obj.name}: булева операция ничего не вырезала")
    return obj


def box_uv(obj, size=1.0):
    """Развёртка «кубом» в метрах: грань проецируется вдоль главной оси своей нормали, 1 UV = size м."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bm = bmesh.new()
    bm.from_mesh(me)
    layer = bm.loops.layers.uv.verify()
    for f in bm.faces:
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        for loop in f.loops:
            co = loop.vert.co
            a, b = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            loop[layer].uv = (a / size, b / size)
    bm.to_mesh(me)
    bm.free()


# ---------- контуры на фасаде (s, z) ----------

def arch(sc, w, z0, zs, n=12):
    """Проём с полуциркульным верхом: середина sc, ширина w, низ z0, пята арки zs."""
    r = w / 2
    return [(sc - r, z0), (sc + r, z0)] + [(sc + r * math.cos(math.pi * k / n), zs + r * math.sin(math.pi * k / n))
                                           for k in range(n + 1)]


def arch_frame(sc, w, z0, zs, f, n=12):
    """∩-рамка ширины f вокруг проёма arch(sc, w, z0, zs) — наличник или арка аркатуры (без подоконника)."""
    r, big = w / 2, w / 2 + f
    outer = [(sc + big * math.cos(math.pi * k / n), zs + big * math.sin(math.pi * k / n)) for k in range(n + 1)]
    inner = [(sc + r * math.cos(math.pi * k / n), zs + r * math.sin(math.pi * k / n)) for k in range(n, -1, -1)]
    return [(sc + big, z0)] + outer + [(sc - big, z0), (sc - r, z0)] + inner + [(sc + r, z0)]


def rect(s0, s1, z0, z1):
    return [(s0, z0), (s1, z0), (s1, z1), (s0, z1)]


def spline(points, per=4):
    """Catmull-Rom через точки [(x, y)], per отрезков между соседними."""
    p = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(p) - 2):
        for k in range(per):
            t = k / per
            out.append(tuple(0.5 * (2 * p[i][j] + (-p[i - 1][j] + p[i + 1][j]) * t
                                    + (2 * p[i - 1][j] - 5 * p[i][j] + 4 * p[i + 1][j] - p[i + 2][j]) * t * t
                                    + (-p[i - 1][j] + 3 * p[i][j] - 3 * p[i + 1][j] + p[i + 2][j]) * t ** 3)
                             for j in range(2)))
    return out + [points[-1]]


# ---------- детали фасадов (материалы — из M) ----------

class Openings:
    """Проёмы одного тела: вырезы копятся и вычитаются разом, наличники, подоконники и стёкла — отдельные тела.
    recess — глубина проёма до стекла, frame — (ширина, вынос) наличника, mat — ключ материала тела: его получают
    откосы после выреза, наличники и подоконники."""

    def __init__(self, recess=0.5, frame=(0.28, 0.14), mat="wall"):
        self.cutters, self.parts = [], []
        self.recess, self.frame, self.mat = recess, frame, mat

    def window(self, fr, s, w, sill, spring, frame=True, hood=False):
        """Окно с полуциркульным верхом: середина s, ширина w, низ sill, пята арки spring."""
        rc, (ff, fd) = self.recess, self.frame
        self.cutters.append(extrude("cut", fr, arch(s, w, sill, spring), -rc, 0.6, M[self.mat]))
        self.parts.append(extrude("glass", fr, arch(s, w - 0.04, sill + 0.02, spring), -rc - 0.05, -rc + 0.03,
                                  M["glass"]))
        if frame:
            f = ff * min(1.0, w / 1.2)
            self.parts.append(extrude("nalichnik", fr, arch_frame(s, w - 0.06, sill, spring, f + 0.03), -0.12, fd,
                                      M[self.mat]))
            hw = w / 2 + f + 0.1
            self.parts.append(extrude("sill", fr, rect(s - hw, s + hw, sill - 0.22, sill), -0.12, 0.22, M[self.mat]))
            if hood:  # бровка — вторая арка над наличником, как у окон четверика собора
                self.parts.append(extrude("hood", fr, arch_frame(s, w + 2 * f + 0.5, spring - 0.5, spring, 0.2),
                                          -0.12, 0.2, M[self.mat]))

    def slit(self, fr, s, w, z0, z1):
        """Прямоугольное окошко без наличника (бойница столпа, окна пристройки)."""
        rc = self.recess
        self.cutters.append(extrude("cut", fr, rect(s - w / 2, s + w / 2, z0, z1), -rc, 0.6, M[self.mat]))
        self.parts.append(extrude("glass", fr, rect(s - w / 2, s + w / 2, z0, z1), -rc - 0.05, -rc + 0.03, M["glass"]))

    def apply(self, body):
        return [cut(body, self.cutters)] + self.parts


def band(u0, u1, v0, v1, z0, z1, proud, key="wall"):
    """Пояс или карниз вокруг прямоугольника в плане: плита шире стен на proud (середина скрыта в теле)."""
    return box("band", u0 - proud, u1 + proud, v0 - proud, v1 + proud, z0, z1, M[key])


def cornice(u0, u1, v0, v1, z, h, proud, flash=True):
    """Карниз высотой h под отметкой z; сверху — зелёный отлив (жесть), как на фото собора."""
    parts = [band(u0, u1, v0, v1, z - h, z, proud)]
    if flash:
        parts.append(band(u0, u1, v0, v1, z, z + 0.05, proud + 0.03, "green"))
    return parts


# ---------- детали башен (шатры, вышки, венчание) ----------

def finial(center, z_top, z_vane, ra=0.25):
    """Венчание шатра над точкой center: тёмное яблоко на z_top, шпилёк и флажок флюгера (прапор) на восток до z_vane."""
    parts = [lathe("apple", center, [(ra * math.sin(math.pi * i / 10), z_top - 0.05 + ra - ra * math.cos(math.pi * i / 10))
                                     for i in range(11)], M["dark"], seg=16)]
    z_pole = z_top - 0.05 + 2 * ra
    cu, cv = center
    parts.append(box("vane_pole", cu - 0.03, cu + 0.03, cv - 0.03, cv + 0.03, z_pole - 0.1, z_vane, M["dark"]))
    fr = Frame(center, (0.0, 1.0), (1.0, 0.0))            # флажок — на восток от шпиля
    parts.append(extrude("vane", fr, [(0.04, z_vane - 0.75), (0.75, z_vane - 0.6), (0.65, z_vane - 0.38),
                                      (0.75, z_vane - 0.16), (0.04, z_vane - 0.3)], -0.015, 0.015, M["dark"]))
    return parts


def nlathe(name, center, profile, mat, n):
    """Гранёное «тело вращения»: профиль [(r, z)] по правильным n-угольникам ngon, r — до граней (грани смотрят
    по осям u и v); r = 0 — точка на оси."""
    return loft(name, [ngon(center, r, z, n) for r, z in profile], mat)


def lookout(center, kind, collar, posts, eave, z_top, n=8, sides=0):
    """Сторожевая вышка над шатром: поясок от верха шатра collar = (r, z), вышка posts = (r, низ, верх) —
    kind "open": n столбов с двумя перилами (Кутекрома), "closed": глухой сруб cabin с окошками; зонтик
    eave = (r края, z края, z у шатрика) и шатрик до z_top. sides > 0 — всё гранёное (четверик у Власьевской):
    радиусы — до граней, грани по осям."""
    cr, cz = collar
    lr, l0, l1 = posts
    er, ez0, ez1 = eave
    if sides:
        parts = [nlathe("collar", center, [(cr, cz - 0.1), (cr + 0.25, cz + 0.15), (cr + 0.25, l0), (0.0, l0)],
                        M["wood"], sides)]
        parts += cabin(center, lr, l0, l1, sides, facets=True)
        parts.append(nlathe("lookout_eave", center, [(lr - 0.1, ez0 - 0.05), (er, ez0), (er - 0.05, ez0 + 0.1),
                                                     (lr - 0.1, ez1), (0.0, ez1)], M["wood"], sides))
        parts.append(nlathe("lookout_tent", center, [(lr - 0.15, ez1 - 0.05), (0.0, z_top)], M["wood"], sides))
        return parts
    parts = [lathe("collar", center, [(cr, cz - 0.1), (cr + 0.35, cz + 0.15), (cr + 0.35, l0), (0.0, l0)], M["wood"],
                   seg=32, smooth=False)]
    if kind == "open":
        for k in range(n):
            a = 2 * math.pi * k / n                       # в углах восьмигранных перил
            u, v = center[0] + lr * math.cos(a), center[1] + lr * math.sin(a)
            parts.append(box("post", u - 0.07, u + 0.07, v - 0.07, v + 0.07, l0, l1, M["wood"]))
        for zr in (l0 + 0.55, l0 + 0.95):                   # перила
            parts.append(lathe("rail", center, [(lr - 0.05, zr), (lr + 0.05, zr), (lr + 0.05, zr + 0.08),
                                                (lr - 0.05, zr + 0.08)], M["wood"], seg=n, closed=True, smooth=False))
    else:
        parts += cabin(center, lr, l0, l1, n)
    parts.append(lathe("lookout_eave", center, [(lr - 0.1, ez0 - 0.05), (er, ez0), (er - 0.05, ez0 + 0.1),
                                                (lr - 0.1, ez1), (0.0, ez1)], M["wood"], seg=32, smooth=False))
    parts.append(lathe("lookout_tent", center, [(lr - 0.15, ez1 - 0.05), (0.0, z_top)], M["wood"], seg=24))
    return parts


def cabin(center, r, z0, z1, n=8, win=(0.45, 0.6), facets=False):
    """Глухая сторожевая вышка: n-гранный сруб, обшитый тёсом, от z0 до z1; окошко (ширина, высота) посередине
    каждой второй грани. facets=False — r по углам, угол на оси u (как у lathe); True — r до граней, грани по осям,
    окошки у четверика — на всех четырёх гранях."""
    zc = (z0 + z1) / 2
    op = Openings(recess=0.12, mat="wood")
    if facets:
        body = prism("cabin", [p[:2] for p in ngon(center, r, 0.0, n)], z0, z1, M["wood"])
        for k in range(0, n, 1 if n == 4 else 2):
            op.slit(Frame.radial(center, r, 2 * math.pi * k / n), 0.0, win[0], zc - win[1] / 2, zc + win[1] / 2)
        return op.apply(body)
    body = lathe("cabin", center, [(r, z0), (r, z1)], M["wood"], seg=n, smooth=False)
    ap = r * math.cos(math.pi / n)
    for k in range(0, n, 2):
        op.slit(Frame.radial(center, ap, 2 * math.pi * (k + 0.5) / n), 0.0, win[0], zc - win[1] / 2, zc + win[1] / 2)
    return op.apply(body)
