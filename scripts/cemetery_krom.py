"""cemetery_krom.py — Мироносицкое кладбище в L_Krom: надгробия и звенья ограды — HISM по точкам (M5+).

Запуск (сначала точки и модели):
    PYTHONIOENCODING=utf-8 .venv/Scripts/python scripts/cemetery_points.py    # build/cemetery/points.json
    python scripts/bl_run.py scripts/blender/cemetery.py                      # build/blender/SM_Cem_*.glb
    python scripts/ue_run.py scripts/cemetery_krom.py

Меши — build/blender/SM_Cem_<Имя>.glb → /Game/Krom/Environment/Cemetery (Nanite, без коллизии; своя папка и своя
папка импорта — ассеты малых форм furniture_krom не задеваются). Материалы по имени слота, как у героев: ключ
krom_plan.COLORS → M_Krom<Ключ> (materials_krom.py), пока его нет — MI_BO_<Ключ>; им ставится флаг
used_with_instanced_static_meshes. Текстур нет.

Расстановка: вид точки (kind) → модель по заголовку points.json (kinds), поворот — yaw_deg, растяжение по X —
scale_x (звенья ограды: кусок стены OSM делится на звенья ≤ 3 м), высота — трассой по Landscape при каждом запуске
(рельеф меняют terrain_krom и дороги D-038; z в точках нет). Точка, где трасса не нашла Landscape (за его краем),
пропускается. Один актор с HierarchicalInstancedStaticMesh на модель: тысячи отдельных акторов — тысячи файлов
World Partition.

Храм Жён-Мироносиц и надвратная колокольня — герои генератора pskov_church.py (krom_plan.MIRONOSITSY,
MIRONOSITSY_GATE; ставит heroes_krom.py), не этот скрипт.

Идемпотентен: удаляет свои акторы (тег generated:cemetery_krom), переимпортирует меши в те же ассеты и сохраняет.
"""
import json
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:cemetery_krom")
FOLDER = "Generated/cemetery_krom"
CEM_DIR = "/Game/Krom/Environment/Cemetery"
BO_DIR = "/Game/Krom/Blockout"
STAGING = f"{CEM_DIR}/_import"
GLB_DIR = os.path.join(geo.REPO, "build", "blender")
POINTS = os.path.join(geo.REPO, "build", "cemetery", "points.json")
TRACE_Z_M = 300.0

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def slot_material(key):
    """Материал слота key: M_Krom<Ключ>, иначе MI_BO_<Ключ>; с флагом для HISM."""
    mat = palette_krom.building_material(key)
    if mat is None:
        bo = f"{BO_DIR}/MI_BO_{key.capitalize()}"
        if not assets.does_asset_exist(bo):
            raise RuntimeError(f"нет материала для слота {key}: сначала materials_krom.py (или blockout_krom.py)")
        mat = unreal.load_asset(bo)
    base = mat if isinstance(mat, unreal.Material) else mat.get_base_material()
    if not base.get_editor_property("used_with_instanced_static_meshes"):
        base.set_editor_property("used_with_instanced_static_meshes", True)
        mel.recompile_material(base)
        assets.save_loaded_asset(base)
    return mat


