"""blockout_krom.py — blockout Крома и Довмонтова города из примитивов, посаженный на рельеф (M2).

Запуск:  python scripts/ue_run.py scripts/blockout_krom.py
Нужно: L_Krom с Landscape (см. scripts/README.md). Что и где стоит — scripts/krom_plan.py.

Идемпотентен: удаляет свои акторы (тег generated:blockout_krom), обновляет материалы M_Blockout / MI_BO_*
и граненые примитивы SM_BO_*, заново ставит всё и сохраняет. Высоты земли — трассировкой по Landscape,
до того как появятся новые акторы.

Стены — коробки не длиннее SEG_MAX_M по участкам WallRun: верх — более высокая сторона + высота со двора,
низ — самая низкая земля под стеной минус EMBED_M. Здания — примитивы Part, база — земля в Building.ground_at (base или origin);
части «от земли» опускаются до самой низкой земли под контуром. Здания, у которых уже есть ассет героя
(Building.hero), пропускаются — их ставит heroes_krom.py; участки стен с готовым мешем (krom_plan.wall_asset) —
тоже, их ставит walls_krom.py.
"""
import importlib
import math
import os
import sys
from collections import Counter

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo  # noqa: E402
import krom_plan  # noqa: E402

# Python редактора живёт между запусками ue_run: без reload правки плана не подхватятся.
importlib.reload(krom_geo)
import yard_plan  # noqa: E402 — krom_plan.buildings() берёт из него постройки двора; без reload — старый план
importlib.reload(yard_plan)
import prikaz_plan  # noqa: E402 — Приказные палаты (герой), как yard_plan
importlib.reload(prikaz_plan)
import pskovgu_plan  # noqa: E402 — ПсковГУ (герои), как yard_plan
importlib.reload(pskovgu_plan)
import pozemskogo_plan  # noqa: E402 — Запсковье (герои), как yard_plan
importlib.reload(pozemskogo_plan)
import zapskovye_plan  # noqa: E402 — Запсковье, партия 1 (герои), как yard_plan
importlib.reload(zapskovye_plan)
import lenina_plan  # noqa: E402 — площадь Ленина (герои), как yard_plan
importlib.reload(lenina_plan)
plan = importlib.reload(krom_plan)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:blockout_krom")
FOLDER = "Generated/blockout_krom"
BO_DIR = "/Game/Krom/Blockout"
# свои примитивы (к /Engine/BasicShapes): ключ Part.shape → (ассет, граней, верх/низ радиуса)
FACETED = {
    "pyr": ("SM_BO_Pyramid4", 4, 0.0),
    "oct": ("SM_BO_Prism8", 8, 1.0),
    "pyr8": ("SM_BO_Pyramid8", 8, 0.0),
}

SEG_MAX_M = 6.0    # длина одной коробки стены: ступенька по высоте на склоне не больше пары метров
EMBED_M = 1.0      # насколько низ уходит под самую низкую землю
SIDE_M = 1.0       # на сколько за грань стены смотреть землю, чтобы найти «двор»
TRACE_Z_M = 300.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


# ---------- ассеты ----------

def faceted_mesh(name, sides, top):
    """Граненая призма или пирамида 100 uu по граням и по высоте, центр в середине — как /Engine/BasicShapes.
    Грани смотрят по осям X и Y."""
    path = f"{BO_DIR}/{name}"
    r = 50 / math.cos(math.pi / sides)
    mesh = unreal.DynamicMesh()
    unreal.GeometryScript_Primitives.append_cone(
        mesh, unreal.GeometryScriptPrimitiveOptions(),
        unreal.Transform(rotation=unreal.Rotator(roll=0, pitch=0, yaw=180 / sides)),
        base_radius=r, top_radius=r * top, height=100, radial_steps=sides, height_steps=1,
        capped=True, origin=unreal.GeometryScriptPrimitiveOriginMode.CENTER)
    unreal.GeometryScript_Normals.set_per_face_normals(mesh)
    if assets.does_asset_exist(path):
        sm = unreal.load_asset(path)
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(
            mesh, sm, unreal.GeometryScriptCopyMeshToAssetOptions(), unreal.GeometryScriptMeshWriteLOD())
    else:
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        sm, _ = unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(mesh, path, opts)
    assets.save_loaded_asset(sm)
    return sm


