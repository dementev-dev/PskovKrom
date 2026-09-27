"""tree.py — деревья и кусты M5: ветви трубками, листва карточками по скелетам Procedural Vegetation Editor (UE 5.8).

    python scripts/bl_run.py scripts/blender/tree.py                  # все варианты VARIANTS
    python scripts/bl_run.py scripts/blender/tree.py -- Maple_01      # один или несколько

Скелет — JSON Houdini из плагина UE ProceduralVegetationEditor (PVE_DIR, в репозиторий не копируем):
points.positions — точки ветвей (м, ось Y вверх), pscale — радиус ветви (м); primitives.points — ломаные ветвей
(дочерняя начинается в точке родителя); instancer_pivot / instancer_UP / instancer_N — веточки с листвой: точка на
ветви, ось веточки, нормаль листа. instancer_scale — множитель к мешам Quixel, которых у нас нет: размер карточки
задаёт порода (LEAF), а instancer_scale даёт только разброс.

Ветви — трубки по прореженной ломаной (граней 12…4 по радиусу); ветви тоньше drop_r не строятся — на них только листва.
Ствол уходит под землю на SINK м (для склонов), комель расширен. UV коры — в метрах: U — дуга по окружности (θ·r),
V — длина вдоль ветви; материал делит UV на tile_m коры (refs/textures/trees.json).
Листва — квадратные карточки на ячейку атласа своей породы (раскладка — refs/textures/trees.json, её пишет
scripts/leaf_atlas.py): основание веточки из атласа — в точке крепления, карточка вытянута вдоль оси веточки.
Карточки ставятся (1) по instancer_* (кроме сухих веточек) — spray штук вдоль воображаемой веточки, (2) вдоль
тонких ветвей (r < leafy_r) с шагом step и на концах ветвей. Карточка — «книжка» из двух половин с изломом по оси
или крест из двух квадов; ось карточки прижата к поверхности кроны (не «ёжик»), лицо — наружу; нормали вершин
отогнуты от центра кроны (объём при освещении). Масштаб варианта: scale — весь скелет, spread — дополнительно по
горизонтали (крона шире), thick — толщина ветвей (у скелетов стволы тонковаты для такой высоты — гипотеза).

Слоты материалов: bark, leaves; UV — один слой; цвет вершин COLOR_0 — см. Builder. Выгрузка —
build/blender/SM_Tree_<Порода>_<NN>.glb (как bl_krom.export_glb, плюс цвет вершин), сводка — build/blender/
trees_report.json; превью — media/renders/blender/tree_<Порода>_<NN>_{side,ground,crown}.png (Workbench, текстуры
с отсечением по альфе, фигура человека 1,8 м).
Детерминированно: seed — crc32 имени варианта. Оси Blender: X, Y, Z-вверх, метры; основание ствола — (0, 0, 0).
Порода «липа» — скелет бука Beech_01 с листом липы в атласе (гипотеза: габитус взрослых деревьев похож).
"""
import json
import math
import os
import random
import sys
import zlib
from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402

PVE_DIR = "D:/Games/Epic Games/UE_5.8/Engine/Plugins/Experimental/ProceduralVegetationEditor/Content/SampleAssets"
TREES_JSON = os.path.join(bk.REPO, "refs", "textures", "trees.json")
SINK = 0.5          # ствол ниже земли, м
UP = Vector((0.0, 0.0, 1.0))


@dataclass
class Leaf:
    """Листва породы: card — сторона карточки (м); spray — карточек на веточку instancer вдоль spray_len (м);
    leafy_r — ветви тоньше (м, после масштаба) облиственные, step — шаг карточек по ним (м); cross — доля крестов;
    min_z — ниже листвы нет (м); hug — насколько ось карточки прижата к поверхности кроны (0..1); twig — строить
    воображаемую веточку spray тонкой трубкой (длинные spray иначе висят в воздухе). Сторона карточки согласована
    с атласом: лист в метрах = доля пластинки в ячейке (leaf_atlas.SPECIES) × card."""
    card: float
    spray: int
    spray_len: float
    leafy_r: float
    step: float
    cross: float = 0.3
    min_z: float = 0.0
    hug: float = 0.5
    twig: bool = False


