"""pskov_church.py — генератор «псковского храма» XIV–XVI вв. (D-036): храм, отдельная звонница, ограда с воротами —
скриптом Blender по планам krom_plan.PskovChurchPlan / PskovBelfryPlan (D-018, D-019).

    python scripts/bl_run.py scripts/blender/pskov_church.py                 # все храмы krom_plan.CHURCHES
    python scripts/bl_run.py scripts/blender/pskov_church.py -- Kozmy        # один (PskovChurchPlan.key)
    python scripts/bl_run.py scripts/blender/pskov_church.py -- Kozmy --no-render

Выгрузка — build/blender/SM_<key>.glb (храм с оградой и воротами) и SM_<key звонницы>.glb (в UE их ставит
scripts/heroes_krom.py), превью — media/renders/blender/<key>_*.png (оба здания на своих местах).
Типология — параметрами плана: четверик с покрытием четырёхскатным, восьмискатным, шестнадцатискатным или
позакомарным; лопатки и ползучие арочки; 1–3 апсиды (полукруглые с конусной кровлей, прямоугольные с односкатной);
барабан с луковичной или шлемовидной главой, поясами и щелевыми окнами; пристройки (притвор, приделы, паперти,
крыльцо) с односкатной, щипцовой или вальмовой кровлей, окнами, дверями, сквозными арками, бровками и столбами;
стена звона с пролётами на круглых или прямоугольных столпах (на отдельной палатке или на стене храма); ограда
по земле heightmap и ворота с проездом и проходом. Размеры — из плана (источники записаны там), здесь только детали
«на глаз»: ширина лопаток, выносы карнизов, пояса, профили глав.
Прототип — scripts/blender/paromenye.py (его не трогаем: он выгружает Пароменье сам); общие приёмы перенесены сюда.
Оси: u — на восток по оси храма, v — к югу, z — от земли в center (у звонницы — в base). Ограда строится по
refs/dem/heightmap_L_Krom.png: после пересчёта рельефа храм нужно выгрузить заново.
Материалы — слоты по ключам krom_plan.COLORS: побелка wall, кровли — plan.roof_mat, глава — ChurchDome.mat, кресты
gold, двери и балки wood, стёкла glass, отливы ограды tin, кровля ворот — ChurchGate.mat_roof.
Храм, ещё не внесённый в CHURCHES (до приёмки), выгружается по ключу (`-- Mironositsy`): план ищется среди
PskovChurchPlan модуля krom_plan, звонницы — среди PskovBelfryPlan с тем же началом ключа. Черновик плана до вставки
в krom_plan — `-- Varlaam --plan build/varlaam_refs/plan.py`: файл исполняется в пространстве имён krom_plan (текст —
готовый раздел krom_plan, его потом дописывают в конец модуля как есть). Звонница может быть
надвратной башней (krom_plan.GateBelfryPlan): ярусы с низом z0 (TierAnnex, TierZvon), главы и купол со шпилем
(ChurchDome kind="spire"); профиль "hemisphere" — полусферическая глава с шейкой, DomeBall.apple_mat — цвет яблока.
Пролёты звона разной ширины — krom_plan.ZvonBays: widths (просветы) и piers (ширины столпов), раскладка по длине стены.
Ярус-восьмерик — krom_plan.TierOctagon в annexes храма или blocks звонницы (отличается полем chamfer): гранёные стенки
со сквозным арочным проёмом в каждой грани, решётки, рельефные арки, карниз, низкая восьмискатная кровля под барабан
главы, колокол. Арка пристройки может нести пятое поле — глубину выреза, м ((фасад, s, ширина, пята, глубина));
без него — как раньше (на фасадах N и S не глубже 2,5 м), глубже самой пристройки — проход насквозь.
Новые поля читаются через getattr: у прежних планов их нет, их выгрузка не меняется.
"""
import math
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402
import krom_plan  # noqa: E402
from bl_krom import M, Openings, band  # noqa: E402

HEIGHTMAP = os.path.join(bk.REPO, "refs", "dem", "heightmap_L_Krom.png")
HALF = 1008                    # heightmap: пиксель (строка y + HALF, столбец x + HALF), метры от собора


class Ground:
    """Земля Landscape из heightmap_L_Krom (16 бит: z = (p − 32768) / 128), билинейно."""

    def __init__(self):
        img = bpy.data.images.load(HEIGHTMAP)
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        a = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(a)
        self.z = (a.reshape(h, w, img.channels)[::-1, :, 0].astype(np.float64) * 65535.0 - 32768.0) / 128.0
        bpy.data.images.remove(img)

    def at(self, x, y):
        n = self.z.shape[0] - 2                                 # у края Landscape — последний пиксель, без переноса
        fy, fx = min(max(y + HALF, 0.0), n), min(max(x + HALF, 0.0), n)
        i, j = int(math.floor(fy)), int(math.floor(fx))
        a, b = fy - i, fx - j
        z = self.z
        return float(z[i, j] * (1 - a) * (1 - b) + z[i + 1, j] * a * (1 - b) + z[i, j + 1] * (1 - a) * b
                     + z[i + 1, j + 1] * a * b)


def local(center, yaw, x, y):
    """Точка мира (x — север, y — восток) → оси здания (u, v)."""
    t = math.radians(yaw)
    dx, dy = x - center[0], y - center[1]
    return dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)


def faces(u0, u1, v0, v1):
    """Фасады прямоугольника в плане; s — слева направо, если смотреть снаружи."""
    c = ((u0 + u1) / 2, (v0 + v1) / 2)
    return {"W": bk.Frame.between((u0, v0), (u0, v1), c), "N": bk.Frame.between((u1, v0), (u0, v0), c),
            "E": bk.Frame.between((u1, v1), (u1, v0), c), "S": bk.Frame.between((u0, v1), (u1, v1), c)}


def bar(name, p0, p1, w, mat):
    """Брус квадратного сечения w между точками p0 и p1 (u, v, z) — балки, перила, решётки."""
    d = [b - a for a, b in zip(p0, p1)]
    L = math.sqrt(sum(x * x for x in d))
    ax = [x / L for x in d]
    ref = (0.0, 0.0, 1.0) if abs(ax[2]) < 0.9 else (1.0, 0.0, 0.0)
    n1 = (ax[1] * ref[2] - ax[2] * ref[1], ax[2] * ref[0] - ax[0] * ref[2], ax[0] * ref[1] - ax[1] * ref[0])
    k = math.sqrt(sum(x * x for x in n1))
    n1 = [x / k for x in n1]
    n2 = (ax[1] * n1[2] - ax[2] * n1[1], ax[2] * n1[0] - ax[0] * n1[2], ax[0] * n1[1] - ax[1] * n1[0])
    h = w / 2
    ring = [[h * (a * n1[i] + b * n2[i]) for i in range(3)] for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    verts = [tuple(p0[i] + r[i] for i in range(3)) for r in ring] + [tuple(p1[i] + r[i] for i in range(3)) for r in ring]
    return bk.mesh(name, verts, [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]], mat)


def ribbon(fr, pts, t, d0, d1, mat, name="relief"):
    """Рельефная лента толщиной t по ломаной [(s, z)] на фасаде fr (арочки, бровки)."""
    poly = [(s, z + t / 2) for s, z in pts] + [(s, z - t / 2) for s, z in reversed(pts)]
    return bk.extrude(name, fr, poly, d0, d1, mat)