def blockout_materials():
    """M_Blockout (цвет — параметр) и по экземпляру на каждый ключ krom_plan.COLORS."""
    path = f"{BO_DIR}/M_Blockout"
    if assets.does_asset_exist(path):
        mat = unreal.load_asset(path)
        mel.delete_all_material_expressions(mat)
    else:
        mat = tools.create_asset("M_Blockout", BO_DIR, unreal.Material, unreal.MaterialFactoryNew())
    color = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -300, 0)
    color.set_editor_property("parameter_name", "Color")
    color.set_editor_property("default_value", unreal.LinearColor(0.5, 0.5, 0.5, 1))
    rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -300, 200)
    rough.set_editor_property("r", 0.85)
    mel.connect_material_property(color, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)

    out = {}
    for key, rgb in plan.COLORS.items():
        name = f"MI_BO_{key.capitalize()}"
        mi_path = f"{BO_DIR}/{name}"
        if assets.does_asset_exist(mi_path):
            mi = unreal.load_asset(mi_path)
        else:
            mi = tools.create_asset(name, BO_DIR, unreal.MaterialInstanceConstant,
                                    unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(mi, mat)
        mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(*rgb, 1))
        assets.save_loaded_asset(mi)
        out[key] = mi
    return out


# ---------- рельеф ----------

class Ground:
    """Высота Landscape в точке (м), трассировкой сверху вниз; с кешем по сетке 0,25 м.

    Если трасса упёрлась не в Landscape, точка считается промахом (None) и в расчёт не идёт.
    """

    def __init__(self, world):
        self.world = world
        self.cache = {}
        self.misses = 0

    def __call__(self, x, y):
        key = (round(x * 4), round(y * 4))
        if key not in self.cache:
            self.cache[key] = self._trace(x, y)
        return self.cache[key]

    def _trace(self, x, y):
        top = unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100)
        bottom = unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100)
        hit = unreal.SystemLibrary.line_trace_single(
            self.world, top, bottom, unreal.TraceTypeQuery.ECC_VISIBILITY, False, [],
            unreal.DrawDebugTrace.NONE, True)
        if hit is not None:
            t = hit.to_tuple()  # (blocking, initial_overlap, time, distance, location, impact_point, …, actor, …)
            if isinstance(t[9], unreal.LandscapeProxy):
                return t[5].z / 100.0
        self.misses += 1
        return None

    def many(self, points):
        """Высоты в точках без промахов; если промахнулись все — 0 (уровень собора)."""
        return [z for z in (self(*p) for p in points) if z is not None] or [0.0]


# ---------- раскладка в коробки ----------

def wall_boxes(run, ground):
    """Участок стены → список (центр xy, yaw, длина, z низа, z верха), всё в метрах."""
    t, pts = run.thickness, run.points
    boxes = []
    for i, (a, b) in enumerate(zip(pts, pts[1:])):
        seg = math.dist(a, b)
        if seg < 1e-3:
            continue
        dx, dy = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
        yaw = math.degrees(math.atan2(dy, dx))
        # удлинение на t/2 — только на изломах и концах участка, чтобы не было щелей и совпадающих граней
        ext_a = t / 2 if i == 0 or _turn(pts[i - 1], a, b) > 2 else 0.0
        ext_b = t / 2 if i == len(pts) - 2 or _turn(a, b, pts[i + 2]) > 2 else 0.0
        n = max(1, math.ceil(seg / SEG_MAX_M))
        for k in range(n):
            p = (a[0] + dx * seg * k / n, a[1] + dy * seg * k / n)
            q = (a[0] + dx * seg * (k + 1) / n, a[1] + dy * seg * (k + 1) / n)
            e0 = ext_a if k == 0 else 0.0
            e1 = ext_b if k == n - 1 else 0.0
            samples = ground.many([(c[0] + s * -dy, c[1] + s * dx)
                                   for c in (p, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), q)
                                   for s in (0.0, t / 2 + SIDE_M, -(t / 2 + SIDE_M))])
            length = seg / n + e0 + e1
            shift = (e1 - e0) / 2
            center = ((p[0] + q[0]) / 2 + dx * shift, (p[1] + q[1]) / 2 + dy * shift)
            boxes.append((center, yaw, length, min(samples) - EMBED_M, max(samples) + run.height))
    return boxes


