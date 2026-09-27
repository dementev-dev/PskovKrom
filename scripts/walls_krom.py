"""walls_krom.py — стены Крома и Довмонтова города в L_Krom: StaticMesh на каждый участок krom_plan.WallRun (D-021).
Тем же прогоном — стена Окольного города по Великой к югу от Ольгинского моста (okolny_plan.py): участки
okolny_plan.scene_runs() идут после участков Крома, их тело с речной стороны уходит до okolny_plan.FOOT_Z.

Запуск:  python scripts/ue_run.py scripts/walls_krom.py
Нужно: L_Krom с Landscape; материалы M_KromStone и M_KromWood (materials_krom.py, D-027) или хотя бы MI_BO_Stone
и MI_BO_Wood (их создаёт blockout_krom.py от M_Blockout). Порядок — scripts/README.md «Первичная сборка».

Поперечник — krom_plan.WallProfile, геометрия — scripts/wall_mesh.py (звенья со ступенями, бруствер с бойницами,
ход, столбы, тёсовая кровля, проходы). Земля — трассой по Landscape; то, что стоит над ней (башни, герои), трасса
проходит насквозь. Меш — GeometryScript → /Game/Krom/Architecture/Walls/SM_Wall_<участок>: Nanite с полным
запасным мешем, коллизия «complex as simple», слоты по ключам COLORS — как у героев (D-019).

Идемпотентен: удаляет свои акторы (тег generated:walls_krom) и коробки стен blockout, пересобирает меши
в те же ассеты (ссылки не рвутся), ставит акторы и сохраняет. blockout_krom.py участки с готовым мешем пропускает.
"""
import importlib
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo  # noqa: E402
import krom_plan  # noqa: E402
import okolny_plan  # noqa: E402
import palette_krom  # noqa: E402
import wall_mesh  # noqa: E402

importlib.reload(krom_geo)
plan = importlib.reload(krom_plan)
okolny = importlib.reload(okolny_plan)
importlib.reload(palette_krom)
wm = importlib.reload(wall_mesh)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:walls_krom")
BLOCKOUT_TAG = unreal.Name("generated:blockout_krom")
FOLDER = "Generated/walls_krom"
BO_WALLS = "Generated/blockout_krom/Walls"
BO_DIR = "/Game/Krom/Blockout"
MATS = ("stone", "wood")
TRACE_Z_M = 300.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
GS = unreal.GeometryScript_MeshEdits


class Ground:
    """Высота Landscape (м) трассой сверху. Если трасса упёрлась в актор над землёй (башню, героя), он
    добавляется в исключения и трасса повторяется: земля нужна и под башнями, куда стена заходит концами."""

    def __init__(self, world):
        self.world, self.ignore, self.misses = world, [], 0

    def __call__(self, x, y):
        for _ in range(6):
            hit = unreal.SystemLibrary.line_trace_single(
                self.world, unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100),
                unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100),
                unreal.TraceTypeQuery.ECC_VISIBILITY, True, self.ignore, unreal.DrawDebugTrace.NONE, True)
            if hit is None:
                break
            t = hit.to_tuple()  # (blocking, initial_overlap, time, distance, location, impact_point, …, actor, …)
            if isinstance(t[9], unreal.LandscapeProxy):
                return t[5].z / 100.0
            self.ignore.append(t[9])
        self.misses += 1
        return None


def with_foot(z, foot):
    """Земля под внешней гранью (вторая точка на станцию в WallGeom.probes(), w = −0,5) — не выше foot: тело
    подпорной стены (okolny_plan.FOOT_Z) уходит до газона у подошвы, даже пока рельеф там — сглаженный откос."""
    k = wm.WallGeom.PROBES
    return [(foot if v is None else min(v, foot)) if i % k == 1 else v for i, v in enumerate(z)]