def cross8(u, v, z0, h, th=None, mat="gold"):
    """Восьмиконечный крест: перекладины вдоль v, нижняя — северным концом вверх."""
    th = th or max(0.06, 0.045 * h)
    fr = bk.Frame((u, v), (0.0, 1.0), (1.0, 0.0))
    polys = [bk.rect(-th / 2, th / 2, z0, z0 + h),
             bk.rect(-0.17 * h, 0.17 * h, z0 + 0.86 * h - th / 2, z0 + 0.86 * h + th / 2),
             bk.rect(-0.3 * h, 0.3 * h, z0 + 0.66 * h - th / 2, z0 + 0.66 * h + th / 2)]
    a, half, zf = math.radians(25), 0.18 * h, z0 + 0.3 * h
    along, perp = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
    polys.append([(sa * half * along[0] + sp * th / 2 * perp[0], zf + sa * half * along[1] + sp * th / 2 * perp[1])
                  for sa, sp in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    return [bk.extrude("cross", fr, p, -th / 2, th / 2, M[mat]) for p in polys]


def ball(u, v, zc, r, mat):
    return bk.lathe("apple", (u, v), [(r * math.sin(math.pi * i / 12), zc - r * math.cos(math.pi * i / 12))
                                      for i in range(13)], M[mat], seg=20)


def keel(sc, w, z0, h):
    """Килевидная арка на фасаде (s, z): прямые бока до 0,5 h, дальше вогнутые дуги к острию (как в paromenye.py)."""
    side = [(0.5, 0.5), (0.42, 0.7), (0.25, 0.83), (0.08, 0.93)]
    right = [(sc + k * w, z0 + m * h) for k, m in side]
    left = [(sc - k * w, z0 + m * h) for k, m in reversed(side)]
    return [(sc - w / 2, z0), (sc + w / 2, z0)] + right + [(sc, z0 + h)] + left


def keel_line(sc, w, z0, h):
    """Середина бровки: килевидная линия от левой пяты через острие к правой."""
    k = keel(sc, w, z0, h)
    return [k[0]] + k[6:] + k[2:6] + [k[1]]


# ---------- главы ----------

# профили глав (доля высоты от низа главки до яблока, доля наибольшего радиуса); луковица — по фото-телеобъективу
# главы Козьмы и Дамиана (S-64, 678 мм экв., почти без перспективы): широкая, наибольший ⌀ на 0,24 высоты, острый верх
PROFILES = {
    "onion": ((0.0, 0.957), (0.054, 0.977), (0.163, 0.996), (0.24, 1.0), (0.3, 0.985), (0.36, 0.93), (0.446, 0.83),
              (0.533, 0.63), (0.62, 0.43), (0.707, 0.25), (0.79, 0.145), (0.88, 0.093), (0.967, 0.05), (1.0, 0.04)),
    "helmet": ((0.0, 0.97), (0.15, 1.0), (0.35, 0.97), (0.55, 0.85), (0.72, 0.62), (0.86, 0.36), (0.95, 0.15),
               (1.0, 0.05)),
    # купол со шпилем (надвратная колокольня Мироносицкого кладбища, фото S-81): низкий купол до 0,17 высоты, дальше
    # тонкий шпиль, сужающийся к яблоку
    "spire": ((0.0, 1.0), (0.05, 0.93), (0.1, 0.72), (0.14, 0.45), (0.17, 0.2), (0.21, 0.12), (0.4, 0.09),
              (0.7, 0.06), (1.0, 0.03)),
    # полусферическая глава с шейкой под шаром-главкой (Жён-Мироносиц, фото S-81: высота купола ≈0,6 ширины,
    # шейка ≈0,8 м)
    "hemisphere": ((0.0, 1.0), (0.1, 0.99), (0.25, 0.95), (0.4, 0.86), (0.55, 0.72), (0.66, 0.52), (0.74, 0.3),
                   (0.79, 0.12), (0.83, 0.08), (1.0, 0.08)),
}


def dome(d):
    """Барабан с поясами (аркатурка под карнизом, поребрик и бегунец ниже), щелевыми окнами под треугольными
    бровками, карниз-юбка, главка по профилю, яблоко, крест."""
    c, r = (d.u, d.v), d.drum_d / 2
    body = bk.lathe("drum", c, [(r, d.z0), (r, d.z_lip - 0.02)], M["wall"], seg=64)
    op, parts = Openings(recess=0.45), []
    if d.windows:
        n, w, z0, z1 = d.windows
        for k in range(n):
            a = 2 * math.pi * (k + 0.5) / n
            fr = bk.Frame.radial(c, r, a)
            op.slit(fr, 0.0, w, z0, z1)
            parts.append(bk.extrude("brow", fr, [(-w / 2 - 0.25, z1 + 0.15), (w / 2 + 0.25, z1 + 0.15),
                                                 (0.0, z1 + 0.55)], -0.05, 0.1, M["wall"]))
    if d.bands:
        zl = d.z_lip
        for z0, z1, pr in ((zl - 1.62, zl - 1.5, 0.06), (zl - 1.3, zl - 1.12, 0.06), (zl - 0.98, zl - 0.9, 0.06)):
            parts.append(bk.lathe("drum_band", c, [(r - 0.1, z0), (r + pr, z0), (r + pr, z1), (r - 0.1, z1)], M["wall"],
                                  seg=64, closed=True, smooth=False))
        n = max(16, int(2 * math.pi * r / 0.8))
        w = 2 * math.pi * r / n
        for k in range(n):                                   # аркатурка под карнизом
            fr = bk.Frame.radial(c, r, 2 * math.pi * k / n)
            parts.append(bk.extrude("arcature", fr, bk.arch_frame(0.0, w - 0.16, zl - 0.85, zl - 0.85 + 0.45, 0.07, 6),
                                    -0.05, 0.06, M["wall"]))
    ring = (d.ring_d or d.drum_d + 0.4) / 2
    parts.append(bk.lathe("ring", c, [(r - 0.2, d.z_lip - 0.05), (ring, d.z_lip - 0.05), (ring, d.z_lip + 0.1),
                                      (r - 0.2, d.z_lip + 0.1)], M[d.mat], seg=64, closed=True, smooth=False))
    rmax, z0 = d.onion_d / 2, d.z_lip + 0.1
    H = d.z_apple - d.apple_d / 2 - z0
    prof = PROFILES[d.kind]
    top = [(k * rmax, z0 + h * H) for h, k in bk.spline(prof, 3)]
    parts.append(bk.lathe("onion", c, top + [(0.0, z0 + H + 0.02)], M[d.mat], seg=64))
    parts.append(ball(d.u, d.v, d.z_apple, d.apple_d / 2, getattr(d, "apple_mat", "gold")))
    zc = d.z_apple + d.apple_d / 2 - 0.02
    parts += cross8(d.u, d.v, zc, d.z_top - zc)
    return op.apply(body) + parts


# ---------- четверик ----------

def bays(p):
    """Прясла четверика: (u0, u1, v0, v1, боковое прясло по u, по v, середина u, v)."""
    u0, u1, v0, v1 = p.quad
    su, sv = (u1 - u0) * (1 - p.mid_bay) / 2, (v1 - v0) * (1 - p.mid_bay) / 2
    return u0, u1, v0, v1, su, sv, (u0 + u1) / 2, (v0 + v1) / 2


def roof_height(p, u, v):
    """Верх кровли четверика в точке (u, v) (за стенами — продолжение плоскостей на свес)."""
    u0, u1, v0, v1, su, sv, uc, vc = bays(p)
    zq, zg, zs = p.z_quad, p.z_gable, p.z_shoulder or p.z_quad
    mu, mv = (u1 - u0) / 2 - su, (v1 - v0) / 2 - sv            # полуширина среднего прясла
    if p.cover == "gable8":                                     # крест из двух щипцовых кровель
        return max(zg - (zg - zq) * abs(v - vc) / ((v1 - v0) / 2), zg - (zg - zq) * abs(u - uc) / ((u1 - u0) / 2))
    if p.cover == "trefoil16":
        a = min(u - u0, u1 - u) / su
        b = min(v - v0, v1 - v) / sv
        h = zq + (zs - zq) * min(1.0, max(a, b))              # полущипцы боковых лопастей, ендовы по диагоналям углов
        if abs(u - uc) <= mu + 1e-9:
            h = max(h, zs + (zg - zs) * (1 - abs(u - uc) / mu))
        if abs(v - vc) <= mv + 1e-9:
            h = max(h, zs + (zg - zs) * (1 - abs(v - vc) / mv))
        return h
    if p.cover == "zakomary":                                   # своды прясел: полуциркульные арки на обоих направлениях
        h = zq
        for c, w, top in ((u0 + su / 2, su, zs), (uc, 2 * mu, zg), (u1 - su / 2, su, zs)):
            t = 1 - ((u - c) / (w / 2)) ** 2
            if t > 0:
                h = max(h, zq + (top - zq) * math.sqrt(t))
        for c, w, top in ((v0 + sv / 2, sv, zs), (vc, 2 * mv, zg), (v1 - sv / 2, sv, zs)):
            t = 1 - ((v - c) / (w / 2)) ** 2
            if t > 0:
                h = max(h, zq + (top - zq) * math.sqrt(t))
        return h
    raise ValueError(p.cover)


def heightfield(name, fn, us, vs, thick, mat):
    """Кровля-плита по высотам fn(u, v) на сетке us × vs: у каждой клетки диагональ выбирается по высоте в её
    середине (так рёбра конька и ендовы ложатся на сетку); снизу — та же поверхность ниже на thick."""
    nu, nv = len(us), len(vs)
    top = [(u, v, fn(u, v)) for v in vs for u in us]
    verts = top + [(u, v, z - thick) for u, v, z in top]
    n = len(top)

    def i(a, b):
        return b * nu + a
    faces_ = []
    for b in range(nv - 1):
        for a in range(nu - 1):
            q = [i(a, b), i(a + 1, b), i(a + 1, b + 1), i(a, b + 1)]
            zc = fn((us[a] + us[a + 1]) / 2, (vs[b] + vs[b + 1]) / 2)
            d1 = abs((top[q[0]][2] + top[q[2]][2]) / 2 - zc)
            d2 = abs((top[q[1]][2] + top[q[3]][2]) / 2 - zc)
            tris = [[q[0], q[1], q[2]], [q[0], q[2], q[3]]] if d1 <= d2 else [[q[0], q[1], q[3]], [q[1], q[2], q[3]]]
            faces_ += tris + [[x + n for x in reversed(t)] for t in tris]
    ring = [i(a, 0) for a in range(nu)] + [i(nu - 1, b) for b in range(1, nv)] + \
        [i(a, nv - 1) for a in range(nu - 2, -1, -1)] + [i(0, b) for b in range(nv - 2, 0, -1)]
    for k in range(len(ring)):
        a, b = ring[k], ring[(k + 1) % len(ring)]
        faces_.append([a, b, b + n, a + n])
    return bk.mesh(name, verts, faces_, mat)


def grid(p, oh):
    """Линии сетки кровли: стены, края среднего прясла, середина, свес (у позакомарного — дуги подробно)."""
    u0, u1, v0, v1, su, sv, uc, vc = bays(p)
    us = {u0 - oh, u0, u0 + su, uc, u1 - su, u1, u1 + oh}
    vs = {v0 - oh, v0, v0 + sv, vc, v1 - sv, v1, v1 + oh}
    if p.cover == "zakomary":
        for a, b in ((u0, u0 + su), (u0 + su, u1 - su), (u1 - su, u1)):
            us |= {a + (b - a) * k / 12 for k in range(13)}
        for a, b in ((v0, v0 + sv), (v0 + sv, v1 - sv), (v1 - sv, v1)):
            vs |= {a + (b - a) * k / 12 for k in range(13)}
    return sorted(us), sorted(vs)


def quad(p):
    """Четверик: стены с верхом по покрытию, лопатки по углам и краям среднего прясла, ползучие арочки
    (трёхлопастные в среднем прясле), окна, круглые ниши, кровля-плита со свесом."""
    u0, u1, v0, v1, su, sv, uc, vc = bays(p)
    zf = p.z_foot
    fr = faces(u0, u1, v0, v1)
    oh, parts = 0.55, []
    wall_t = 1.4
    for side, f in fr.items():
        L = f.length
        side_bay = su if side in "NS" else sv
        ss = sorted({0.0, side_bay, L / 2, L - side_bay, L} | ({L * k / 24 for k in range(25)}
                                                                  if p.cover == "zakomary" else set()))
        if p.cover == "hip":
            prof = [(s, p.z_quad) for s in (0.0, L)]
        else:
            prof = [(s, roof_height(p, *f.p(s, 0.0)[:2]) - 0.1) for s in ss]
        poly = [(0.0, zf), (L, zf)] + [(s, z) for s, z in reversed(prof)]
        body = bk.extrude("quad_wall", f, poly, -wall_t, 0.0, M["wall"])
        op = Openings(recess=0.6)
        for w_side, ds, w, sill, spring in p.windows:
            if w_side == side:
                op.window(f, L / 2 + ds, w, sill, spring, frame=False)
        for o_side, z, dd in p.oculi:
            if o_side == side:
                circ = [(L / 2 + dd / 2 * math.cos(2 * math.pi * k / 20), z + dd / 2 * math.sin(2 * math.pi * k / 20))
                        for k in range(20)]
                op.cutters.append(bk.extrude("cut", f, circ, -0.18, 0.5, M["wall"]))
        parts += op.apply(body)

        def top_at(s):
            return p.z_quad if p.cover == "hip" else roof_height(p, *f.p(s, 0.0)[:2])
        for s0, s1 in ((-0.12, 0.8), (side_bay - 0.45, side_bay + 0.45), (L - side_bay - 0.45, L - side_bay + 0.45),
                       (L - 0.8, L + 0.12)):                                           # лопатки
            zt = min(top_at(max(0.0, s0)), top_at(min(L, s1))) - 0.35
            parts.append(bk.extrude("lopatka", f, bk.rect(s0, s1, zf, zt), -0.1, 0.13, M["wall"]))
        if p.cover in ("trefoil16", "gable8", "zakomary"):                             # ползучие арочки
            zs = p.z_shoulder or p.z_quad
            a0, a1 = 0.8, side_bay - 0.45
            w = a1 - a0
            for lo, hi, flip in ((a0, a1, False), (L - a1, L - a0, True)):
                pts = [(0.0, p.z_quad - 1.7), (0.35, p.z_quad - 0.95), (0.62, zs - 1.05), (0.8, zs - 0.62),
                       (1.0, zs - 1.0)]
                pts = [(lo + (1 - x if flip else x) * w, z) for x, z in pts]
                parts.append(ribbon(f, bk.spline(sorted(pts), 3), 0.14, -0.05, 0.09, M["wall"], "lobe"))
            h = L / 2 - side_bay - 0.45
            c = L / 2
            zg = p.z_gable
            pts = [(-1.0, zs - 1.6), (-0.8, zs - 0.8), (-0.6, zs - 0.5), (-0.46, zs - 0.75), (-0.3, zg - 1.9),
                   (0.0, zg - 1.2), (0.3, zg - 1.9), (0.46, zs - 0.75), (0.6, zs - 0.5), (0.8, zs - 0.8), (1.0, zs - 1.6)]
            parts.append(ribbon(f, bk.spline([(c + x * h, z) for x, z in pts], 3), 0.14, -0.05, 0.09, M["wall"], "lobe"))
    if p.cover == "hip":
        parts.append(bk.hip_roof("quad_roof", u0 - oh, u1 + oh, v0 - oh, v1 + oh, p.z_quad + 0.2,
                                 p.z_gable - p.z_quad, 0.25, M[p.roof_mat]))
    else:
        us, vs = grid(p, oh)
        parts.append(heightfield("quad_roof", lambda u, v: roof_height(p, u, v) + 0.12, us, vs, 0.25, M[p.roof_mat]))
    return parts


# ---------- апсиды ----------

def apses(p):
    """Апсиды: полукруглые — стены, пояс поребрика под карнизом, арочки-валики по верху, конусная кровля; прямоугольные —
    коробка с односкатной кровлей от четверика."""
    ue, out = p.quad[1], []
    zf = p.z_foot
    for a in p.apses:
        vc, r = (a.v0 + a.v1) / 2, (a.v1 - a.v0) / 2
        if a.kind == "rect":
            body = bk.box("apse_rect", ue - 0.4, a.tip, a.v0, a.v1, zf, a.z, M["wall"])
            out += [body, band(ue - 0.4, a.tip, a.v0, a.v1, a.z - 0.55, a.z - 0.35, 0.06),
                    bk.slab("apse_roof", [(ue - 0.2, a.v0 - 0.3, a.z + a.rise), (ue - 0.2, a.v1 + 0.3, a.z + a.rise),
                                          (a.tip + 0.4, a.v1 + 0.3, a.z - 0.05), (a.tip + 0.4, a.v0 - 0.3, a.z - 0.05)],
                            0.22, M[p.roof_mat])]
            continue
        uc = a.tip - r

        def outline(g, uc=uc, vc=vc, r=r, a=a):
            return [(ue - 0.4, a.v0 - g), (uc, a.v0 - g)] + \
                [(uc + (r + g) * math.cos(t), vc + (r + g) * math.sin(t))
                 for t in (-math.pi / 2 + math.pi * k / 20 for k in range(1, 20))] + [(uc, a.v1 + g), (ue - 0.4, a.v1 + g)]
        body = bk.prism("apse", outline(0.0), zf, a.z - 0.35, M["wall"])
        op = Openings(recess=0.5)
        op.window(bk.Frame.radial((uc, vc), r, 0.0), 0.0, 0.7, a.z - 4.2, a.z - 3.0, frame=False)
        parts = [bk.prism("apse_band", outline(0.07), a.z - 1.35, a.z - 1.05, M["wall"]),
                 bk.prism("apse_cornice", outline(0.25), a.z - 0.35, a.z, M["wall"])]
        if a.arches:                                           # арочки-валики по верху до половины высоты
            n = a.arches
            for k in range(n):
                t0, t1 = -math.pi / 2 + math.pi * k / n, -math.pi / 2 + math.pi * (k + 1) / n
                tc, w = (t0 + t1) / 2, r * (t1 - t0)
                fr = bk.Frame.radial((uc, vc), r, tc)
                zs = a.z - 1.6 - w / 2
                parts.append(bk.extrude("apse_arch", fr, bk.arch_frame(0.0, w - 0.3, zs, zs, 0.14, 8), -0.05, 0.1,
                                        M["wall"]))
                if k:
                    parts.append(bk.extrude("valik", bk.Frame.radial((uc, vc), r, t0), bk.rect(-0.12, 0.12, a.z / 2, zs),
                                            -0.05, 0.1, M["wall"]))
        g = 0.45
        parts.append(bk.lathe("apse_roof", (uc, vc), [(r + g, a.z - 0.2), (r + g, a.z), (0.0, a.z + a.rise),
                                                      (0.0, a.z - 0.2)], M[p.roof_mat], seg=40,
                              closed=True, arc=(-math.pi / 2, math.pi / 2), smooth=False))
        parts.append(bk.slab("apse_roof_w", [(ue - 0.3, vc - r - g, a.z), (uc, vc - r - g, a.z), (uc, vc, a.z + a.rise),
                                             (ue - 0.3, vc, a.z + a.rise)], 0.2, M[p.roof_mat]))
        parts.append(bk.slab("apse_roof_w", [(ue - 0.3, vc, a.z + a.rise), (uc, vc, a.z + a.rise),
                                             (uc, vc + r + g, a.z), (ue - 0.3, vc + r + g, a.z)], 0.2, M[p.roof_mat]))
        out += op.apply(body) + parts
    return out


# ---------- пристройки ----------

def annex_top(a, u, v):
    """Верх кровли пристройки в точке (u, v) (без свеса)."""
    lo, hi = a.z_eave, a.z_high
    if a.roof == "lean_n":
        return lo + (hi - lo) * (v - a.v0) / (a.v1 - a.v0)
    if a.roof == "lean_s":
        return hi - (hi - lo) * (v - a.v0) / (a.v1 - a.v0)
    if a.roof == "lean_w":
        return lo + (hi - lo) * (u - a.u0) / (a.u1 - a.u0)
    if a.roof == "lean_e":
        return hi - (hi - lo) * (u - a.u0) / (a.u1 - a.u0)
    if a.roof == "gable_u":
        half = (a.v1 - a.ridge) if v >= a.ridge else (a.ridge - a.v0)
        return hi - (hi - lo) * abs(v - a.ridge) / half
    if a.roof == "gable_v":
        half = (a.u1 - a.ridge) if u >= a.ridge else (a.ridge - a.u0)
        return hi - (hi - lo) * abs(u - a.ridge) / half
    return lo


def annex(a, zf, oh=0.4):
    """Пристройка: стены с верхом по кровле (торцы щипцовых — щипцы), проёмы, сквозные арки (каждая — своим вырезом),
    бровки под карнизом, круглые столбы у арок, кровля-плита со свесом."""
    fr = faces(a.u0, a.u1, a.v0, a.v1)
    parts = []
    if a.roof == "hip":
        body = bk.box(a.name, a.u0, a.u1, a.v0, a.v1, zf, a.z_eave, M["wall"])
    elif a.roof in ("gable_u", "lean_n", "lean_s"):           # профиль по v, выдавлен вдоль u
        vs = sorted({a.v0, a.v1} | ({a.ridge} if a.roof == "gable_u" else set()))
        f = fr["W"]
        poly = [(0.0, zf), (a.v1 - a.v0, zf)] + [(v - a.v0, annex_top(a, a.u0, v) - 0.08) for v in reversed(vs)]
        body = bk.extrude(a.name, f, poly, -(a.u1 - a.u0), 0.0, M["wall"])
    else:                                                     # профиль по u, выдавлен вдоль v
        us = sorted({a.u0, a.u1} | ({a.ridge} if a.roof == "gable_v" else set()))
        f = fr["S"]
        poly = [(0.0, zf), (a.u1 - a.u0, zf)] + [(u - a.u0, annex_top(a, u, a.v1) - 0.08) for u in reversed(us)]
        body = bk.extrude(a.name, f, poly, -(a.v1 - a.v0), 0.0, M["wall"])
    op = Openings(recess=0.45)
    for side, s, w, sill, spring in a.windows:
        op.window(fr[side], s, w, sill, spring, frame=False)
    for side, s, w, h in a.doors:
        door = bk.arch(s, w, zf + 0.1, h - w / 2)
        op.cutters.append(bk.extrude("cut", fr[side], [(x, max(z, -0.3)) for x, z in door], -0.5, 0.5, M["wall"]))
        op.parts.append(bk.extrude("door", fr[side], bk.arch(s, w, -0.3, h - w / 2), -0.52, -0.42, M["wood"]))
    body = op.apply(body)
    parts += body[1:]
    body = body[0]
    for arc in a.arches:                                      # сквозные арки: по одной булевой операции
        side, s, w, spring = arc[:4]
        f = fr[side]
        depth = (a.u1 - a.u0 if side in "WE" else a.v1 - a.v0) - (0.5 if side == "W" else 0.05)
        if side in "NS":
            depth = min(depth, 2.5)
        if len(arc) > 4:                                      # пятое поле — глубина выреза (проход насквозь)
            depth = arc[4]
        prof = bk.arch(s, w, -0.3, spring, 16)
        bk.cut(body, [bk.extrude("cut", f, prof, -depth, 0.5, M["wall"])])
        parts.append(bk.extrude("archivolt", f, bk.arch_frame(s, w, spring, spring, 0.3, 16), -0.05, 0.12, M["wall"]))
    for side, s, r, h in a.piers:
        f = fr[side]
        c = f.p(s, 0.0, 0.25)[:2]
        parts += [bk.lathe("pier", c, [(r, -0.3), (r, h)], M["wall"], seg=24),
                  bk.lathe("pier_cap", c, [(r + 0.1, h), (r + 0.1, h + 0.25)], M["wall"], seg=24),
                  bk.lathe("pier_base", c, [(r + 0.12, -0.3), (r + 0.12, 0.3)], M["wall"], seg=24)]
    for side, n in a.brows:                                   # бровки-кокошники под карнизом
        f = fr[side]
        L = f.length
        w = L / n
        z0 = annex_top(a, *f.p(L / 2, 0.0)[:2]) - 1.25
        for k in range(n):
            parts.append(ribbon(f, keel_line((k + 0.5) * w, w * 0.62, z0, 0.9), 0.12, -0.05, 0.08, M["wall"], "brow"))
    # кровля
    mat = M[a.mat_roof]
    t = 0.2
    if a.roof == "hip":
        parts.append(bk.hip_roof(f"{a.name}_roof", a.u0 - oh, a.u1 + oh, a.v0 - oh, a.v1 + oh, a.z_eave + 0.1,
                                 a.z_high - a.z_eave, t, mat))
    elif a.roof.startswith("lean"):
        u0, u1, v0, v1 = a.u0 - oh, a.u1 + oh, a.v0 - oh, a.v1 + oh
        if a.roof == "lean_n":
            v1 = a.v1 + 0.1
        elif a.roof == "lean_s":
            v0 = a.v0 - 0.1
        elif a.roof == "lean_w":
            u1 = a.u1 + 0.1
        else:
            u0 = a.u0 - 0.1

        def z(u, v):
            return annex_top(a, u, v) + 0.1
        parts.append(bk.slab(f"{a.name}_roof", [(u0, v0, z(u0, v0)), (u1, v0, z(u1, v0)), (u1, v1, z(u1, v1)),
                                                (u0, v1, z(u0, v1))], t, mat))
    elif a.roof == "gable_u":
        r = a.ridge
        for va, vb in ((a.v0 - oh, r), (r, a.v1 + oh)):
            za, zb = annex_top(a, a.u0, va) + 0.1, annex_top(a, a.u0, vb) + 0.1
            parts.append(bk.slab(f"{a.name}_roof", [(a.u0 - oh, va, za), (a.u1 + 0.1, va, za), (a.u1 + 0.1, vb, zb),
                                                    (a.u0 - oh, vb, zb)], t, mat))
    else:                                                     # gable_v
        r = a.ridge
        for ua, ub in ((a.u0 - oh, r), (r, a.u1 + oh)):
            za, zb = annex_top(a, ua, a.v0) + 0.1, annex_top(a, ub, a.v0) + 0.1
            parts.append(bk.slab(f"{a.name}_roof", [(ua, a.v0 - oh, za), (ub, a.v0 - oh, zb), (ub, a.v1 + oh, zb),
                                                    (ua, a.v1 + oh, za)], t, mat))
    return [body] + parts


# ---------- восьмерик ----------

BELL = ((0.0, 1.0), (0.04, 1.0), (0.12, 0.86), (0.3, 0.72), (0.55, 0.64), (0.8, 0.6), (0.92, 0.52), (1.0, 0.36),
        (1.0, 0.0))                                           # колокол: (доля высоты от губы, доля радиуса губы)


def chamfer_ring(a, g=0.0):
    """Восьмерик TierOctagon в плане: прямоугольник u0…u1 × v0…v1 со срезанными под 45° углами (катет chamfer, 0 —
    как у правильного восьмерика по меньшей стороне), раздвинутый наружу на g (g < 0 — внутрь); 8 точек (u, v)
    по кругу, первая — восточная грань у севера."""
    c = (a.chamfer or min(a.u1 - a.u0, a.v1 - a.v0) / (2 + math.sqrt(2))) + g * (2 - math.sqrt(2))
    u0, u1, v0, v1 = a.u0 - g, a.u1 + g, a.v0 - g, a.v1 + g
    return [(u1, v0 + c), (u1, v1 - c), (u1 - c, v1), (u0 + c, v1), (u0, v1 - c), (u0, v0 + c), (u0 + c, v0),
            (u1 - c, v0)]


def octagon(a):
    """Восьмерик (krom_plan.TierOctagon): грани — стенки толщиной wall от z0 до z_eave, каждая своим телом (углы
    перекрываются внутри, как стены четверика), в каждой — сквозной арочный проём (своя булева операция) с решёткой
    и отливом; рельефные арки по граням, пол на 0,1 ниже подоконников, двухступенчатый карниз, низкая восьмискатная
    кровля от свеса до z_high (верх — восьмерик r_top под барабан главы), колокол ⌀bell на балке."""
    ring = chamfer_ring(a)
    c = ((a.u0 + a.u1) / 2, (a.v0 + a.v1) / 2)
    t, ze = a.wall, a.z_eave
    parts = []
    for k in range(8):
        f = bk.Frame.between(ring[k], ring[(k + 1) % 8], c)
        L = f.length
        body = bk.extrude("tier_wall", f, bk.rect(0.0, L, a.z0, ze), -t, 0.0, M["wall"])
        if a.opening:
            w, sill, spring = a.opening
            s = L / 2
            bk.cut(body, [bk.extrude("cut", f, bk.arch(s, w, sill, spring, 16), -t - 0.5, 0.5, M["wall"])])
            parts.append(bk.extrude("tier_sill", f, bk.rect(s - w / 2 - 0.12, s + w / 2 + 0.12, sill - 0.08, sill),
                                    -0.1, 0.22, M[a.mat_roof]))
            m = max(3, int(w / 0.16))                          # решётка в проёме, посередине толщи стены
            for i in range(1, m):
                x = s - w / 2 + w * i / m
                ztop = spring + math.sqrt(max(0.0, (w / 2) ** 2 - (x - s) ** 2)) - 0.03
                parts.append(bar("grille", f.p(x, sill, -t / 2), f.p(x, ztop, -t / 2), 0.03, M["dark"]))
            for zz in (sill + 0.9, spring):
                parts.append(bar("grille", f.p(s - w / 2, zz, -t / 2), f.p(s + w / 2, zz, -t / 2), 0.04, M["dark"]))
        parts.append(body)
        if a.arcs:                                             # рельефная арка по грани: пяты в углах, верх посередине
            z0, z1 = a.arcs
            pts = [(L / 2 - (L / 2 - 0.1) * math.cos(math.pi * i / 12), z0 + (z1 - z0) * math.sin(math.pi * i / 12))
                   for i in range(13)]
            parts.append(ribbon(f, pts, 0.12, -0.05, 0.08, M["wall"], "tier_arc"))
    inner = chamfer_ring(a, -t + 0.05)
    if a.opening:
        zf = a.opening[1] - 0.1
        parts.append(bk.prism("tier_floor", inner, zf - 0.2, zf, M["wall"]))
    parts += [bk.prism("tier_cornice", chamfer_ring(a, 0.15), ze - 0.5, ze - 0.25, M["wall"]),
              bk.prism("tier_cornice", chamfer_ring(a, a.cornice), ze - 0.25, ze, M["wall"])]
    outer = chamfer_ring(a, a.cornice + 0.12)
    k = a.r_top / max(math.dist(p, c) for p in outer)
    top = [(c[0] + (u - c[0]) * k, c[1] + (v - c[1]) * k) for u, v in outer]
    parts.append(bk.loft("tier_roof", [[(u, v, ze - 0.05) for u, v in outer], [(u, v, ze + 0.12) for u, v in outer],
                                       [(u, v, a.z_high) for u, v in top]], M[a.mat_roof]))
    if a.bell:                                                 # колокол на балке поперёк яруса
        zb = ze - 0.6
        hu = (a.u1 - a.u0) / 2 - t + 0.15
        parts.append(bk.box("beam", c[0] - hu, c[0] + hu, c[1] - 0.09, c[1] + 0.09, zb - 0.09, zb + 0.09, M["wood"]))
        d, zt = a.bell, zb - 0.1
        parts.append(bk.lathe("bell", c, [(kk * d / 2, zt - 0.95 * d + tt * 0.95 * d) for tt, kk in BELL], M["bronze"],
                              seg=24))
    return parts


# ---------- стена звона ----------

def zvon(z, zf):
    """Стена звона: глухая до подоконников, пролёты — внизу общим вырезом с круглыми столбами и капителями, наверху —
    арками; над каждым пролётом щипец с коньком поперёк стены; балки, перила в пролётах, балкон."""
    L, t = z.u1 - z.u0, z.v1 - z.v0
    n = z.spans
    col = z.column or 1.2
    cap_w = col + 0.3
    a = (L - 2 * z.end_pier - (n - 1) * cap_w) / n            # просвет арки между капителями
    s_free = (L - 2 * z.end_pier - (n - 1) * col) / n         # просвет между столбами
    pitch = a + cap_w
    centers = [z.end_pier + a / 2 + k * pitch for k in range(n)]       # середины пролётов, s от u0
    piers = [z.end_pier + a + cap_w / 2 + k * pitch for k in range(n - 1)]
    A, S, C = [a] * n, [s_free] * n, [col] * (n - 1)            # по пролётам: просвет арки, просвет, ширина столпа
    e0 = e1 = z.end_pier                                        # крайние столпы у u0 и у u1
    if getattr(z, "widths", ()):                                # пролёты разной ширины (ZvonBays): масштаб — по L
        k = L / (sum(z.widths) + sum(z.piers))
        S, C = [w * k for w in z.widths], [w * k for w in z.piers[1:-1]]
        e0, e1 = z.piers[0] * k, z.piers[-1] * k
        A = [w - 0.3 for w in S]                                # капители выступают на 0,15 с каждой стороны
        centers, piers, s = [], [], e0
        for i in range(n):
            centers.append(s + S[i] / 2)
            s += S[i]
            if i < n - 1:
                piers.append(s + C[i] / 2)
                s += C[i]
    f = bk.Frame.between((z.u0, z.v1), (z.u1, z.v1), ((z.u0 + z.u1) / 2, z.v0))   # s — от u0, наружу — +v
    edges = [0.0] + piers + [L]                                 # края щипцов: концы стены и середины столпов
    prof = [(0.0, z.z_eave)]
    if z.gables:
        for k, c in enumerate(centers):
            prof += [(c, z.z_ridge - 0.35), (edges[k + 1], z.z_eave)]
    else:
        prof += [(L, z.z_eave)]
    poly = [(0.0, zf), (L, zf)] + list(reversed(prof))
    body = bk.extrude("zvon", f, poly, -t, 0.0, M["wall"])
    low = bk.rect(e0, L - e1, z.z_sill, z.z_cap)
    bk.cut(body, [bk.extrude("cut", f, low, -t - 0.5, 0.5, M["wall"])])
    arches = [bk.extrude("cut", f, bk.arch(c, A[k], z.z_cap - 0.01, z.z_spring, 16), -t - 0.5, 0.5, M["wall"])
              for k, c in enumerate(centers)]
    bk.cut(body, arches)
    parts = [body]
    vm = (z.v0 + z.v1) / 2
    for j, s in enumerate(piers):                              # круглые столбы с капителями
        u, cj = z.u0 + s, C[j]
        cw = cj + 0.3
        if z.column:
            parts += [bk.lathe("column", (u, vm), [(cj / 2, z.z_sill - 0.05), (cj / 2 * 1.08, (z.z_sill + z.z_cap) / 2),
                                                    (cj / 2, z.z_cap)], M["wall"], seg=24),
                      bk.box("capital", u - cw / 2 - 0.06, u + cw / 2 + 0.06, z.v0 - 0.06, z.v1 + 0.06,
                             z.z_cap - 0.02, z.z_spring + 0.05, M["wall"])]
        else:
            parts.append(bk.box("pier", u - cj / 2, u + cj / 2, z.v0, z.v1, z.z_sill - 0.05, z.z_spring, M["wall"]))
    for sgn in (0, 1):                                         # капители крайних столпов
        u = z.u0 + (e0 - 0.15 if sgn == 0 else L - e1 - 0.15)
        parts.append(bk.box("capital", u, u + 0.3, z.v0 - 0.08, z.v1 + 0.08, z.z_cap - 0.02, z.z_spring + 0.05,
                            M["wall"]))
    for k, c in enumerate(centers):                            # архивольты, подоконники, балки, перила
        a, s_free = A[k], S[k]
        parts.append(bk.extrude("archivolt", f, bk.arch_frame(c, a, z.z_spring, z.z_spring, 0.18, 12), -0.02, 0.1,
                                M["wall"]))
        u = z.u0 + c
        parts.append(bk.box("sill", u - s_free / 2 - 0.1, u + s_free / 2 + 0.1, z.v0 - 0.12, z.v1 + 0.12,
                            z.z_sill - 0.15, z.z_sill, M["wall"]))
        for zb in z.beams:
            parts.append(bk.box("beam", u - a / 2 - 0.2, u + a / 2 + 0.2, vm - 0.09, vm + 0.09, zb - 0.09, zb + 0.09,
                                M["wood"]))
        for v in (z.v0 + 0.15, z.v1 - 0.15):
            u0, u1, zr = u - s_free / 2 + 0.05, u + s_free / 2 - 0.05, z.z_sill + 0.9
            parts += [bar("rail", (u0, v, zr), (u1, v, zr), 0.08, M["wood"]),
                      bar("rail", (u0, v, z.z_sill + 0.05), (u1, v, zr), 0.06, M["wood"]),
                      bar("rail", (u0, v, zr), (u1, v, z.z_sill + 0.05), 0.06, M["wood"])]
    for k, d in enumerate(z.bells):
        if d and k < n:
            u = z.u0 + centers[k]
            zt = z.beams[-1] - 0.1 if z.beams else z.z_spring - 0.3
            prof_b = ((0.0, 1.0), (0.04, 1.0), (0.12, 0.86), (0.3, 0.72), (0.55, 0.64), (0.8, 0.6), (0.92, 0.52),
                      (1.0, 0.36), (1.0, 0.0))
            parts.append(bk.lathe("bell", (u, vm), [(kk * d / 2, zt - 0.95 * d + tt * 0.95 * d) for tt, kk in prof_b],
                                  M["bronze"], seg=24))
    # кровли щипцов: скаты вдоль u над каждым пролётом, свес поперёк стены
    oh, ot = 0.65, 0.2
    mat = M[z.mat_roof]
    if z.gables:
        for k, c in enumerate(centers):
            e0, e1, uc = z.u0 + edges[k], z.u0 + edges[k + 1], z.u0 + c
            ua, ub = e0 - (0.5 if k == 0 else 0.0), e1 + (0.5 if k == n - 1 else 0.0)
            za = z.z_ridge - (z.z_ridge - z.z_eave) * (uc - ua) / (uc - e0)
            zb = z.z_ridge - (z.z_ridge - z.z_eave) * (ub - uc) / (e1 - uc)
            parts += [bk.slab("zvon_roof", [(ua, z.v0 - oh, za + 0.1), (uc, z.v0 - oh, z.z_ridge + 0.1),
                                            (uc, z.v1 + oh, z.z_ridge + 0.1), (ua, z.v1 + oh, za + 0.1)], ot, mat),
                      bk.slab("zvon_roof", [(uc, z.v0 - oh, z.z_ridge + 0.1), (ub, z.v0 - oh, zb + 0.1),
                                            (ub, z.v1 + oh, zb + 0.1), (uc, z.v1 + oh, z.z_ridge + 0.1)], ot, mat)]
    else:
        parts.append(bk.hip_roof("zvon_roof", z.u0 - oh, z.u1 + oh, z.v0 - oh, z.v1 + oh, z.z_eave + 0.1,
                                 z.z_ridge - z.z_eave, ot, mat))
    if z.balcony:                                              # деревянный балкон вдоль стены на уровне пролётов
        side, dep = z.balcony
        va, vb = (z.v1, z.v1 + dep) if side == "S" else (z.v0 - dep, z.v0)
        zb = z.z_sill - 0.15
        parts.append(bk.box("balcony", z.u0 + 0.3, z.u1 - 0.3, va, vb, zb - 0.15, zb, M["wood"]))
        vo = vb - 0.06 if side == "S" else va + 0.06
        m = max(2, int((L - 0.6) / 1.4))
        for k in range(m + 1):
            u = z.u0 + 0.35 + (L - 0.7) * k / m
            parts.append(bk.box("post", u - 0.05, u + 0.05, vo - 0.05, vo + 0.05, zb, zb + 1.0, M["wood"]))
        for zr in (zb + 0.5, zb + 0.95):
            parts.append(bk.box("rail", z.u0 + 0.3, z.u1 - 0.3, vo - 0.04, vo + 0.04, zr, zr + 0.07, M["wood"]))
        for uu in (z.u0 + 0.3, z.u1 - 0.36):
            parts.append(bk.box("rail", uu, uu + 0.06, va, vb, zb + 0.95, zb + 1.02, M["wood"]))
        for k in range(4):                                     # подкосы
            u = z.u0 + 1.0 + (L - 2.0) * k / 3
            vw = z.v1 if side == "S" else z.v0
            parts.append(bar("strut", (u, vw, zb - 1.2), (u, vo, zb - 0.15), 0.12, M["wood"]))
    return parts


# ---------- ограда и ворота ----------

def fence(p, ground, g0):
    """Ограда по ломаным плана: кладка толщиной fence_t высотой fence_h от земли, кусками по ≈3 м, с плоскими
    лопатками снаружи и двускатным отливом (tin); низ — на 0,8 м в земле."""
    t, h = p.fence_t, p.fence_h
    parts = []
    for line in p.fence:
        pts = [local(p.center, p.yaw, *xy) for xy in line]
        c = (0.0, 0.0)                                         # двор — вокруг храма
        for (x0, y0), (x1, y1), a, b in zip(line, line[1:], pts, pts[1:]):
            L = math.dist(a, b)
            n = max(1, int(L / 3.0))
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            nrm = (-d[1], d[0])
            if (c[0] - a[0]) * nrm[0] + (c[1] - a[1]) * nrm[1] > 0:     # наружу — от середины двора
                nrm = (-nrm[0], -nrm[1])
            for k in range(n):
                s0, s1 = L * k / n, L * (k + 1) / n
                e0, e1 = (s0 - (t / 2 if k == 0 else 0.0)), (s1 + (t / 2 if k == n - 1 else 0.0))
                za = ground.at(x0 + (x1 - x0) * s0 / L, y0 + (y1 - y0) * s0 / L) - g0
                zb = ground.at(x0 + (x1 - x0) * s1 / L, y0 + (y1 - y0) * s1 / L) - g0

                def q(s, off, z):
                    return (a[0] + d[0] * s + nrm[0] * off, a[1] + d[1] * s + nrm[1] * off, z)
                verts = [q(e0, -t / 2, za - 0.8), q(e1, -t / 2, zb - 0.8), q(e1, t / 2, zb - 0.8), q(e0, t / 2, za - 0.8),
                         q(e0, -t / 2, za + h - 0.12), q(e1, -t / 2, zb + h - 0.12), q(e1, t / 2, zb + h - 0.12),
                         q(e0, t / 2, za + h - 0.12)]
                parts.append(bk.mesh("fence", verts, [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5],
                                                      [2, 3, 7, 6], [3, 0, 4, 7]], M["wall"]))
                cap = [q(e0, -t / 2 - 0.08, za + h - 0.14), q(e1, -t / 2 - 0.08, zb + h - 0.14),
                       q(e1, t / 2 + 0.08, zb + h - 0.14), q(e0, t / 2 + 0.08, za + h - 0.14),
                       q(e0, 0.0, za + h + 0.08), q(e1, 0.0, zb + h + 0.08)]
                parts.append(bk.mesh("fence_cap", cap, [[0, 1, 2, 3], [0, 1, 5, 4], [3, 2, 5, 4], [0, 4, 3], [1, 2, 5]],
                                     M["tin"]))
                sm, zm = (s0 + s1) / 2, (za + zb) / 2
                parts.append(bk.mesh("fence_pilaster", [q(sm - 0.3, t / 2 - 0.02, zm - 0.8), q(sm + 0.3, t / 2 - 0.02, zm - 0.8),
                                                        q(sm + 0.3, t / 2 + 0.07, zm - 0.8), q(sm - 0.3, t / 2 + 0.07, zm - 0.8),
                                                        q(sm - 0.3, t / 2 - 0.02, zm + h - 0.2), q(sm + 0.3, t / 2 - 0.02, zm + h - 0.2),
                                                        q(sm + 0.3, t / 2 + 0.07, zm + h - 0.2), q(sm - 0.3, t / 2 + 0.07, zm + h - 0.2)],
                                     [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]],
                                     M["wall"]))
    return parts


