"""okolny_plan.py — стена Окольного города по Великой к югу от Ольгинского моста: участки стен (план, как krom_plan).

Чистый Python без `unreal`. krom_plan здесь только читается: типы WallProfile / WallRun, round_tower, геометрия линий.
walls_krom.py строит эти участки вместе со стенами Крома (scene_runs), trees_points.py не сажает на них деревья.

    python scripts/okolny_plan.py     # участки, самопроверка (ассеты, двор выше, сетка на ровной и наклонной земле)

Что это (REFERENCES S-72…S-74 и раздел «Стена Окольного города по Великой»): «Прясло крепостной стены от
Власьевской башни до Мстиславской башни» объекта «Стены Окольного города, XVI в.» (ГИКЭ 2026); по летописи —
каменная стена по Великой 1400–1402 гг., стена Среднего города, потом часть Окольного.
Линии OSM (barrier=city_wall, historic=citywalls), с севера на юг:
  39012957 — 292 м от съезда с Ольгинского моста (Рижский пр., бывший Власьевский спуск) до Профсоюзной улицы
             (бывший Плоский спуск);
  96333698 — 15 м за Профсоюзной, до здания поликлиники (way 61677188 стоит в разрыве линии);
  96333733 — 207 м от поликлиники до Мстиславской башни (way 96333724); последние ≈16 м линии обходят башню по контуру.
Западная стена Крома (way 654691936) уже вся в krom_plan: кончается у съезда с моста, 34 м до этой линии — проезд.

Стена подпорная (фото S-74): со стороны города земля почти у верха — невысокий парапет, с речной стороны — лицо
6–7 м до газона у набережной, контрфорсы. Под кровлей — короткие куски: три у сквера по контурам OSM (building=yes,
3,8 × 13,2 м вплотную к линии с городской стороны; один из них — на фото у Профсоюзной) и у Мстиславской башни (ход,
бойницы и кровля над ходом — ГИКЭ 2026; фото). Двор — город, к востоку от линии (yard = −1, как у стен Крома).
Участки — «Окольный город, первая открытая», «…, первая под кровлей» и т. д. по порядку от моста (10 участков, 498 м).

Рельеф: FABDEM сглаживает перепад в откос шириной ≈30 м, и земля у внешней грани в heightmap лишь на 0,3–1,3 м ниже
городской. FOOT_Z — отметка газона у подошвы с речной стороны: walls_krom.py опускает тело до неё, даже пока рельеф
там выше (тело уходит в откос), а terrain_krom должен срезать землю до неё за внешней гранью — тогда лицо откроется.
Высоты — гипотезы по фото (±1 м), пока нет обмеров; поправлять здесь.
"""
import math
from dataclasses import dataclass

import krom_plan as plan
from krom_plan import WallProfile, WallRun

# Открытая подпорная стена: парапет над землёй города (фото panoramio 137: верх почти вровень с дорожкой сквера);
# толщина видимого верха — гип. («средняя толщина 2 сажени ≈ 4 м» у стен Окольного — о теле, оно ниже земли города)
OPEN = WallProfile(t=3.0, h=0.8, roof=False)
# Под кровлей: бруствер с бойницами, ход, столбы и тёсовая кровля — профиль стен Крома (D-021); толщина — по контурам
# OSM у сквера (3,8 м); ход ≈1 м над городом: z_walk = h − tg25°·(0,9 + 1,5) − 0,13 − 2,1 ≈ 1,05 м (гип.)
ROOFED = WallProfile(t=3.8, h=4.4, walk=1.5)
FOOT_Z = -8.5   # газон у подошвы с речной стороны, м от собора: ≈34,6 абс., ≈4,6 над урезом; набережная ≈0,5 ниже,
#                 нижняя набережная у моста ≈2,5–3 над урезом (S-48); лицо от верха 6–7 м (фото) — всё гип. ±1 м
TOWER_HIT_M = 0.5   # линия OSM ближе этого к контуру башни — дальше она обходит башню, участок кончается
ROOF_OUTLINE_M = 1.0   # контур кровли OSM — не дальше стольких метров от линии (иначе это не кусок стены)
WALL = "Окольный город"
ORDINAL = ("первая", "вторая", "третья", "четвёртая", "пятая", "шестая", "седьмая", "восьмая", "девятая", "десятая")

