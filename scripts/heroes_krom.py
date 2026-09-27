"""heroes_krom.py — герои M3 из Blender в L_Krom: импорт .glb, материалы, установка по krom_plan (D-018).

Запуск (сначала выгрузка героя из Blender):
    python scripts/bl_run.py scripts/blender/cathedral.py
    python scripts/ue_run.py scripts/heroes_krom.py

Здания krom_plan с полем hero: build/blender/<имя ассета>.glb → StaticMesh по пути hero (Nanite, коллизия «complex as
simple»). Материалы — по имени слота = ключ krom_plan.COLORS → M_Krom<Ключ> (materials_krom.py, D-027), пока его
нет — MI_BO_<Ключ>. Актор ставится
в origin с азимутом yaw, высота — земля в Building.ground_at (base или origin), как у blockout.

Идемпотентен: удаляет свои акторы (тег generated:heroes_krom) и примитивы blockout этих зданий, импортирует меш
заново во временную папку, заменяет им прежний ассет, ставит акторы и сохраняет. blockout_krom.py здания
с готовым героем не ставит.
"""
import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo  # noqa: E402
import krom_plan  # noqa: E402
import palette_krom  # noqa: E402

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
importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:heroes_krom")
BLOCKOUT_TAG = unreal.Name("generated:blockout_krom")
FOLDER = "Generated/heroes_krom"
BO_DIR = "/Game/Krom/Blockout"
STAGING = "/Game/Krom/Architecture/_import"   # Interchange кладёт сюда меш и свои MI по подпапкам; после — удаляется
GLB_DIR = os.path.join(krom_geo.REPO, "build", "blender")

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def blockout_mi(key):
    """MI_BO_<Ключ> из blockout с цветом krom_plan.COLORS; нет — создать от M_Blockout."""
    name = f"MI_BO_{key.capitalize()}"
    path = f"{BO_DIR}/{name}"
    color = unreal.LinearColor(*plan.COLORS[key], 1)
    if assets.does_asset_exist(path):
        mi = unreal.load_asset(path)
        if mel.get_material_instance_vector_parameter_value(mi, "Color") != color:   # цвет в плане поменялся
            mel.set_material_instance_vector_parameter_value(mi, "Color", color)
            assets.save_loaded_asset(mi)
        return mi
    mi = tools.create_asset(name, BO_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, unreal.load_asset(f"{BO_DIR}/M_Blockout"))
    mel.set_material_instance_vector_parameter_value(mi, "Color", color)
    assets.save_loaded_asset(mi)
    return mi


def import_hero(path):
    """build/blender/<имя>.glb → StaticMesh по пути path; прежний ассет заменяется. Возвращает меш."""
    name = path.rsplit("/", 1)[1]
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    if not os.path.exists(glb):
        raise RuntimeError(f"нет {glb} — сначала python scripts/bl_run.py scripts/blender/<герой>.py")
    if assets.does_directory_exist(STAGING):
        assets.delete_directory(STAGING)
    task = unreal.AssetImportTask()
    for k, v in (("filename", glb), ("destination_path", STAGING), ("replace_existing", True),
                 ("automated", True), ("save", False)):
        task.set_editor_property(k, v)
    tools.import_asset_tasks([task])
    staged = [p for p in task.get_editor_property("imported_object_paths")
              if isinstance(unreal.load_asset(p), unreal.StaticMesh)]
    if len(staged) != 1:
        raise RuntimeError(f"импорт {glb}: ждали один StaticMesh, получили {staged}")
    src = unreal.load_asset(staged[0])
    names = [str(s.get_editor_property("material_slot_name")) for s in src.get_editor_property("static_materials")]
    mis = [palette_krom.building_material(n) or blockout_mi(n) for n in names]
    if not assets.does_asset_exist(path):
        if not assets.rename_asset(staged[0].split(".")[0], path):
            raise RuntimeError(f"не удалось переместить {staged[0]} → {path}")
        sm = unreal.load_asset(path)
        for i, mi in enumerate(mis):
            sm.set_material(i, mi)
    else:  # ассет уже есть: геометрия копируется в него, ссылки на него (акторы, отмена) остаются целы
        sm = unreal.load_asset(path)
        dm, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            src, unreal.DynamicMesh(), unreal.GeometryScriptCopyMeshFromAssetOptions(),
            unreal.GeometryScriptMeshReadLOD())
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("replace_materials", True), ("new_materials", mis),
                     ("new_material_slot_names", [unreal.Name(n) for n in names])):
            opts.set_editor_property(k, v)
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    assets.delete_directory(STAGING)
    meshes.remove_collisions(sm)  # Interchange строит один выпуклый корпус — он закрыл бы весь собор
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    # запасной меш Nanite — без упрощения: по нему считаются коллизия и снимки SceneCapture (r.SceneCapture.Nanite 0),
    # а Interchange по умолчанию оставляет ≈6 % треугольников и теряет окна
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
    ns.set_editor_property("fallback_percent_triangles", 1.0)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


def ground_z(world, x, y):
    """Высота Landscape в точке (м) трассировкой сверху; мимо Landscape — None. Актор над землёй (стена, другой
    герой) трасса проходит насквозь: башни стоят в линии стен, и точка отсчёта может оказаться под стеной."""
    ignore = []
    for _ in range(6):
        hit = unreal.SystemLibrary.line_trace_single(
            world, unreal.Vector(x * 100, y * 100, 30000), unreal.Vector(x * 100, y * 100, -30000),
            unreal.TraceTypeQuery.ECC_VISIBILITY, False, ignore, unreal.DrawDebugTrace.NONE, True)
        if hit is None:
            return None
        t = hit.to_tuple()
        if isinstance(t[9], unreal.LandscapeProxy):
            return t[5].z / 100.0
        ignore.append(t[9])
    return None


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    heroes = [b for b in plan.towers() + plan.buildings() if b.hero]
    bo_folders = {f"Generated/blockout_krom/{b.group}/{b.name}" for b in heroes}
    for a in actors.get_all_level_actors():
        if TAG in a.tags or (BLOCKOUT_TAG in a.tags and str(a.get_folder_path()) in bo_folders):
            actors.destroy_actor(a)

    report = []
    for b in heroes:
        base = ground_z(world, *b.ground_at)
        if base is None:
            raise RuntimeError(f"{b.name}: под {b.ground_at} нет Landscape")
        under = [z for z in (ground_z(world, *p) for p in b.footprint) if z is not None]
        sm = import_hero(b.hero)
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor,
                                          unreal.Vector(b.origin[0] * 100, b.origin[1] * 100, base * 100),
                                          unreal.Rotator(roll=0, pitch=0, yaw=b.yaw))
        a.set_actor_label(b.name)
        a.set_folder_path(f"{FOLDER}/{b.group}")
        a.set_editor_property("tags", [TAG])
        a.set_editor_property("is_spatially_loaded", False)
        a.static_mesh_component.set_static_mesh(sm)
        report.append(f"{b.name}: {b.hero}, земля {base:+.2f} м, под контуром {min(under) - base:+.2f}…"
                      f"{max(under) - base:+.2f} м от неё")

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[heroes_krom] {line}")
    unreal.log(f"[heroes_krom] done: {len(heroes)} героев")


main()