def gate(p, g, ground, g0):
    """Ворота: кладка от a до b толщиной depth внутрь ограды, кровля с коньком вдоль ограды, проезд и проход арками
    насквозь, у арок круглые столбы, ниши на лицевой грани, кованые решётки в проёмах."""
    a, b = local(p.center, p.yaw, *g.a), local(p.center, p.yaw, *g.b)
    L = math.dist(a, b)
    mx, my = (g.a[0] + g.b[0]) / 2, (g.a[1] + g.b[1]) / 2
    zg = ground.at(mx, my) - g0
    inside = (-a[0] - b[0], -a[1] - b[1])                      # к центру храма
    f = bk.Frame.between(a, b, (a[0] + inside[0], a[1] + inside[1]))
    front = p.fence_t / 2                                      # лицевая грань — по наружной грани ограды
    fr = bk.Frame(f.p(0.0, 0.0, front)[:2], f.t, f.n, L)
    body = bk.extrude("gate", fr, bk.rect(-0.1, L + 0.1, zg - 0.8, zg + g.z), -g.depth, 0.0, M["wall"])
    for s, w, spring in g.arches:
        bk.cut(body, [bk.extrude("cut", fr, bk.arch(s, w, zg - 0.3, zg + spring, 16), -g.depth - 0.5, 0.5, M["wall"])])
    parts = [body]
    op = Openings(recess=0.2)
    for s, w, z0, z1, arched in g.niches:
        shape = bk.arch(s, w, zg + z0, zg + z1 - w / 2, 10) if arched else bk.rect(s - w / 2, s + w / 2, zg + z0, zg + z1)
        op.cutters.append(bk.extrude("cut", fr, shape, -0.2, 0.5, M["wall"]))
    parts = op.apply(body) + parts[1:]
    for s, w, spring in g.arches:
        parts.append(bk.extrude("archivolt", fr, bk.arch_frame(s, w, zg + spring, zg + spring, 0.28, 16), -0.02, 0.12,
                                M["wall"]))
        for side in (-1, 1):                                   # столбы у пят
            c = fr.p(s + side * (w / 2 + 0.3), 0.0, 0.3)[:2]
            parts += [bk.lathe("gate_pier", c, [(0.34, zg - 0.3), (0.34, zg + spring - 0.25)], M["wall"], seg=8,
                               smooth=False),
                      bk.lathe("gate_cap", c, [(0.42, zg + spring - 0.25), (0.42, zg + spring)], M["wall"], seg=8,
                               smooth=False)]
        m = max(3, int(w / 0.25))                              # решётка в проёме
        dm = -g.depth / 2
        for k in range(1, m):
            x = s - w / 2 + w * k / m
            ztop = zg + spring + math.sqrt(max(0.0, (w / 2) ** 2 - (x - s) ** 2)) - 0.1
            p0, p1 = fr.p(x, zg, dm), fr.p(x, ztop, dm)
            parts.append(bar("grille", p0, p1, 0.035, M["dark"]))
        for zz in (zg + 0.2, zg + spring - 0.3):
            parts.append(bar("grille", fr.p(s - w / 2, zz, dm), fr.p(s + w / 2, zz, dm), 0.05, M["dark"]))
    ze = zg + g.z
    oh = 0.35
    for d0, d1 in ((oh, -g.depth / 2), (-g.depth / 2, -g.depth - oh)):
        z0 = ze + 0.05 + g.rise * (abs(d0 + g.depth / 2) < 1e-6)
        z1 = ze + 0.05 + g.rise * (abs(d1 + g.depth / 2) < 1e-6)
        parts.append(bk.slab("gate_roof", [fr.p(-0.4, z0, d0), fr.p(L + 0.4, z0, d0), fr.p(L + 0.4, z1, d1),
                                           fr.p(-0.4, z1, d1)], 0.15, M[g.mat_roof]))
    return parts


