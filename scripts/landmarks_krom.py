"""landmarks_krom.py — памятные знаки в L_Krom: два креста, «Меч Довмонта», «Россия начинается здесь», памятник
Ленину, памятник Ольге и амфитеатр Детского парка — всё по landmarks_plan.py (M5+).

Запуск (сначала модели):
    python scripts/bl_run.py scripts/blender/landmarks.py     # build/blender/SM_Mark_*.glb
    python scripts/ue_run.py scripts/landmarks_krom.py

Где стоят, куда смотрят и от чего мерить высоту — scripts/landmarks_plan.py (источники и гипотезы — там же).
Меши — build/blender/<asset>.glb → /Game/Krom/Environment/Landmarks/<asset> (Nanite, коллизия «complex as simple»,
как у героев). Материалы — по имени слота, как у героев и малых форм: ключ krom_plan.COLORS → M_Krom<Ключ>
(materials_krom.py), пока его нет — MI_BO_<Ключ> (создаётся от M_Blockout). Текстур нет.

Расстановка: по StaticMeshActor на знак в Landmark.xy с поворотом yaw; высота — трассой по Landscape в
Landmark.height_at при каждом запуске (рельеф меняют terrain_krom и дороги) плюс dz. Трасса проходит насквозь акторы
над землёй (стены, герои). У «Меча Довмонта» отсчёт — уровень двора Крома у Персей (krom_plan.LEVEL_AT) плюс низ
кровли над внешней гранью: композиция висит на стене, её ноль — верх лица стены.

Идемпотентен: удаляет свои акторы (тег generated:landmarks_krom), переимпортирует меши в те же ассеты и сохраняет.
"""
import importlib
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import krom_plan  # noqa: E402
import landmarks_plan  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(geo)
importlib.reload(krom_plan)
importlib.reload(palette_krom)
lp = importlib.reload(landmarks_plan)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:landmarks_krom")
FOLDER = "Generated/landmarks_krom"
MARK_DIR = "/Game/Krom/Environment/Landmarks"
BO_DIR = "/Game/Krom/Blockout"
STAGING = f"{MARK_DIR}/_import"
GLB_DIR = os.path.join(geo.REPO, "build", "blender")
TRACE_Z_M = 300.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def slot_material(key):
    """Материал слота key: M_Krom<Ключ>; нет — MI_BO_<Ключ> с цветом krom_plan.COLORS (создать от M_Blockout)."""
    mat = palette_krom.building_material(key)
    if mat is not None:
        return mat
    name = f"MI_BO_{key.capitalize()}"
    path = f"{BO_DIR}/{name}"
    if assets.does_asset_exist(path):
        return unreal.load_asset(path)
    mi = tools.create_asset(name, BO_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, unreal.load_asset(f"{BO_DIR}/M_Blockout"))
    mel.set_material_instance_vector_parameter_value(mi, "Color", unreal.LinearColor(*krom_plan.COLORS[key], 1))
    assets.save_loaded_asset(mi)
    return mi


def import_mesh(name):
    """build/blender/<name>.glb → StaticMesh MARK_DIR/<name>; прежний ассет заменяется (ссылки акторов целы)."""
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    if not os.path.exists(glb):
        raise RuntimeError(f"нет {glb} — сначала python scripts/bl_run.py scripts/blender/landmarks.py")
    path = f"{MARK_DIR}/{name}"
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
    mats = [slot_material(n) for n in names]
    if not assets.does_asset_exist(path):
        if not assets.rename_asset(staged[0].split(".")[0], path):
            raise RuntimeError(f"не удалось переместить {staged[0]} → {path}")
        sm = unreal.load_asset(path)
        for i, m in enumerate(mats):
            sm.set_material(i, m)
    else:
        sm = unreal.load_asset(path)
        dm, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            src, unreal.DynamicMesh(), unreal.GeometryScriptCopyMeshFromAssetOptions(),
            unreal.GeometryScriptMeshReadLOD())
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("replace_materials", True), ("new_materials", mats),
                     ("new_material_slot_names", [unreal.Name(n) for n in names])):
            opts.set_editor_property(k, v)
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    assets.delete_directory(STAGING)
    meshes.remove_collisions(sm)   # Interchange строит один выпуклый корпус — он закрыл бы крест вместе с валуном
    sm.get_editor_property("body_setup").set_editor_property(
        "collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    ns.set_editor_property("fallback_target", unreal.NaniteFallbackTarget.PERCENT_TRIANGLES)
    ns.set_editor_property("fallback_percent_triangles", 1.0)   # меши малые: запасной — без упрощения
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


class Ground:
    """Высота Landscape (м) трассой сверху; актор над землёй трасса проходит насквозь (как в furniture_krom)."""

    def __init__(self, world):
        self.world, self.ignore = world, []

    def __call__(self, x, y):
        for _ in range(8):
            hit = unreal.SystemLibrary.line_trace_single(
                self.world, unreal.Vector(x * 100, y * 100, TRACE_Z_M * 100),
                unreal.Vector(x * 100, y * 100, -TRACE_Z_M * 100),
                unreal.TraceTypeQuery.ECC_VISIBILITY, True, self.ignore, unreal.DrawDebugTrace.NONE, True)
            if hit is None:
                return None
            t = hit.to_tuple()
            if isinstance(t[9], unreal.LandscapeProxy):
                return t[5].z / 100.0
            self.ignore.append(t[9])
        return None


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    marks = lp.landmarks()
    ground = Ground(world)
    heights = {m.name: ground(*m.height_at) for m in marks}     # все трассы — до новых акторов
    report = []
    for m in marks:
        z0 = heights[m.name]
        if z0 is None:
            raise RuntimeError(f"{m.name}: под {m.height_at} нет Landscape")
        sm = import_mesh(m.asset)
        z = z0 + m.dz
        a = actors.spawn_actor_from_class(unreal.StaticMeshActor,
                                          unreal.Vector(m.xy[0] * 100, m.xy[1] * 100, z * 100),
                                          unreal.Rotator(roll=0, pitch=0, yaw=m.yaw))
        a.set_actor_label(m.name)
        a.set_folder_path(FOLDER)
        a.set_editor_property("tags", [TAG])
        a.set_editor_property("is_spatially_loaded", False)
        a.static_mesh_component.set_static_mesh(sm)
        report.append(f"{m.name}: {m.asset} в ({m.xy[0]:.1f}, {m.xy[1]:.1f}), yaw {m.yaw:.1f}, "
                      f"земля {z0:+.2f} + {m.dz:.2f} = {z:+.2f} м")

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for line in report:
        unreal.log(f"[landmarks_krom] {line}")
    unreal.log(f"[landmarks_krom] done: {len(report)} знаков, {time.time() - t0:.0f} с")


if __name__ == "__main__":   # ue_run.py выполняет файл в словаре __main__
    main()