def import_mesh(name, mats):
    """build/blender/<name>.glb → StaticMesh CEM_DIR/<name> (Nanite, без коллизии); слоты по mats."""
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    if not os.path.exists(glb):
        raise RuntimeError(f"нет {glb} — сначала python scripts/bl_run.py scripts/blender/cemetery.py")
    path = f"{CEM_DIR}/{name}"
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
    for n in names:
        if n not in mats:
            mats[n] = slot_material(n)
    if not assets.does_asset_exist(path):
        if not assets.rename_asset(staged[0].split(".")[0], path):
            raise RuntimeError(f"не удалось переместить {staged[0]} → {path}")
        sm = unreal.load_asset(path)
        for i, n in enumerate(names):
            sm.set_material(i, mats[n])
    else:  # геометрия копируется в прежний ассет — ссылки HISM на него остаются
        sm = unreal.load_asset(path)
        dm, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(
            src, unreal.DynamicMesh(), unreal.GeometryScriptCopyMeshFromAssetOptions(),
            unreal.GeometryScriptMeshReadLOD())
        opts = unreal.GeometryScriptCopyMeshToAssetOptions()
        for k, v in (("enable_recompute_normals", False), ("enable_recompute_tangents", False),
                     ("replace_materials", True), ("new_materials", [mats[n] for n in names]),
                     ("new_material_slot_names", [unreal.Name(n) for n in names])):
            opts.set_editor_property(k, v)
        unreal.GeometryScript_AssetUtils.copy_mesh_to_static_mesh(dm, sm, opts, unreal.GeometryScriptMeshWriteLOD())
    assets.delete_directory(STAGING)
    meshes.remove_collisions(sm)
    ns = sm.get_editor_property("nanite_settings")
    ns.set_editor_property("enabled", True)
    sm.set_editor_property("nanite_settings", ns)
    assets.save_loaded_asset(sm)
    return sm


class Ground:
    """Высота Landscape (м) трассой сверху; актор над землёй трасса проходит насквозь (как в furniture_krom)."""

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
            t = hit.to_tuple()
            if isinstance(t[9], unreal.LandscapeProxy):
                return t[5].z / 100.0
            self.ignore.append(t[9])
        self.misses += 1
        return None


def new_actor(label, tags):
    a = actors.spawn_actor_from_class(unreal.Actor, unreal.Vector(0, 0, 0))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", tags)
    a.set_editor_property("is_spatially_loaded", False)
    return a


def add_component(parent, cls, label):
    """Компонент класса cls под parent (дескриптор подобъекта) → (дескриптор, компонент)."""
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    h, fail = sub.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=parent, new_class=cls,
                                                                 blueprint_context=None))
    if str(fail):
        raise RuntimeError(f"{label}: компонент {cls} не добавлен — {fail}")
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    return h, lib.get_associated_object(lib.get_data(h))


def actor_handle(a):
    return unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem).k2_gather_subobject_data_for_instance(a)[0]


def hism_actor(sm, label):
    """Актор с одним HierarchicalInstancedStaticMeshComponent для меша sm."""
    a = new_actor(label, [TAG])
    _, comp = add_component(actor_handle(a), unreal.HierarchicalInstancedStaticMeshComponent, label)
    comp.set_static_mesh(sm)
    comp.set_collision_profile_name("NoCollision")
    return comp


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    with open(POINTS, encoding="utf-8") as f:
        data = json.load(f)
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    mats = {}
    kinds = {k: v["asset"] for k, v in data["kinds"].items()}
    used = sorted({kinds[p["kind"]] for p in data["points"]})
    sms = {name: import_mesh(name, mats) for name in used}

    ground = Ground(world)
    transforms, count = {}, {}
    for p in data["points"]:
        name = kinds[p["kind"]]
        z = ground(p["x"], p["y"])
        if z is None:
            continue
        transforms.setdefault(name, []).append(unreal.Transform(
            unreal.Vector(p["x"] * 100, p["y"] * 100, z * 100), unreal.Rotator(roll=0, pitch=0, yaw=p["yaw_deg"]),
            unreal.Vector(p.get("scale_x", 1.0), 1, 1)))
        count[p["kind"]] = count.get(p["kind"], 0) + 1
    for name, ts in sorted(transforms.items()):
        hism_actor(sms[name], f"Cemetery {name}").add_instances(ts, False, True)

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[cemetery_krom] done: {sum(len(ts) for ts in transforms.values())} экземпляров в "
               f"{len(transforms)} HISM, мимо Landscape {ground.misses}, по видам {dict(sorted(count.items()))}, "
               f"{time.time() - t0:.0f} с")


if __name__ == "__main__":   # ue_run.py выполняет файл в словаре __main__
    main()