def dynamic_mesh(mesh, origin):
    """wall_mesh.Mesh (метры плана) → DynamicMesh в сантиметрах относительно origin; material ID — по MATS."""
    dm = unreal.DynamicMesh()
    ox, oy = origin
    for mid, key in enumerate(MATS):
        if key not in mesh.parts:
            continue
        verts, norms, uvs, tris = mesh.parts[key]
        buf = unreal.GeometryScriptSimpleMeshBuffers()
        buf.set_editor_property("vertices", [unreal.Vector((x - ox) * 100, (y - oy) * 100, z * 100) for x, y, z in verts])
        buf.set_editor_property("normals", [unreal.Vector(*n) for n in norms])
        buf.set_editor_property("uv0", [unreal.Vector2D(u, v) for u, v in uvs])
        buf.set_editor_property("triangles", [unreal.IntVector(*t) for t in tris])
        GS.append_buffers_to_mesh(dm, buf, material_id=mid)
    return dm


def write_asset(dm, path, mis):
    """DynamicMesh → StaticMesh по пути path (создать или переписать), Nanite с полным запасным мешем,
    коллизия по самому мешу."""
    if not assets.does_asset_exist(path):
        opts = unreal.GeometryScriptCreateNewStaticMeshAssetOptions()
        opts.set_editor_property("enable_recompute_normals", False)
        unreal.GeometryScript_NewAssetUtils.create_new_static_mesh_asset_from_mesh(dm, path, opts)
    sm = unreal.load_asset(path)
    opts = unreal.GeometryScriptCopyMeshToAssetOptions()
    for k, v in (("enable_recompute_normals", False), ("replace_materials", True), ("new_materials", mis),
                 ("new_material_slot_names", [unreal.Name(k) for k in MATS])):
        opts.set_editor_property(k, v)
    unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    meshes.remove_collisions(sm)
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    ns.set_editor_property("fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
    ns.set_editor_property("fallback_percent_triangles", 1.0)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    mis = []
    for key in MATS:
        path = f"{BO_DIR}/MI_BO_{key.capitalize()}"
        mat = palette_krom.building_material(key)
        if mat is None and not assets.does_asset_exist(path):
            raise RuntimeError(f"нет {path} — сначала materials_krom.py, blockout_krom.py или heroes_krom.py")
        mis.append(mat or unreal.load_asset(path))
    for a in actors.get_all_level_actors():
        if TAG in a.tags or (BLOCKOUT_TAG in a.tags and str(a.get_folder_path()).startswith(BO_WALLS)):
            actors.destroy_actor(a)

    runs, gates = okolny.scene_runs()   # krom_plan.wall_runs() как есть + стена Окольного города по Великой
    ground = Ground(world)
    report = []
    for r in runs:
        geom = wm.WallGeom(r, gates.get(r.name, ()))
        level = ground(*r.level_at) if r.level_at else None  # уровень двора участка (D-026)
        z = [ground(*p) for p in geom.probes()]
        foot = okolny.foot_z(r)
        mesh = geom.build(z if foot is None else with_foot(z, foot), level)
        origin = tuple(round(c, 1) for c in r.points[0])
        sm = write_asset(dynamic_mesh(mesh, origin), plan.wall_asset(r), mis)
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(origin[0] * 100, origin[1] * 100, 0),
                                          unreal.Rotator(roll=0, pitch=0, yaw=0))
        a.set_actor_label(f"Стена {r.name}")
        a.set_folder_path(f"{FOLDER}/{r.wall}")
        a.set_editor_property("tags", [TAG])
        a.set_editor_property("is_spatially_loaded", False)
        a.static_mesh_component.set_static_mesh(sm)
        levels_z = [z[2] for z in geom.zvena]
        warn = "" if geom.yard_higher >= 0.5 else f"  ВНИМАНИЕ: двор выше снаружи лишь в {geom.yard_higher:.0%} точек"
        report.append(f"{r.name}: {r.length:.0f} м, звеньев {len(geom.zvena)}, земля двора {min(levels_z):+.1f}…"
                      f"{max(levels_z):+.1f} м, треугольников {mesh.triangles()}{warn}")

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[walls_krom] {line}")
    unreal.log(f"[walls_krom] done: {len(runs)} участков, {sum(r.length for r in runs):.0f} м, мимо Landscape "
               f"{ground.misses}, насквозь {len(ground.ignore)} акторов, {time.time() - t0:.0f} с")


main()
