"""finpark_krom.py — Финский парк (парк Куопио) и плотина на Пскове у пешеходного моста в L_Krom (M5+).

Запуск (сначала модели; план — чистый Python, отдельно запускать не нужно):
    python scripts/bl_run.py scripts/blender/finpark.py       # build/finpark/SM_FinPark_*.glb
    python scripts/ue_run.py scripts/finpark_krom.py

Что и где — scripts/finpark_plan.py (placements(): модель, точка, поворот, способ высоты; источники — там же).
Ставится только то, что на Landscape (Y ≤ 1007 м): восточная половина парка — за краем, на кольце горизонта.

Меши — build/finpark/SM_FinPark_<Имя>.glb → /Game/Krom/Environment/FinPark (Nanite, без коллизии; геометрия
при повторном запуске копируется в прежний ассет, как в furniture_krom). Материалы — по имени слота:
  ключ krom_plan.COLORS → M_Krom<Ключ> (materials_krom.py), пока его нет — MI_BO_<Ключ> (blockout_krom.py);
  concrete, metal → M_KromConcrete, M_KromRailing (bridge_krom.py; нет — wall, dark);
  glow → MI_KromLampGlow (furniture_krom.py: вечером свечение включает furniture_krom.lights(True); нет — glass).
Новых материалов и текстур нет. Скамейки — готовый SM_Furn_Bench из furniture_krom.py (не переимпортируется).

Высота (finpark_plan, z_mode): плотина — от уреза Landscape (refs/dem/heightmap_L_Krom.json: water_level_z_m);
остальное — трассой по Landscape при каждом запуске; лестница садится на землю в первом узле и растягивается по Z
под подъём трассы до последнего узла; мостик — настил над выше лежащим концом. Нет Landscape под точкой — модель
пропускается (счётчик «мимо Landscape»).

Акторы: плотина, лестницы, мостики, корабль — по StaticMeshActor; фонари и скамейки — по одному актору
с HierarchicalInstancedStaticMesh на модель. Все — с тегом generated:finpark_krom, в папке Generated/finpark_krom.
Идемпотентен: удаляет свои акторы, переимпортирует меши в те же ассеты и сохраняет.
"""
import importlib
import json
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finpark_plan  # noqa: E402
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)
fp = importlib.reload(finpark_plan)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:finpark_krom")
FOLDER = "Generated/finpark_krom"
MESH_DIR = "/Game/Krom/Environment/FinPark"
STAGING = f"{MESH_DIR}/_import"
BO_DIR = "/Game/Krom/Blockout"
GLB_DIR = os.path.join(geo.REPO, "build", "finpark")
META = os.path.join(geo.REPO, "refs", "dem", "heightmap_L_Krom.json")
BENCH = "/Game/Krom/Environment/Furniture/SM_Furn_Bench"
SPECIAL = {   # слот → (готовый материал другого скрипта, запасной ключ COLORS)
    "concrete": ("/Game/Krom/Materials/Bridges/M_KromConcrete", "wall"),
    "metal": ("/Game/Krom/Materials/Bridges/M_KromRailing", "dark"),
    "glow": ("/Game/Krom/Materials/Furniture/MI_KromLampGlow", "glass"),
}
HISM_ASSETS = ("SM_FinPark_Lamp", "SM_Furn_Bench")   # много одинаковых — экземплярами
TRACE_Z_M = 300.0
STAIR_SCALE = (0.4, 2.5)   # растяжение лестницы по Z под трассу — не дальше этих пределов

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary


def flag_hism(mat):
    """Флаг used_with_instanced_static_meshes у базового материала (как в furniture_krom)."""
    base = mat if isinstance(mat, unreal.Material) else mat.get_base_material()
    if not base.get_editor_property("used_with_instanced_static_meshes"):
        base.set_editor_property("used_with_instanced_static_meshes", True)
        mel.recompile_material(base)
        assets.save_loaded_asset(base)


def color_material(key):
    """M_Krom<Ключ>, иначе MI_BO_<Ключ>; None — нет ни того, ни другого."""
    mat = palette_krom.building_material(key)
    if mat is None:
        bo = f"{BO_DIR}/MI_BO_{key.capitalize()}"
        mat = unreal.load_asset(bo) if assets.does_asset_exist(bo) else None
    return mat


def slot_material(key, hism):
    """Материал слота key (см. шапку); hism — поставить флаг для экземпляров."""
    path, fallback = SPECIAL.get(key, (None, key))
    mat = unreal.load_asset(path) if path and assets.does_asset_exist(path) else color_material(fallback)
    if mat is None:
        mat = color_material("wall")
        unreal.log_warning(f"[finpark_krom] нет материала для слота {key} — взят wall")
    if mat is None:
        raise RuntimeError(f"нет материала для слота {key}: сначала materials_krom.py (или blockout_krom.py)")
    if hism:
        flag_hism(mat)
    return mat


def import_mesh(name, hism):
    """build/finpark/<name>.glb → StaticMesh MESH_DIR/<name> (Nanite, без коллизии); слоты по именам, как в
    furniture_krom."""
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    if not os.path.exists(glb):
        raise RuntimeError(f"нет {glb} — сначала python scripts/bl_run.py scripts/blender/finpark.py")
    path = f"{MESH_DIR}/{name}"
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
    mats = {n: slot_material(n, hism) for n in names}
    if not assets.does_asset_exist(path):
        if not assets.rename_asset(staged[0].split(".")[0], path):
            raise RuntimeError(f"не удалось переместить {staged[0]} → {path}")
        sm = unreal.load_asset(path)
        for i, n in enumerate(names):
            sm.set_material(i, mats[n])
    else:  # геометрия копируется в прежний ассет — ссылки акторов на него остаются
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


