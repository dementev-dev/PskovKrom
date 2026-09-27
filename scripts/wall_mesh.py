"""wall_mesh.py — геометрия стены по участку krom_plan.WallRun и высотам земли (D-021). Чистый Python, без unreal.

walls_krom.py снимает землю трассой по Landscape в точках WallGeom.probes() и отдаёт высоты в WallGeom.build().
Здесь — звенья с горизонтальным верхом и ступенями, поперечник по WallProfile, проходы, столбы и бойницы.
Сетка — плоские грани, развёртка кубом (1 UV = 1 м), материалы — ключи krom_plan.COLORS (stone, wood).
Без булевых операций: бойницы — промежутки между блоками бруствера, проход — тело, разрезанное на куски.

    python scripts/wall_mesh.py     # самопроверка на ровной и наклонной земле
"""
import math

SAMPLE_M = 2.0     # шаг точек трассы, где снимается земля
STEP_M = 1.0       # звено держит отметку, пока земля двора не уйдёт больше чем на ступень (фото belfry_yard)
EMBED_M = 1.0      # низ звена — под самой низкой землёй под ним
YARD_M = 1.5       # земля двора — в стольких метрах от внутренней грани тела
OUT_M = 6.0        # «снаружи» — для самопроверки стороны двора
END_EXT_M = 2.0    # конец участка у башни уходит в неё
END_EXT = {"Колокольня": 1.0}   # пристройка колокольни несёт свой свес кровли — стена лишь заходит в её кладку
FLOOR_T = 0.08     # настил хода
POST = 0.18        # сечение столба
ROOF_LAP = 0.3     # кровля звена заходит за его края (на ступенях — внахлёст)
ARCH_N = 8         # граней в своде арки
MITER_MAX = 3.0


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a, b):
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class Mesh:
    """Сетка по материалам: parts[key] = (вершины, нормали, uv, треугольники); координаты — метры плана.

    Порядок вершин — как в GeometryScript: нормаль грани = −(v1 − v0) × (v2 − v0) (проверено на append_box)."""

    def __init__(self):
        self.parts = {}

    def quad(self, mat, pts, out):
        """Плоский четырёхугольник; out — примерное направление наружу, по нему выбирается сторона."""
        a, b, c, d = pts
        n = _cross(_sub(b, a), _sub(c, a))
        if _dot(n, n) < 1e-12:
            n = _cross(_sub(c, a), _sub(d, a))
            if _dot(n, n) < 1e-12:
                return
        if _dot(n, out) > 0:
            pts, n = [a, d, c, b], (-n[0], -n[1], -n[2])
        k = math.sqrt(_dot(n, n))
        nrm = (-n[0] / k, -n[1] / k, -n[2] / k)
        u, v = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[max(range(3), key=lambda i: abs(nrm[i]))]
        verts, norms, uvs, tris = self.parts.setdefault(mat, ([], [], [], []))
        i0 = len(verts)
        h = math.hypot(nrm[0], nrm[1])
        if mat == "wood" and 1e-3 < h < abs(nrm[2]):
            # скат кровли: доски тёса (вертикаль текстуры) — вниз по скату, а не вдоль мировой оси, как дала бы
            # проекция по Z; ось u — вдоль карниза
            eave = (-nrm[1] / h, nrm[0] / h, 0.0)
            slope = _cross(nrm, eave)
            for p in pts:
                verts.append(p)
                norms.append(nrm)
                uvs.append((_dot(p, eave), -_dot(p, slope)))
            tris += [(i0, i0 + 1, i0 + 2), (i0, i0 + 2, i0 + 3)]
            return
        for p in pts:
            verts.append(p)
            norms.append(nrm)
            uvs.append((p[u], -p[v]))
        tris += [(i0, i0 + 1, i0 + 2), (i0, i0 + 2, i0 + 3)]

    def triangles(self):
        return sum(len(p[3]) for p in self.parts.values())