# ---------- сборка ----------

def church(p, ground):
    g0 = ground.at(*p.center)
    parts = quad(p) + apses(p)
    for a in p.annexes:
        parts += octagon(a) if hasattr(a, "chamfer") else annex(a, p.z_foot)
    for d in p.domes:
        parts += dome(d)
    if p.zvon:
        parts += zvon(p.zvon, p.z_foot)
    if p.fence:
        parts += fence(p, ground, g0)
    for g in p.gates:
        parts += gate(p, g, ground, g0)
    return parts


def belfry(b):
    """Звонница: объёмы и стена звона от z_foot; у ярусов башни (поле z0 у подклассов плана) низ — z0, главы и
    шпиль — поле domes (подклассы плана, см. krom_plan.GateBelfryPlan)."""
    parts = []
    for a in b.blocks:
        if hasattr(a, "chamfer"):                              # восьмерик (TierOctagon)
            parts += octagon(a)
            continue
        parts += annex(a, b.z_foot if getattr(a, "z0", None) is None else a.z0)
    parts += zvon(b.zvon, b.z_foot if getattr(b.zvon, "z0", None) is None else b.zvon.z0)
    for d in getattr(b, "domes", ()):
        parts += dome(d)
    return parts


def build(objs, name):
    obj = bk.join(objs, name)
    bk.box_uv(obj)
    me = obj.data
    tris = sum(len(q.vertices) - 2 for q in me.polygons)
    print(f"[pskov_church] {len(objs)} тел → {name}: {len(me.vertices)} вершин, {len(me.polygons)} граней, "
          f"≈{tris} треугольников, слоты {[m.name for m in me.materials]}")
    bk.export_glb(obj, name)
    return obj, tris