# Мстиславская башня (way 96333724): круглая, на скале берега; ствол 13,6 м, наружный ⌀ 10,2 м на 3-м ярусе,
# консервационная шатровая крыша с малым уклоном; к реке пять ярусов бойниц, к городу три над землёй. Сейчас в уровне
# она — коробка city_mesh 6,6 м; blockout или герой — следующий шаг. Здесь — контур, в который упирается участок.
MSTISLAVSKAYA = plan.round_tower("Мстиславская", (-894.1, 137.0), 10.2, 15.6, 2.0,
                                 "Окольный город, на скале берега Великой; ствол 13,6 м, ⌀ 10,2; шатёр 2 м гип.")


@dataclass(frozen=True)
class Section:
    """Линия OSM стены по Великой. Кончается «концом» (разрыв линии: улица, здание) или башней tower. roofs — куски
    под кровлей: id контура OSM (way building вдоль линии — кусок от первой до последней его проекции на линию) или
    число — столько метров у конца линии."""
    way: int
    roofs: tuple = ()
    tower: object = None
    note: str = ""


SECTIONS = (
    Section(39012957, (96260903, 95192411, 96333727),
            note="от съезда с моста до Профсоюзной; под кровлей — три контура OSM 3,8 × 13,2 м через ≈95 м; "
                 "южный — на фото у Профсоюзной (Сигачёв 2023, Mavier 2024), северный — на фото с моста (2015)"),
    Section(96333698, note="15 м между спуском Профсоюзной и поликлиникой; кровли на фото нет (гип.)"),
    Section(96333733, (45.0,), MSTISLAVSKAYA,
            note="«наиболее впечатляющий» участок, «на несколько десятков метров укрыта кровлей»; кровля и ход у башни "
                 "— ГИКЭ 2026 и фото; длина под кровлей 45 м гип."),
)
YARD = -1   # город — справа по ходу линий OSM (они идут с севера на юг), к востоку


def towers():
    """Башни стены по Великой, в которые упираются участки (в уровне их пока строит только city_mesh)."""
    return [s.tower for s in SECTIONS if s.tower is not None]


def _length(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _piece(pts, s0, s1):
    """Кусок ломаной между путями s0 < s1: точка на s0, вершины между ними, точка на s1."""
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + math.dist(a, b))

    def at(s):
        i = max(0, min(len(pts) - 2, next((k for k in range(len(pts) - 1) if s <= acc[k + 1]), len(pts) - 2)))
        L = acc[i + 1] - acc[i]
        k = 0.0 if L < 1e-9 else (s - acc[i]) / L
        return pts[i][0] + (pts[i + 1][0] - pts[i][0]) * k, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * k

    out = [at(s0)] + [p for p, s in zip(pts, acc) if s0 < s < s1] + [at(s1)]
    return [p for i, p in enumerate(out) if i == 0 or math.dist(p, out[i - 1]) > 1e-6]


def _roof_spans(pts, sec):
    """Интервалы пути [(s0, s1)] под кровлей, по порядку."""
    L, run = _length(pts), WallRun(WALL, "конец", "конец", tuple(pts), OPEN, YARD)
    spans = []
    for r in sec.roofs:
        if isinstance(r, int):
            ring = plan.osm_way(r)
            ds = [plan.station(run, p) for p in ring]
            near = [s for d, s in ds if d <= ROOF_OUTLINE_M]
            if len(near) < 2:
                raise ValueError(f"контур {r} не прилегает к линии {sec.way}")
            spans.append((max(0.0, min(s for _, s in ds)), min(L, max(s for _, s in ds))))
        else:
            spans.append((L - r, L))
    spans.sort()
    for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
        if b0 < a1 + 1.0:
            raise ValueError(f"куски под кровлей на {sec.way} перекрываются или ближе 1 м")
    return spans