def hism_actor(sm, label):
    """Актор с одним HierarchicalInstancedStaticMeshComponent для меша sm (как в furniture_krom)."""
    a = new_actor(label, [TAG])
    sub = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    root = sub.k2_gather_subobject_data_for_instance(a)[0]
    h, fail = sub.add_new_subobject(unreal.AddNewSubobjectParams(
        parent_handle=root, new_class=unreal.HierarchicalInstancedStaticMeshComponent, blueprint_context=None))
    if str(fail):
        raise RuntimeError(f"{label}: компонент HISM не добавлен — {fail}")
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    comp = lib.get_associated_object(lib.get_data(h))
    comp.set_static_mesh(sm)
    comp.set_collision_profile_name("NoCollision")
    return comp


def mesh_actor(sm, label, x, y, z, yaw, scale_z=1.0):
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(x * 100, y * 100, z * 100),
                                      unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)
    a.static_mesh_component.set_static_mesh(sm)
    a.static_mesh_component.set_collision_profile_name("NoCollision")
    if scale_z != 1.0:
        a.set_actor_scale3d(unreal.Vector(1, 1, scale_z))
    return a


def height(p, ground, water_z, report):
    """(z, масштаб по Z) для точки плана или None — нет Landscape; report[asset] — что вышло."""
    mode = p["z_mode"]
    if mode == "water":
        return water_z, 1.0
    if mode == "ground":
        z = ground(p["x"], p["y"])
        return None if z is None else (z, 1.0)
    if mode == "stairs":
        z0, z1 = ground(p["x"], p["y"]), ground(*p["end"])
        if z0 is None or z1 is None:
            return None
        baked, traced = p["rise"], z1 - z0
        s = traced / baked if abs(baked) > 0.2 and traced * baked > 0 else 1.0
        s = min(max(s, STAIR_SCALE[0]), STAIR_SCALE[1])
        report[p["asset"]] = f"подъём по трассе {traced:+.2f} м, в модели {baked:+.2f} — масштаб Z {s:.2f}"
        return z0, s
    if mode == "deck":
        zs = [z for z in (ground(*e) for e in p["ends"]) if z is not None] or \
             [z for z in (ground(p["x"], p["y"]),) if z is not None]
        if not zs:
            return None
        above = fp.DECK_ABOVE_M if p["asset"] == "SM_FinPark_FlatBridge" else fp.HUMP_DECK_ABOVE_M
        return max(zs) + above, 1.0
    raise ValueError(f"z_mode {mode}")


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    with open(META, encoding="utf-8") as f:
        water_z = json.load(f)["water_level_z_m"]
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    plan = [p for p in fp.placements() if p["inside"]]
    sms, skipped = {}, {}
    for name in sorted({p["asset"] for p in plan}):
        try:
            if name == "SM_Furn_Bench":
                if not assets.does_asset_exist(BENCH):
                    raise RuntimeError(f"нет {BENCH} — сначала furniture_krom.py")
                sms[name] = unreal.load_asset(BENCH)
            else:
                sms[name] = import_mesh(name, name in HISM_ASSETS)
        except Exception as e:  # noqa: BLE001 — одна модель не должна останавливать остальные
            unreal.log_warning(f"[finpark_krom] {name}: {e}")
            skipped[name] = str(e)

    ground = Ground(world)
    report, instances, placed = {}, {}, {}
    for p in plan:
        name = p["asset"]
        if name not in sms:
            continue
        hz = height(p, ground, water_z, report)
        if hz is None:
            continue
        z, sz = hz
        if name in HISM_ASSETS:
            instances.setdefault(name, []).append(unreal.Transform(
                unreal.Vector(p["x"] * 100, p["y"] * 100, z * 100), unreal.Rotator(roll=0, pitch=0, yaw=p["yaw_deg"]),
                unreal.Vector(1, 1, 1)))
        else:
            try:
                mesh_actor(sms[name], name.replace("SM_FinPark_", "FinPark "), p["x"], p["y"], z, p["yaw_deg"], sz)
            except Exception as e:  # noqa: BLE001
                unreal.log_warning(f"[finpark_krom] {name}: актор не поставлен — {e}")
                continue
        placed[name] = placed.get(name, 0) + 1
    for name, ts in sorted(instances.items()):
        try:
            hism_actor(sms[name], name.replace("SM_FinPark_", "FinPark ").replace("SM_Furn_", "FinPark ")) \
                .add_instances(ts, False, True)
        except Exception as e:  # noqa: BLE001
            unreal.log_warning(f"[finpark_krom] {name}: экземпляры не поставлены — {e}")
            placed.pop(name, None)

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    for name, line in sorted(report.items()):
        unreal.log(f"[finpark_krom] {name}: {line}")
    unreal.log(f"[finpark_krom] done: {dict(sorted(placed.items()))}, урез {water_z:+.2f} м, мимо Landscape "
               f"{ground.misses}, пропущены {skipped or 'нет'}, {time.time() - t0:.0f} с")


if __name__ == "__main__":
    main()