# ---------- превью и сверка с фото ----------

def render(name, eye, fwd, size, f_px, shift=(0.0, 0.0), roll=0.0):
    """Превью Workbench: камера в осях храма (u, v, z), направление fwd, фокусное в пикселях кадра size, сдвиг главной
    точки shift (пиксели, как у камеры фото), крен roll (°)."""
    from mathutils import Matrix, Vector
    os.makedirs(bk.PREVIEW_DIR, exist_ok=True)
    s = bpy.context.scene
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    s.collection.objects.link(cam)
    cam.location = (eye[0], -eye[1], eye[2])
    w, h = size
    cam.data.sensor_fit = "HORIZONTAL"
    cam.data.sensor_width = 36.0
    cam.data.lens = f_px * 36.0 / w
    cam.data.shift_x = -shift[0] / max(w, h)
    cam.data.shift_y = shift[1] / max(w, h)
    cam.data.clip_end = 5000
    d = Vector((fwd[0], -fwd[1], fwd[2]))
    q = d.to_track_quat("-Z", "Y")
    cam.rotation_euler = (q.to_matrix().to_4x4() @ Matrix.Rotation(math.radians(roll), 4, "Z")).to_euler()
    s.camera = cam
    if os.environ.get("PSKOV_DEBUG"):
        from bpy_extras.object_utils import world_to_camera_view
        s.render.resolution_x, s.render.resolution_y = size
        bpy.context.view_layer.update()
        for tag, q in (("origin", (0.0, 0.0, 0.0)), ("z26.7", (0.0, 0.0, 26.7))):
            c = world_to_camera_view(s, cam, Vector((q[0], -q[1], q[2])))
            print(f"[debug] {name} {tag}: px=({c.x * w:.1f}, {(1 - c.y) * h:.1f})")
    if s.world is None:
        s.world = bpy.data.worlds.new("Preview")
    s.world.color = (0.75, 0.8, 0.86)
    s.render.engine = "BLENDER_WORKBENCH"
    s.display.shading.light = "STUDIO"
    s.display.shading.color_type = "MATERIAL"
    s.display.shading.show_shadows = True
    s.display.shading.show_cavity = True
    s.render.resolution_x, s.render.resolution_y = size
    s.render.filepath = os.path.join(bk.PREVIEW_DIR, f"{name}.png")
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam)
    print(f"[pskov_church] preview {s.render.filepath}")