LEAF = {
    "maple": Leaf(card=0.75, spray=14, spray_len=1.2, leafy_r=0.035, step=0.15, twig=True),
    "aspen": Leaf(card=0.55, spray=4, spray_len=0.6, leafy_r=0.02, step=0.22),
    "hazel": Leaf(card=0.55, spray=1, spray_len=0.3, leafy_r=0.012, step=0.25, min_z=0.3),
    "linden": Leaf(card=0.6, spray=7, spray_len=0.7, leafy_r=0.035, step=0.17),
}
TWIG_R = 0.008      # радиус воображаемой веточки у основания, м


@dataclass
class Variant:
    src: str            # JSON скелета от PVE_DIR
    species: str        # ключ LEAF и строки атласа
    scale: float        # весь скелет
    spread: float = 1.0  # дополнительно по горизонтали
    thick: float = 1.0   # толщина ветвей
    drop_r: float = 0.008  # ветви тоньше (м, после масштаба) не строятся
    flare: float = 0.35  # расширение комля у земли (доля радиуса)


VARIANTS = {
    "Maple_01": Variant("Tree_Norway_Maple_01/Instances/NorwayMaple_01.json", "maple", 1.2, 1.25, 1.4),
    "Maple_02": Variant("Tree_Norway_Maple_01/Instances/NorwayMaple_02.json", "maple", 1.25, 1.2, 1.4),
    "Aspen_01": Variant("Tree_European_QuakingAspen_01/Instances/QuakingAspen_01.json", "aspen", 1.1, 1.0, 1.15),
    "Aspen_02": Variant("Tree_European_QuakingAspen_01/Instances/QuakingAspen_02.json", "aspen", 1.3, 1.0, 1.15),
    "Hazel_01": Variant("Tree_Common_Hazel_01/Instances/Broadleaf_Hazel_01.json", "hazel", 0.88, 1.0, 1.1,
                        drop_r=0.005, flare=0.1),
    "Linden_01": Variant("Tree_European_Beech_01/Instances/Beech_01.json", "linden", 0.82, 1.2, 1.4),
}
DEAD = ("Dead", "BrTwig")   # сухие и голые веточки — без листвы


# ---------- скелет ----------

class Skeleton:
    """Скелет в осях Blender (метры, Z вверх) с масштабом варианта."""

    def __init__(self, v):
        with open(os.path.join(PVE_DIR, v.src), encoding="utf-8") as f:
            d = json.load(f)
        s = np.array([v.scale * v.spread, v.scale * v.spread, v.scale])
        p = np.asarray(d["points"]["positions"], dtype=np.float64)
        self.P = np.stack([p[:, 0], -p[:, 2], p[:, 1]], axis=1) * s
        self.R = np.asarray(d["points"]["attributes"]["pscale"]["values"], dtype=np.float64) * v.scale * v.thick
        pr = d["primitives"]
        a = pr["attributes"]
        self.prims = [list(x) for x in pr["points"]]
        self.gen = a["branchGeneration"]["values"]
        self.children = a["children"]["values"]
        self.inst = []   # (номер ветви, точка, ось веточки, нормаль листа, instancer_scale)
        for i in range(len(self.prims)):
            piv, upv, nv = (a[k]["values"][i] for k in ("instancer_pivot", "instancer_UP", "instancer_N"))
            for k, (name, sc) in enumerate(zip(a["instancer_name"]["values"][i], a["instancer_scale"]["values"][i])):
                if any(x in name for x in DEAD):
                    continue
                q = np.array(piv[3 * k:3 * k + 3])
                u = np.array(upv[3 * k:3 * k + 3])
                n = np.array(nv[3 * k:3 * k + 3])
                self.inst.append((i, Vector(np.array([q[0], -q[2], q[1]]) * s),
                                  Vector(np.array([u[0], -u[2], u[1]]) * s).normalized(),
                                  Vector(np.array([n[0], -n[2], n[1]]) / s).normalized(), sc))