class Path:
    """Трасса участка, продлённая в башни на концах. s — путь от начала продлённой трассы, m — нормаль к двору."""

    def __init__(self, run):
        pts = [tuple(p) for p in run.points]
        pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
        self.ext = (0.0 if run.a == "конец" else END_EXT.get(run.a, END_EXT_M),
                    0.0 if run.b == "конец" else END_EXT.get(run.b, END_EXT_M))
        d0, d1 = _dir(pts[0], pts[1]), _dir(pts[-2], pts[-1])
        pts.insert(0, (pts[0][0] - d0[0] * self.ext[0], pts[0][1] - d0[1] * self.ext[0]))
        pts.append((pts[-1][0] + d1[0] * self.ext[1], pts[-1][1] + d1[1] * self.ext[1]))
        pts = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
        self.pts = pts
        self.dirs = [_dir(a, b) for a, b in zip(pts, pts[1:])]
        self.norms = [(-d[1] * run.yard, d[0] * run.yard) for d in self.dirs]
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + math.dist(a, b))
        self.length = self.s[-1]

    def seg(self, s, right=True):
        """Сегмент под путём s; в вершине — следующий (right) или предыдущий."""
        for i in range(len(self.dirs) - 1):
            if s < self.s[i + 1] or (not right and s <= self.s[i + 1]):
                return i
        return len(self.dirs) - 1

    def at(self, s, w=0.0, right=True):
        """Точка трассы на пути s, сдвинутая к двору на w."""
        i = self.seg(s, right)
        d, m, p = self.dirs[i], self.norms[i], self.pts[i]
        k = s - self.s[i]
        return p[0] + d[0] * k + m[0] * w, p[1] + d[1] * k + m[1] * w

    def sub(self, a, b):
        """Отрезок трассы [a, b]: [(точка, сдвиг к двору на 1 м, сегмент следующего куска, путь)]. Во внутренних
        вершинах сдвиг идёт по биссектрисе («на ус»), чтобы грани соседних сегментов сходились без щелей."""
        out = [(self.at(a), self.norms[self.seg(a)], self.seg(a), a)]
        for i in range(1, len(self.pts) - 1):
            if a < self.s[i] < b:
                m0, m1 = self.norms[i - 1], self.norms[i]
                mx, my = m0[0] + m1[0], m0[1] + m1[1]
                L = math.hypot(mx, my)
                if L < 1e-9:
                    continue
                k = min(MITER_MAX, L / max(1e-3, mx * m1[0] + my * m1[1]))
                out.append((self.pts[i], (mx / L * k, my / L * k), i, self.s[i]))
        j = self.seg(b, right=False)
        out.append((self.at(b, right=False), self.norms[j], j, b))
        return out


def _dir(a, b):
    L = math.dist(a, b)
    return (b[0] - a[0]) / L, (b[1] - a[1]) / L


def strip(mesh, path, a, b, w, zb, zt, mat, top_out=(0.0, 0.0, 1.0)):
    """Брус вдоль трассы от a до b: поперёк от w[0] до w[1] (w[0] < w[1]). Низ zb и верх zt — пара отметок
    на w[0] и w[1] (наклон поперёк) или функция пути s (наклон вдоль: свод арки)."""
    if b - a < 1e-3:
        return
    sub = path.sub(a, b)

    def o(k, j, z):
        (px, py), (mx, my), _, s = sub[k]
        return px + mx * w[j], py + my * w[j], z(s) if callable(z) else z[j]

    for k in range(len(sub) - 1):
        mx, my = path.norms[sub[k][2]]
        mesh.quad(mat, [o(k, 0, zt), o(k + 1, 0, zt), o(k + 1, 1, zt), o(k, 1, zt)], top_out)
        mesh.quad(mat, [o(k, 0, zb), o(k + 1, 0, zb), o(k + 1, 1, zb), o(k, 1, zb)], (0.0, 0.0, -1.0))
        mesh.quad(mat, [o(k, 0, zb), o(k + 1, 0, zb), o(k + 1, 0, zt), o(k, 0, zt)], (-mx, -my, 0.0))
        mesh.quad(mat, [o(k, 1, zb), o(k + 1, 1, zb), o(k + 1, 1, zt), o(k, 1, zt)], (mx, my, 0.0))
    d0, d1 = path.dirs[sub[0][2]], path.dirs[sub[-1][2]]
    n = len(sub) - 1
    mesh.quad(mat, [o(0, 0, zb), o(0, 1, zb), o(0, 1, zt), o(0, 0, zt)], (-d0[0], -d0[1], 0.0))
    mesh.quad(mat, [o(n, 0, zb), o(n, 1, zb), o(n, 1, zt), o(n, 0, zt)], (d1[0], d1[1], 0.0))


def minus(a, b, holes):
    """Отрезок [a, b] без отверстий [(h0, h1), ...] — список оставшихся кусков."""
    out, cur = [], a
    for h0, h1 in sorted(holes):
        if h1 <= cur or h0 >= b:
            continue
        if h0 > cur:
            out.append((cur, h0))
        cur = max(cur, h1)
    if cur < b:
        out.append((cur, b))
    return out