def photo_views(p, g0):
    """Ракурсы фото Commons с камерами, восстановленными solve.py (build/kozmy_refs/solve.json): (глаз, направление,
    кадр, фокусное px, сдвиг, крен) в осях храма."""
    import json
    path = os.path.join(bk.REPO, "build", f"{p.key.lower()}_refs", "solve.json")
    if not os.path.exists(path):
        return {}
    sol = json.load(open(path, encoding="utf-8"))
    sizes = {"028": (1280, 853), "033": (1280, 806), "021": (1280, 853), "032": (1280, 960), "031": (1280, 853)}
    sizes.update({k: tuple(v) for k, v in sol.get("sizes", {}).items()})
    out = {}
    t = math.radians(p.yaw)
    for key, (X, Y, Z, az, pi, ro, f, dcx, dcy) in sol["cams"].items():
        pi = (pi + 180.0) % 360.0 - 180.0                       # та же ориентация с наклоном в ±90°
        if abs(pi) > 90.0:
            pi, az, ro = math.copysign(180.0, pi) - pi, az + 180.0, ro + 180.0
        ro = (ro + 180.0) % 360.0 - 180.0
        u, v = local(p.center, p.yaw, X, Y)
        a, b = math.radians(az), math.radians(pi)
        dx, dy, dz = math.cos(b) * math.cos(a), math.cos(b) * math.sin(a), math.sin(b)
        du, dv = dx * math.cos(t) + dy * math.sin(t), -dx * math.sin(t) + dy * math.cos(t)
        out[f"photo_{key}"] = ((u, v, Z - g0), (du, dv, dz), sizes.get(key, (1280, 853)), f, (dcx, dcy), ro)
    return out