# ---------- сборка меша ----------

class Builder:
    """Вершины, грани с материалом, UV, нормали и цвет по углам граней — один меш с двумя слотами.
    Цвет вершин (COLOR_0): R — случайное число карточки (оттенок), G — удалённость от центра кроны (0 — центр,
    1 — поверхность; для затенения внутри кроны), B — 0 кора / 1 листва."""

    def __init__(self):
        self.verts, self.faces, self.mat, self.uv, self.nrm, self.col = [], [], [], [], [], []

    def v(self, co):
        self.verts.append(tuple(co))
        return len(self.verts) - 1

    def face(self, idx, mat, uvs, nrms, col=(0.5, 1.0, 0.0, 1.0)):
        self.faces.append(tuple(idx))
        self.mat.append(mat)
        self.uv += uvs
        self.nrm += [tuple(n) for n in nrms]
        self.col += [col] * len(idx)

    def tris(self, mat):
        return sum(len(f) - 2 for f, m in zip(self.faces, self.mat) if m == mat)

    def to_object(self, name, materials):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        for m in materials:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.mat)
        me.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        uv = me.uv_layers.new(name="UVMap")
        uv.data.foreach_set("uv", [c for p in self.uv for c in p])
        ca = me.color_attributes.new("Color", "FLOAT_COLOR", "CORNER")
        ca.data.foreach_set("color", [c for p in self.col for c in p])
        me.color_attributes.active_color = ca
        me.normals_split_custom_set(self.nrm)
        me.update()
        obj = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def perpendicular(t):
    ref = UP if abs(t.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    return (ref - ref.dot(t) * t).normalized()


def decimate(P, R, idx):
    """Прореженная ломаная: жадно тянем отрезок, пока промежуточные точки ближе tol и длина ≤ seg_max."""
    keep, i, n = [idx[0]], 0, len(idx)
    while i < n - 1:
        r = R[idx[i]]
        tol, seg_max = max(0.008, 0.3 * r), min(1.2, max(0.3, 20.0 * r))
        best, j = i + 1, i + 2
        while j < n:
            a, b = P[idx[i]], P[idx[j]]
            ab = b - a
            L = np.linalg.norm(ab)
            if L > seg_max:
                break
            mid = P[idx[i + 1:j]] - a
            dev = np.linalg.norm(mid - np.outer(mid @ ab / (L * L), ab), axis=1).max() if L > 1e-9 else 0.0
            if dev > tol:
                break
            best, j = j, j + 1
        keep.append(idx[best])
        i = best
    return keep


def sides_for(r):
    for lim, n in ((0.1, 12), (0.06, 10), (0.035, 8), (0.02, 6), (0.012, 5)):
        if r >= lim:
            return n
    return 4


def tube(B, pts, rads, rng):
    """Трубка по точкам pts (Vector) с радиусами rads; последняя точка — вершина конуса. UV в метрах."""
    m = len(pts)
    n = sides_for(rads[0])
    tang = []
    for i in range(m):
        a, b = pts[max(0, i - 1)], pts[min(m - 1, i + 1)]
        tang.append((b - a).normalized())
    nor = perpendicular(tang[0])
    rings, s, v_off = [], 0.0, rng.uniform(0.0, 5.0)
    for i in range(m - 1):
        t = tang[i]
        nor = (nor - nor.dot(t) * t).normalized()
        bi = t.cross(nor)
        if i:
            s += (pts[i] - pts[i - 1]).length
        dirs = [math.cos(2 * math.pi * k / n) * nor + math.sin(2 * math.pi * k / n) * bi for k in range(n)]
        rings.append(([B.v(pts[i] + rads[i] * d) for d in dirs], dirs, rads[i], s))
    for (ia, da, ra, sa), (ib, db, rb, sb) in zip(rings, rings[1:]):
        for k in range(n):
            k1 = (k + 1) % n
            th0, th1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            B.face((ia[k], ia[k1], ib[k1], ib[k]), 0,
                   [(th0 * ra, sa + v_off), (th1 * ra, sa + v_off), (th1 * rb, sb + v_off), (th0 * rb, sb + v_off)],
                   [da[k], da[k1], db[k1], db[k]])
    ia, da, ra, sa = rings[-1]
    s_end = sa + (pts[-1] - pts[-2]).length
    apex = B.v(pts[-1])
    t = tang[-1]
    for k in range(n):
        k1 = (k + 1) % n
        th0, th1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
        B.face((ia[k], ia[k1], apex), 0, [(th0 * ra, sa + v_off), (th1 * ra, sa + v_off),
                                          ((th0 + th1) / 2 * ra, s_end + v_off)], [da[k], da[k1], t])


def branches(B, sk, v, rng):
    """Все ветви толще drop_r; у ветвей от земли — ствол под землю и комель."""
    tip_r = max(0.75 * v.drop_r, 0.003)   # тоньше — конец ветви конусом (дальше её прячет листва)
    height = float(sk.P[:, 2].max())
    flare_h = max(0.4, 0.05 * height)
    count = 0
    for i, idx in enumerate(sk.prims):
        if len(idx) < 2 or sk.R[idx[0]] < v.drop_r:
            continue
        cut = next((k for k, j in enumerate(idx) if sk.R[j] < tip_r), len(idx))
        idx = idx[:max(2, cut + 1)]
        keep = decimate(sk.P, sk.R, idx)
        pts = [Vector(sk.P[j]) for j in keep]
        rads = [float(sk.R[j]) for j in keep]
        if pts[0].z < 0.05:          # от земли: комель и уход под землю
            rads = [float(r * (1.0 + v.flare * max(0.0, 1.0 - p.z / flare_h) ** 2)) for p, r in zip(pts, rads)]
            pts.insert(0, Vector((pts[0].x, pts[0].y, -SINK)))
            rads.insert(0, rads[0])
        tube(B, pts, rads, rng)
        count += 1
    return count


# ---------- листва ----------

class Crown:
    """Эллипсоид кроны по точкам листвы: наружное направление для карточек и нормалей."""

    def __init__(self, pts):
        a = np.array([tuple(p) for p in pts])
        lo, hi = a.min(axis=0), a.max(axis=0)
        self.c = Vector((0.0, 0.0, (lo[2] + hi[2]) / 2))
        rh = max(0.5, float(max(np.abs(a[:, 0]).max(), np.abs(a[:, 1]).max())))
        self.r2 = Vector((rh * rh, rh * rh, max(0.5, (hi[2] - lo[2]) / 2) ** 2))
        self.size = (2 * rh, float(hi[2] - lo[2]))

    def out(self, p):
        d = p - self.c
        g = Vector((d.x / self.r2.x, d.y / self.r2.y, d.z / self.r2.z))
        return g.normalized() if g.length > 1e-6 else UP.copy()

    def depth(self, p):
        """0 — центр кроны, 1 — поверхность эллипсоида и дальше."""
        d = p - self.c
        return min(1.0, math.sqrt(d.x * d.x / self.r2.x + d.y * d.y / self.r2.y + d.z * d.z / self.r2.z))


def rand_unit(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.01 < v.length <= 1.0:
            return v.normalized()


class Cards:
    """Карточки листвы одной породы: ячейки атласа, ориентация, «книжка» или крест."""

    def __init__(self, B, atlas, species, leaf, crown, rng):
        g = atlas["grid"][0]
        row = atlas["rows"][species]["row"]
        px = 0.5 / atlas["size"]
        self.cells = [(c / g + px, 1.0 - (row + 1) / g + px, 1.0 / g - 2 * px, 1.0 / g - 2 * px) for c in range(g)]
        self.B, self.leaf, self.crown, self.rng = B, leaf, crown, rng
        self.count = 0

    def add(self, p, axis, hint, size):
        rng, crown = self.rng, self.crown
        o = crown.out(p + axis * size * 0.5)
        a = axis.normalized()
        ao = a.dot(o)
        if ao > 0:                                  # прижать к поверхности кроны: меньше торчащих наружу карточек
            a = (a - self.leaf.hug * ao * o).normalized()
        w = hint - hint.dot(a) * a
        w = w.normalized() if w.length > 1e-4 else perpendicular(a)
        if w.dot(o) < 0:
            w = -w
        u0, v0, du, dv = self.cells[rng.randrange(len(self.cells))]
        if rng.random() < 0.5:                      # зеркально
            u0, du = u0 + du, -du
        self.col = (rng.random(), crown.depth(p + a * size * 0.5), 1.0, 1.0)
        if rng.random() < self.leaf.cross:          # крест: вторая плоскость повёрнута на 90° вокруг оси
            for wi in (w, a.cross(w)):
                e = a.cross(wi)
                q = [p - e * size / 2, p + e * size / 2, p + e * size / 2 + a * size, p - e * size / 2 + a * size]
                self._quad(q, [(u0, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0, v0 + dv)],
                           wi if wi.dot(o) >= 0 else -wi)
        else:
            e = a.cross(w)
            f = -w * size * self.rng.uniform(0.12, 0.25)   # края книжки опущены — выпуклостью к зрителю
            lb, mb, rb = p - e * size / 2 + f, p, p + e * size / 2 + f
            lt, mt, rt = lb + a * size, mb + a * size, rb + a * size
            self._quad([lb, mb, mt, lt], [(u0, v0), (u0 + du / 2, v0), (u0 + du / 2, v0 + dv), (u0, v0 + dv)], w)
            self._quad([mb, rb, rt, mt], [(u0 + du / 2, v0), (u0 + du, v0), (u0 + du, v0 + dv), (u0 + du / 2, v0 + dv)], w)
        self.count += 1

    def _quad(self, q, uvs, facing):
        # порядок обхода — лицом к facing; нормали вершин — наполовину от центра кроны
        n = (q[1] - q[0]).cross(q[3] - q[0])
        if n.dot(facing) < 0:
            q, uvs = [q[1], q[0], q[3], q[2]], [uvs[1], uvs[0], uvs[3], uvs[2]]
        idx = [self.B.v(x) for x in q]
        nrm = [(facing.normalized() * 0.45 + self.crown.out(x) * 0.55).normalized() for x in q]
        self.B.face(idx, 1, uvs, nrm, self.col)


def foliage(B, sk, v, atlas, rng):
    leaf = LEAF[v.species]
    # точки листвы: веточки instancer и тонкие части ветвей
    thin = []
    for i, idx in enumerate(sk.prims):
        for j in idx:
            if sk.R[j] < leaf.leafy_r and sk.P[j][2] > leaf.min_z:
                thin.append(j)
    pts = [Vector(sk.P[j]) for j in thin] + [q for _, q, _, _, _ in sk.inst]
    crown = Crown(pts)
    cards = Cards(B, atlas, v.species, leaf, crown, rng)
    scales = sorted(sc for *_, sc in sk.inst) or [1.0]
    med = scales[len(scales) // 2]
    # (1) веточки instancer: spray карточек вдоль воображаемой веточки, изогнутой наружу и вверх
    for _, q, upv, nv, sc in sk.inst:
        if q.z < leaf.min_z:
            continue
        size0 = leaf.card * min(1.25, max(0.8, math.sqrt(sc / med)))
        twig = (upv + 0.35 * crown.out(q) + 0.25 * UP).normalized()
        if leaf.twig:
            L = leaf.spray_len
            tube(B, [q, q + twig * L * 0.5, q + twig * L], [TWIG_R, TWIG_R * 0.6, 0.0], rng)
        for k in range(leaf.spray):
            t = k / max(1, leaf.spray) * rng.uniform(0.8, 1.2)
            p = q + twig * leaf.spray_len * t + rand_unit(rng).cross(twig) * leaf.spray_len * 0.35 * t
            ax = twig if k == 0 else (twig + rand_unit(rng).cross(twig) * rng.uniform(0.45, 1.0)).normalized()
            hint = crown.out(p) + 0.4 * UP + 0.5 * nv * rng.choice((-1, 1)) + 0.5 * rand_unit(rng)
            cards.add(p, ax, hint, size0 * rng.uniform(0.85, 1.15))
    n_inst = cards.count
    # (2) тонкие ветви: карточки с шагом step (филлотаксис 137,5°) и на концах ветвей
    golden = math.radians(137.5)
    for i, idx in enumerate(sk.prims):
        acc, psi = rng.uniform(0.0, leaf.step), rng.uniform(0.0, 2 * math.pi)
        for a, b in zip(idx, idx[1:]):
            pa, pb = Vector(sk.P[a]), Vector(sk.P[b])
            acc += (pb - pa).length
            if sk.R[b] >= leaf.leafy_r or pb.z < leaf.min_z or acc < leaf.step:
                continue
            acc = rng.uniform(-0.2, 0.2) * leaf.step
            t = (pb - pa).normalized()
            n0 = perpendicular(t)
            side = math.cos(psi) * n0 + math.sin(psi) * t.cross(n0)
            psi += golden
            phi = math.radians(rng.uniform(30, 65))
            ax = (math.cos(phi) * t + math.sin(phi) * side + 0.2 * UP + 0.25 * crown.out(pb)).normalized()
            hint = crown.out(pb) + 0.4 * UP + 0.5 * rand_unit(rng)
            cards.add(pb, ax, hint, leaf.card * rng.uniform(0.8, 1.1))
        if not sk.children[i] and len(idx) > 1:
            pe, pp = Vector(sk.P[idx[-1]]), Vector(sk.P[idx[max(0, len(idx) - 4)]])
            if pe.z >= leaf.min_z:
                t = (pe - pp).normalized()
                cards.add(pe - t * 0.05, (t + 0.2 * crown.out(pe)).normalized(),
                          crown.out(pe) + 0.4 * UP + 0.4 * rand_unit(rng), leaf.card * rng.uniform(0.9, 1.15))
    return crown, n_inst, cards.count - n_inst


# ---------- превью ----------

def figure():
    """Масштабная фигура человека 1,8 м — только для превью."""
    mat = bk.material("figure", (0.55, 0.12, 0.1))
    parts = [bk.box("leg", -0.07, 0.07, -0.2, -0.04, 0.0, 0.85, mat), bk.box("leg", -0.07, 0.07, 0.04, 0.2, 0.0, 0.85, mat),
             bk.box("torso", -0.12, 0.12, -0.22, 0.22, 0.85, 1.5, mat),
             bk.box("arm", -0.06, 0.06, -0.3, -0.22, 0.8, 1.48, mat), bk.box("arm", -0.06, 0.06, 0.22, 0.3, 0.8, 1.48, mat),
             bk.lathe("head", (0.0, 0.0), [(0.12 * math.sin(math.pi * k / 8), 1.56 + 0.12 - 0.12 * math.cos(math.pi * k / 8))
                                           for k in range(9)], mat, seg=16)]
    return bk.join(parts, "Figure")


def preview_materials(obj, atlas, trees):
    """Слотам — текстуры: кора (Diffuse, UV в метрах ≈ плитка 1 м) и атлас с альфой (clip)."""
    bark_key = trees["species_bark"][obj["species"]]
    for slot, path in ((0, trees["bark"][bark_key]["maps"]["Diffuse"]), (1, atlas["diffuse"])):
        m = bpy.data.materials.new(f"preview_{slot}")
        if not m.node_tree:            # Blender 5: узлы у материала всегда; раньше — включить
            m.use_nodes = True
        nt = m.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(os.path.join(bk.REPO, path))
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if slot == 1:
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            for prop, val in (("blend_method", "CLIP"), ("alpha_threshold", 0.5)):  # Workbench: отсечение по альфе
                try:
                    setattr(m, prop, val)
                except (AttributeError, TypeError) as e:
                    print(f"[tree] WARNING {prop}: {e}")
        nt.nodes.active = tex
        obj.data.materials[slot] = m


def previews(name, obj, crown, height, atlas, trees):
    preview_materials(obj, atlas, trees)
    fig = figure()
    fig.location = (0.0, -(crown.size[0] / 2 + 1.5), 0.0)
    g = bk.box("ground", -60, 60, -60, 60, -0.05, 0.0, bk.material("ground", (0.2, 0.24, 0.14)))
    g.hide_select = True
    s = bpy.context.scene
    s.display.shading.color_type = "TEXTURE"
    s.display.shading.light = "STUDIO"
    h, cw = height, crown.size[0]
    lens = 50.0
    k = 18.0 / lens                 # tan половины угла по высоте кадра (кадр 960 × 1280, датчик 36 мм — по высоте)
    dist = max(0.6 * h / k, 0.6 * cw / (k * 0.75)) + cw / 2
    edge = cw / 2 + 2.0             # пешеход у края кроны, смотрит вверх; крупный план — половина кроны
    views = {"side": ((dist * 0.3, -dist, h * 0.5), (0.0, 0.0, h * 0.5), (960, 1280), lens),
             "ground": ((edge * 0.5, -edge * 0.87, 1.6), (0.0, 0.0, h * 0.6), (960, 1280), 16.0),
             "crown": ((cw * 0.25, -(cw / 2 + 0.35 * h), h * 0.72), (0.0, 0.0, h * 0.72), (1280, 960), 50.0)}
    out = []
    for view, (eye, target, size, ln) in views.items():
        out.append(_render(f"tree_{name}_{view}", eye, target, size, ln))
    return out


def _render(name, eye, target, size, lens):
    """Как bl_krom.render_preview, но цвет — из текстур (листва — по альфе)."""
    s = bpy.context.scene
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    s.collection.objects.link(cam)
    cam.location = eye
    cam.data.lens = lens
    cam.data.clip_end = 5000
    bk.look_at(cam, target)
    s.camera = cam
    if s.world is None:
        s.world = bpy.data.worlds.new("Preview")
    s.world.color = (0.75, 0.8, 0.86)
    s.render.engine = "BLENDER_WORKBENCH"
    s.display.shading.show_shadows = True
    s.display.shading.show_cavity = False
    s.render.resolution_x, s.render.resolution_y = size
    s.render.filepath = os.path.join(bk.PREVIEW_DIR, f"{name}.png")
    os.makedirs(bk.PREVIEW_DIR, exist_ok=True)
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    print(f"[tree] preview {s.render.filepath}")
    return s.render.filepath


# ---------- выгрузка и проверка ----------

def export_glb(obj, name):
    """Как bl_krom.export_glb (Y-вверх glTF, метры), плюс цвет вершин COLOR_0 — его bl_krom не выгружает."""
    os.makedirs(bk.BUILD_DIR, exist_ok=True)
    path = os.path.join(bk.BUILD_DIR, f"{name}.glb")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=True,
                              export_yup=True, export_materials="EXPORT", export_cameras=False, export_lights=False,
                              export_normals=True, export_vertex_color="ACTIVE")
    print(f"[tree] export {path}")
    return path


def check_glb(path):
    """Открыть glb заново: габариты, слоты, треугольники."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo = Vector((1e9, 1e9, 1e9))
    hi = -lo
    mats, tris, cols, uvs = set(), 0, set(), set()
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
        mats |= {m.name for m in o.data.materials if m}
        tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
        cols |= {a.name for a in o.data.color_attributes}
        uvs |= {u.name for u in o.data.uv_layers}
    # нормали листвы доехали отогнутыми: у плоских карточек угловые нормали совпали бы с нормалью грани (cos = 1)
    dots = []
    for o in objs:
        me = o.data
        leaves = {i for i, m in enumerate(me.materials) if m and m.name.startswith("leaves")}
        cn = me.corner_normals
        for p in me.polygons:
            if p.material_index in leaves:
                dots += [cn[k].vector.dot(p.normal) for k in p.loop_indices]
    bend = sum(dots) / len(dots) if dots else 1.0
    print(f"[tree] check {os.path.basename(path)}: объектов {len(objs)}, слоты {sorted(mats)}, треугольников {tris}, "
          f"UV {sorted(uvs)}, цвет {sorted(cols)}, cos(нормаль листвы, грань) {bend:.2f}, "
          f"X {lo.x:.2f}…{hi.x:.2f}, Y {lo.y:.2f}…{hi.y:.2f}, Z {lo.z:.2f}…{hi.z:.2f}")
    return {"mats": sorted(mats), "tris": tris, "uv": sorted(uvs), "color": sorted(cols),
            "leaf_normal_cos": round(bend, 3), "lo": [round(x, 2) for x in lo], "hi": [round(x, 2) for x in hi]}


# ---------- вариант ----------

def build(name, v, atlas, trees):
    rng = random.Random(zlib.crc32(name.encode()))
    bk.reset_scene()
    sk = Skeleton(v)
    B = Builder()
    n_br = branches(B, sk, v, rng)
    crown, n_inst, n_branch = foliage(B, sk, v, atlas, rng)
    asset = f"SM_Tree_{name}"
    mats = [bk.material("bark", (0.23, 0.19, 0.15)), bk.material("leaves", (0.15, 0.28, 0.08))]
    obj = B.to_object(asset, mats)
    obj["species"] = v.species
    height = max(p[2] for p in B.verts)
    tb, tl = B.tris(0), B.tris(1)
    stats = {"asset": asset, "species": v.species, "src": v.src, "height_m": round(height, 2),
             "branches": n_br, "cards": n_inst + n_branch, "cards_inst": n_inst, "cards_branch": n_branch,
             "tris_bark": tb, "tris_leaves": tl, "trunk_d_cm": round(2 * float(sk.R[sk.prims[0][0]]) * 100, 1)}
    print(f"[tree] {name}: высота {height:.2f} м, ветвей {n_br}, карточек {n_inst}+{n_branch}, "
          f"треугольников кора {tb} / листва {tl}")
    path = export_glb(obj, asset)
    stats["previews"] = [os.path.relpath(p, bk.REPO).replace("\\", "/")
                         for p in previews(name, obj, crown, height, atlas, trees)]
    stats["check"] = ck = check_glb(path)
    stats["crown_m"] = round(max(ck["hi"][0] - ck["lo"][0], ck["hi"][1] - ck["lo"][1]), 1)  # по габаритам, с карточками
    return stats


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    todo = [k for k in VARIANTS if not argv or k in argv]
    if not todo:
        raise SystemExit(f"[tree] нет варианта {argv}; есть: {list(VARIANTS)}")
    with open(TREES_JSON, encoding="utf-8") as f:
        trees = json.load(f)
    path = os.path.join(bk.BUILD_DIR, "trees_report.json")
    report = {}
    if os.path.exists(path):                       # частичный прогон дополняет сводку, а не затирает
        with open(path, encoding="utf-8") as f:
            old = json.load(f)
        report = {r["asset"]: r for r in (old if isinstance(old, list) else old.values())}
    for k in todo:
        st = build(k, VARIANTS[k], trees["atlas"], trees)
        report[st["asset"]] = st
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(sorted(report.items())), f, ensure_ascii=False, indent=2)
    print(f"[tree] report {path}")


main()