def _turn(a, b, c):
    """Угол поворота ломаной в вершине b, градусы."""
    h1 = math.atan2(b[1] - a[1], b[0] - a[0])
    h2 = math.atan2(c[1] - b[1], c[0] - b[0])
    return abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))


# ---------- акторы ----------

class Spawner:
    def __init__(self, materials, faceted):
        self.mats = materials
        self.meshes = {
            "box": unreal.load_asset("/Engine/BasicShapes/Cube"),
            "cyl": unreal.load_asset("/Engine/BasicShapes/Cylinder"),
            "cone": unreal.load_asset("/Engine/BasicShapes/Cone"),
            "sphere": unreal.load_asset("/Engine/BasicShapes/Sphere"),
            **faceted,
        }
        self.count = Counter()

    def put(self, shape, center_xy, z0, z1, size_uv, yaw, mat, folder, label):
        """Примитив 100 uu с центром в середине → коробка size_uv × (z1 − z0), метры."""
        loc = unreal.Vector(center_xy[0] * 100, center_xy[1] * 100, (z0 + z1) / 2 * 100)
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, loc, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        a.set_actor_label(label)
        a.set_folder_path(f"{FOLDER}/{folder}")
        a.set_editor_property("tags", [TAG])
        a.set_editor_property("is_spatially_loaded", False)
        smc = a.static_mesh_component
        smc.set_static_mesh(self.meshes[shape])
        smc.set_material(0, self.mats[mat])
        a.set_actor_scale3d(unreal.Vector(size_uv[0], size_uv[1], z1 - z0))  # 100 uu = 1 м
        self.count[folder.split("/")[0]] += 1
        return a


def place_building(b, ground, spawner):
    base = ground.many([b.ground_at])[0]
    low = min([base] + ground.many(b.footprint))
    for i, p in enumerate(b.parts):
        xy = plan.to_world(b.origin, b.yaw, *p.uv)
        z0 = (low - EMBED_M) if p.z[0] <= 0 else base + p.z[0]
        spawner.put(p.shape, xy, z0, base + p.z[1], p.size, b.yaw, p.mat, f"{b.group}/{b.name}",
                    f"BO_{b.name}_{i:02d}")
    return base


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not any(isinstance(a, unreal.Landscape) for a in actors.get_all_level_actors()):
        raise RuntimeError(f"в {LEVEL} нет Landscape — blockout не на что сажать (scripts/README.md)")
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    # план и все высоты — до появления новых акторов, чтобы трассы били только в Landscape
    ground = Ground(world)
    towers, buildings = plan.towers(), plan.buildings()
    heroes = [b.name for b in towers + buildings if b.hero and assets.does_asset_exist(b.hero)]
    towers = [b for b in towers if b.name not in heroes]
    buildings = [b for b in buildings if b.name not in heroes]
    runs = [r for r in plan.wall_runs() if not assets.does_asset_exist(plan.wall_asset(r))]  # готовые — walls_krom.py
    walls = [(r, wall_boxes(r, ground)) for r in runs]
    for b in towers + buildings:
        ground(*b.ground_at)
        for p in b.footprint:
            ground(*p)

    spawner = Spawner(blockout_materials(), {k: faceted_mesh(*v) for k, v in FACETED.items()})
    for r, boxes in walls:
        for i, (c, yaw, length, z0, z1) in enumerate(boxes):
            spawner.put("box", c, z0, z1, (length, r.thickness), yaw, "wall", f"Walls/{r.name}",
                        f"BO_{r.name}_{i:03d}")
    report = []
    for b in towers + buildings:
        base = place_building(b, ground, spawner)
        top = max(p.z[1] for p in b.parts)
        report.append(f"{b.name}: земля {base:+.1f} м, верх {base + top:+.1f} м")

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[blockout_krom] {line}")
    total = sum(r.length for r in runs)
    if heroes:
        unreal.log(f"[blockout_krom] герои (ставит heroes_krom.py): {', '.join(heroes)}")
    unreal.log(f"[blockout_krom] done: {dict(spawner.count)} actors, стены {len(runs)} участков / {total:.0f} м, "
               f"трасс {len(ground.cache)}, мимо Landscape {ground.misses}")


main()