def section_runs(sec, counters):
    """Участки одной линии: открытые и под кровлей по порядку. Концы — «конец» (там wall_mesh не продлевает трассу:
    соседние участки стыкуются торцами) или имя башни (продлевается в неё на 2 м, как у Крома). Имена стен —
    «Окольный город, открытая N» / «…, под кровлей N»: N — по порядку от моста, ассеты не совпадают."""
    pts = plan.densify(plan.osm_way(sec.way), plan.DENSIFY_M)
    end = "конец"
    if sec.tower is not None:
        hit = next((i for i, p in enumerate(pts) if plan.dist_to_poly(p, sec.tower.footprint) <= TOWER_HIT_M), None)
        if hit is None:
            raise ValueError(f"way {sec.way} не доходит до башни {sec.tower.name}")
        pts, end = pts[:hit + 1], sec.tower.name
    L = _length(pts)
    cuts, roofed = [0.0], []
    for s0, s1 in _roof_spans(pts, sec):
        cuts += [s0, s1]
        roofed.append((s0, s1))
    cuts.append(L)
    runs = []
    for s0, s1 in zip(cuts, cuts[1:]):
        if s1 - s0 < 0.5:
            continue
        kind = "под кровлей" if (s0, s1) in roofed else "открытая"
        counters[kind] = counters.get(kind, 0) + 1
        piece = plan.simplify(_piece(pts, s0, s1), 0.3)
        b = end if s1 >= L - 1e-6 else "конец"
        runs.append(WallRun(f"{WALL}, {ORDINAL[counters[kind] - 1]} {kind}", "конец", b, tuple(piece),
                            ROOFED if kind == "под кровлей" else OPEN, YARD))
    return runs


def wall_runs():
    """Участки стены Окольного города по Великой (WallRun, линия — внешняя грань, двор — город), с севера на юг."""
    counters = {}
    return [r for s in SECTIONS for r in section_runs(s, counters)]


def foot_z(run):
    """Отметка газона у подошвы с речной стороны для участка этого плана; для чужих участков — None."""
    return FOOT_Z if run.wall.startswith(WALL + ",") else None


def scene_runs():
    """Всё, что строит walls_krom.py: (участки, проёмы). Стены Крома и Довмонтова города — ровно krom_plan.wall_runs()
    и его wall_gates() (порядок и данные те же), за ними — участки этого плана (проёмов в них пока нет)."""
    runs = plan.wall_runs()
    gates = plan.wall_gates(runs)
    return runs + wall_runs(), gates


if __name__ == "__main__":
    import os
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import wall_mesh as wm

    runs = wall_runs()
    for r in runs:
        print(f"{r.name:52} {r.length:6.1f} м  t={r.profile.t} h={r.profile.h} ход {r.profile.z_walk:4.2f}  "
              f"({r.points[0][0]:.1f}, {r.points[0][1]:.1f}) → ({r.points[-1][0]:.1f}, {r.points[-1][1]:.1f})  "
              f"{plan.wall_asset(r)}")
    roofed_m = sum(r.length for r in runs if r.profile.roof)
    print(f"всего {sum(r.length for r in runs):.0f} м (под кровлей {roofed_m:.0f}), "
          "OSM: " + ", ".join(f"{s.way} {_length(plan.osm_way(s.way)):.0f} м" for s in SECTIONS))
    scene, gates = scene_runs()
    assets = [plan.wall_asset(r) for r in scene]
    assert len(set(assets)) == len(assets), "ассеты участков совпадают"
    assert len({r.name for r in scene}) == len(scene)
    assert all(r.length >= 3.0 for r in runs), [(r.name, r.length) for r in runs if r.length < 3.0]
    # соседние участки одной линии стыкуются точно: конец одного — начало следующего
    for s in SECTIONS:
        own = section_runs(s, {})
        for p, q in zip(own, own[1:]):
            assert math.dist(p.points[-1], q.points[0]) < 1e-6, (p.name, q.name)
    # куски под кровлей по контурам OSM — длиной с контур (13,2 м ± 0,5)
    for r in runs:
        if r.profile.roof and r.b == "конец":
            assert abs(r.length - 13.2) < 0.6, (r.name, r.length)
    # двор — город: по heightmap в 12 м от грани к двору земля выше, чем в 12 м к реке
    import roads_mesh
    hm = roads_mesh.Heights(os.path.join(plan.geo.REPO, "refs", "dem", "heightmap_L_Krom.json"))
    for r in runs:
        g = wm.WallGeom(r)
        higher = sum(y > o for y, o in (hm.at([g.path.at(s, 12.0), g.path.at(s, -12.0)]) for s in g.stations))
        assert higher / len(g.stations) > 0.9, (r.name, higher, len(g.stations))
        pr = g.probes()
        flat = g.build([0.0] * len(pr))
        assert len(g.zvena) == 1, r.name
        slope = g.build([0.05 * i / g.PROBES for i in range(len(pr))])
        print(f"{r.name:52} двор выше в {higher}/{len(g.stations)}, ровно {flat.triangles()} тр., "
              f"уклон 5 %: звеньев {len(g.zvena)}, {slope.triangles()} тр.")
    print("ok")