def _fill(values):
    """Промахи трассы (None) — ближайшим соседом; если промахнулись все — 0 (земля у собора)."""
    known = [i for i, v in enumerate(values) if v is not None]
    if not known:
        return [0.0] * len(values)
    return [v if v is not None else values[min(known, key=lambda k: abs(k - i))] for i, v in enumerate(values)]


class WallGeom:
    """Стена одного участка: точки для замера земли и сетка по замеренным высотам."""

    PROBES = 5   # на точку трассы: двор, под стеной ×3, снаружи

    def __init__(self, run, gates=()):
        self.run, self.p = run, run.profile
        self.path = Path(run)
        L = self.path.length
        n = max(1, math.ceil(L / SAMPLE_M))
        self.stations = [L * k / n for k in range(n + 1)]
        self.gates = [(s + self.path.ext[0], g) for s, g in gates]   # путь — от начала продлённой трассы
        self.zvena = []

    def probes(self):
        """Точки (x, y), где нужна земля: на каждой точке трассы PROBES штук по порядку."""
        t = self.p.t
        out = []
        for s in self.stations:
            for w in (t + YARD_M, -0.5, t / 2, t + 0.5, -OUT_M):
                out.append(self.path.at(s, w))
        return out

    def build(self, z, level=None):
        """z — высоты земли в точках probes() (None — промах); level — уровень двора для всего участка (земля
        в run.level_at), иначе звенья идут по земле двора. Пол проёмов — всегда по земле у двора. Возвращает Mesh."""
        k = self.PROBES
        yard = _fill(z[0::k])
        under = _fill([min([v for v in z[i * k + 1:i * k + 4] if v is not None], default=None)
                       for i in range(len(self.stations))])
        outside = _fill(z[4::k])
        self.yard_higher = sum(y > o for y, o in zip(yard, outside)) / len(yard)
        self.zvena = self._zvena(yard if level is None else [level] * len(yard), under)
        mesh = Mesh()
        for a, b, level, bottom in self.zvena:
            self._zveno(mesh, a, b, level, bottom, yard)
        return mesh

    def _zvena(self, yard, under):
        """Звенья: (начало, конец, земля двора, низ). Звено растёт, пока разброс земли двора ≤ STEP_M."""
        st, n, out, i = self.stations, len(self.stations), [], 0
        while i < n:
            lo = hi = yard[i]
            j = i + 1
            while j < n and max(hi, yard[j]) - min(lo, yard[j]) <= STEP_M:
                lo, hi = min(lo, yard[j]), max(hi, yard[j])
                j += 1
            a = 0.0 if i == 0 else (st[i - 1] + st[i]) / 2
            b = self.path.length if j >= n else (st[j - 1] + st[j]) / 2
            bottom = min(under[max(0, i - 1):min(n, j + 1)]) - EMBED_M
            out.append((a, b, (lo + hi) / 2, bottom))
            i = j
        return out

    def _ground(self, s, yard):
        st = self.stations
        i = min(range(len(st)), key=lambda k: abs(st[k] - s))
        return yard[i]

    def _opening(self, mesh, s, g, a, b, B, top, yard):
        """Проём g с серединой на пути s в звене [a, b]: под ним — кладка до земли прохода, над ним — свод
        (полуциркульный, если g.arch) до верха тела. «Проход» — насквозь; «дверь» — насквозь, дощатая створка
        в g.depth от двора; «заложен» — ниши глубиной g.depth с обеих сторон; «ниша» — только со двора (амбразура).
        Возвращает занятый отрезок пути."""
        t, half = self.p.t, g.width / 2
        d = min(g.depth, t / 2 - 0.05) if g.kind == "заложен" else min(g.depth, t - 0.3)
        c0, c1 = max(a, s - half), min(b, s + half)
        if c1 - c0 < 1e-3:
            return None
        floor = self._ground(s, yard)
        crown = min(floor + g.height, top - 0.3)
        spring = max(floor + 0.3, crown - half) if g.arch else crown   # низкий проём — свод лучковый

        def soffit(x):
            k = max(0.0, 1.0 - ((x - s) / half) ** 2)
            return spring + (crown - spring) * math.sqrt(k)

        layers = {"проход": [(0.0, t)], "дверь": [(0.0, t)], "заложен": [(0.0, d), (t - d, t)],
                  "ниша": [(t - d, t)]}[g.kind]
        core = {"проход": None, "дверь": None, "заложен": (d, t - d), "ниша": (0.0, t - d)}[g.kind]
        n = ARCH_N if g.arch else 1
        cuts = [c0 + (c1 - c0) * i / n for i in range(n + 1)]
        for w in layers:
            strip(mesh, self.path, c0, c1, w, (B, B), (floor, floor), "stone")
            for x0, x1 in zip(cuts, cuts[1:]):
                strip(mesh, self.path, x0, x1, w, soffit, (top, top), "stone")
        if core:
            strip(mesh, self.path, c0, c1, core, (B, B), (top, top), "stone")
        if g.kind == "дверь":
            for x0, x1 in zip(cuts, cuts[1:]):
                strip(mesh, self.path, x0, x1, (t - d - 0.06, t - d), (floor, floor), soffit, "wood")
        return c0, c1

    def _zveno(self, mesh, a, b, G, B, yard):
        p, path = self.p, self.path
        t = p.t
        top_body = G + p.z_walk
        # тело с проёмами: под проёмом — кладка до земли прохода, над ним — свод до верха тела
        holes = [h for h in (self._opening(mesh, s, g, a, b, B, top_body, yard) for s, g in self.gates) if h]
        for c0, c1 in minus(a, b, holes):
            strip(mesh, path, c0, c1, (0.0, t), (B, B), (top_body, top_body), "stone")
        if not p.roof:
            return
        # бруствер с бойницами до кровли: низ и верх — сплошные, середина — блоки между бойницами
        pt = p.parapet
        step, sw, s0, s1 = p.slit
        zw = top_body
        inner = (self.path.ext[0], self.path.length - self.path.ext[1])   # вне башен
        slits = []
        k = math.ceil((a - inner[0]) / step - 0.5)
        while inner[0] + (k + 0.5) * step < b:
            c = inner[0] + (k + 0.5) * step
            if a + sw < c < b - sw and inner[0] + 1 < c < inner[1] - 1:
                slits.append((c - sw / 2, c + sw / 2))
            k += 1
        strip(mesh, path, a, b, (0.0, pt), (zw, zw), (zw + s0, zw + s0), "stone")
        for c0, c1 in minus(a, b, slits):
            strip(mesh, path, c0, c1, (0.0, pt), (zw + s0, zw + s0), (zw + s1, zw + s1), "stone")
        strip(mesh, path, a, b, (0.0, pt), (zw + s1, zw + s1), (G + p.roof_under(0), G + p.roof_under(pt)), "stone")
        # настил хода
        w_in = pt + p.walk
        strip(mesh, path, a, b, (pt, w_in), (zw, zw), (zw + FLOOR_T, zw + FLOOR_T), "wood")
        # кровля: конёк над внешней гранью, скат во двор; лежит на брустере и столбах
        tan = math.tan(math.radians(p.pitch))
        e0, e1 = -p.eave[0], w_in + p.eave[1]
        top = (G + p.h - tan * e0, G + p.h - tan * e1)
        dz = p.roof_t / math.cos(math.radians(p.pitch))
        ra, rb = max(0.0, a - ROOF_LAP), min(path.length, b + ROOF_LAP)
        strip(mesh, path, ra, rb, (e0, e1), (top[0] - dz, top[1] - dz), top, "wood")
        # столбы по краю хода — от настила до кровли
        k = math.ceil((a - inner[0]) / p.post_step)
        while inner[0] + k * p.post_step < b:
            c = inner[0] + k * p.post_step
            k += 1
            if not (a + POST < c < b - POST and inner[0] < c < inner[1]):
                continue
            w = w_in - POST / 2
            strip(mesh, path, c - POST / 2, c + POST / 2, (w - POST / 2, w + POST / 2), (zw + FLOOR_T,) * 2,
                  (G + p.roof_under(w + POST / 2),) * 2, "wood")


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import krom_plan as plan

    runs = plan.wall_runs()
    gates = plan.wall_gates(runs)
    for r in runs:
        g = WallGeom(r, gates.get(r.name, ()))
        pr = g.probes()
        flat = g.build([0.0] * len(pr))
        assert len(g.zvena) == 1, (r.name, len(g.zvena))                    # ровная земля — одно звено
        slope = g.build([0.05 * g.path.s[0] + 0.05 * i / g.PROBES for i in range(len(pr))])   # уклон ≈ 5 %
        tris = {k: len(v[3]) for k, v in slope.parts.items()}
        steps = len(g.zvena)
        assert all(abs(z1[1] - z2[0]) < 1e-6 for z1, z2 in zip(g.zvena, g.zvena[1:]))
        print(f"{r.name:52} {g.path.length:6.1f} м  ровно {flat.triangles():6} тр., уклон: звеньев {steps:3}, {tris}")
    print("ok")