def terrain(p, ground, g0, half=150.0, step=2.0, z_far=-9.0):
    """Земля для превью (не выгружается): участок heightmap вокруг храма в его осях, дальше — плоскость на z_far
    (ниже самой низкой камеры фото, иначе камера у реки смотрит в её изнанку)."""
    n = int(2 * half / step) + 1
    verts, faces_ = [], []
    t = math.radians(p.yaw)
    for j in range(n):
        for i in range(n):
            u, v = -half + i * step, -half + j * step
            x = p.center[0] + u * math.cos(t) - v * math.sin(t)
            y = p.center[1] + u * math.sin(t) + v * math.cos(t)
            verts.append((u, -v, ground.at(x, y) - g0 - 0.03))
    for j in range(n - 1):
        for i in range(n - 1):
            k = j * n + i
            faces_.append([k, k + 1, k + n + 1, k + n])
    me = bpy.data.meshes.new("terrain")
    me.from_pydata(verts, [], faces_)
    obj = bpy.data.objects.new("terrain", me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(bk.material("ground", (0.12, 0.16, 0.08)))
    far = bk.box("ground_far", -900, 900, -900, 900, z_far - 0.05, z_far, bk.material("ground", (0.12, 0.16, 0.08)))
    far.hide_select = True
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    drafts = [b for a, b in zip(argv, argv[1:]) if a == "--plan"]
    keys = [a for a in argv if not a.startswith("--") and a not in drafts]
    ns = vars(krom_plan)
    for path in drafts:        # черновик раздела krom_plan (--plan файл.py): исполняется в пространстве имён krom_plan
        ns = dict(ns)
        exec(compile(open(path, encoding="utf-8").read(), path, "exec"), ns)
    plans = [c for c in krom_plan.CHURCHES if not keys or c.key in keys]
    # храм, ещё не внесённый в CHURCHES (приёмка, D-036), — по ключу среди планов krom_plan, со своими звонницами
    known = {c.key for c in plans}
    extra = [v for v in ns.values() if isinstance(v, krom_plan.PskovChurchPlan)
             and v.key in keys and v.key not in known]
    belfries = list(krom_plan.CHURCH_BELFRIES) + [
        v for v in ns.values() if isinstance(v, krom_plan.PskovBelfryPlan)
        and v not in krom_plan.CHURCH_BELFRIES and any(v.key.startswith(c.key) for c in extra)]
    for p in plans + extra:
        bk.reset_scene()
        bk.use_colors(krom_plan.COLORS)
        ground = Ground()
        g0 = ground.at(*p.center)
        ch, tris = build(church(p, ground), f"SM_{p.key}")
        bel = [b for b in belfries if b.key.startswith(p.key)]
        for b in bel:
            obj, tb = build(belfry(b), f"SM_{b.key}")
            u, v = local(p.center, p.yaw, *b.center)
            obj.location = (u, -v, ground.at(*b.base) - g0)
            obj.rotation_euler = (0.0, 0.0, -math.radians(b.yaw - p.yaw))
            tris += tb
        print(f"[pskov_church] {p.key}: всего ≈{tris} треугольников")
        if "--no-render" in argv:
            continue
        views = photo_views(p, g0)
        terr = terrain(p, ground, g0, z_far=min([-9.0] + [e[2] - 3.0 for e, *_ in views.values()]))
        t = math.radians(p.yaw)
        for name, (eye, fwd, size, f, shift, roll) in views.items():
            x = p.center[0] + eye[0] * math.cos(t) - eye[1] * math.sin(t)
            y = p.center[1] + eye[0] * math.sin(t) + eye[1] * math.cos(t)
            terr.hide_render = eye[2] < ground.at(x, y) - g0 + 0.3     # камера ниже heightmap (DEM у дороги неточен)
            render(f"{p.key.lower()}_{name}", eye, fwd, size, f, shift, roll)
        terr.hide_render = False
        su = local(p.center, p.yaw, *krom_plan.SREDNYAYA.center)
        krom = (su[0], su[1], ground.at(*krom_plan.SREDNYAYA.base) - g0 + 18.0)
        tgt = (0.0, 0.0, 8.0)
        d = [b - a for a, b in zip(krom, tgt)]
        render(f"{p.key.lower()}_from_krom", krom, d, (1280, 720), 1280 * 200 / 36)
        for name, eye, tgt, lens in (("west", (-60.0, 2.0, 1.7), (0.0, 0.0, 10.0), 28.0),
                                     ("east", (45.0, -18.0, 1.7), (0.0, 0.0, 10.0), 28.0),
                                     ("high", (70.0, -60.0, 45.0), (-8.0, 0.0, 6.0), 35.0)):
            d = [b - a for a, b in zip(eye, tgt)]
            render(f"{p.key.lower()}_{name}", eye, d, (1280, 853), 1280 * lens / 36)


main()
