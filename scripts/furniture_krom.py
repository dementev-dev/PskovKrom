"""furniture_krom.py — малые формы у Крома в L_Krom: фонари, скамейки, урны — HISM по точкам (M5).

Запуск (сначала точки и модели):
    PYTHONIOENCODING=utf-8 .venv/Scripts/python scripts/furniture_points.py    # build/furniture/points.json
    python scripts/bl_run.py scripts/blender/street_furniture.py               # build/blender/SM_Furn_*.glb
    python scripts/ue_run.py scripts/furniture_krom.py

Вечер (M6) — свет фонарей и свечение рассеивателей одной командой, снимать — следующей:
    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import importlib, furniture_krom; importlib.reload(furniture_krom); furniture_krom.lights(True)"
    (lights(False) — снова день; save=True — сохранить состояние в уровне и материале)

Меши — build/blender/SM_Furn_<Имя>.glb → /Game/Krom/Environment/Furniture (Nanite, без коллизии). Материалы по имени
слота, как у героев: ключ krom_plan.COLORS → M_Krom<Ключ> (materials_krom.py), пока его нет — MI_BO_<Ключ>;
им ставится флаг used_with_instanced_static_meshes (HISM; редактор поставил бы его сам и пометил ассет изменённым).
Слот glow (рассеиватель, стёкла) — MI_KromLampGlow от M_KromLampGlow в /Game/Krom/Materials/Furniture: матовое
стекло днём, вечером — свечение по параметру Glow. Текстур нет.
Свет: на каждый фонарь — PointLightComponent без теней (LIGHT, гипотеза) на одном акторе «Furniture lamp lights»:
по умолчанию выключен (LIGHTS_ON). Сотня точечных источников без теней стоит мало, но замера бюджета ещё нет:
если дорого, остаётся одно свечение (оно видно, но дорожку под программным Lumen почти не освещает).

Расстановка: вид точки (kind) → модель по заголовку points.json (kinds), поворот — yaw_deg, высота — трассой по
Landscape при каждом запуске (рельеф меняют terrain_krom и дороги D-038; z в точках нет). Один актор с
HierarchicalInstancedStaticMesh на модель: сотни отдельных акторов — сотни файлов World Partition.

Идемпотентен: удаляет свои акторы (тег generated:furniture_krom), переимпортирует меши в те же ассеты,
пересобирает материал свечения и сохраняет.
"""
import importlib
import json
import math
import os
import sys
import time

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krom_geo as geo  # noqa: E402
import palette_krom  # noqa: E402

importlib.reload(palette_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:furniture_krom")
LIGHTS_TAG = unreal.Name("furniture_krom:lights")
FOLDER = "Generated/furniture_krom"
FURN_DIR = "/Game/Krom/Environment/Furniture"
MAT_DIR = "/Game/Krom/Materials/Furniture"
GLOW_MAT = f"{MAT_DIR}/M_KromLampGlow"
GLOW_MI = f"{MAT_DIR}/MI_KromLampGlow"
BO_DIR = "/Game/Krom/Blockout"
STAGING = f"{FURN_DIR}/_import"
GLB_DIR = os.path.join(geo.REPO, "build", "blender")
REPORT = os.path.join(GLB_DIR, "furniture_report.json")
POINTS = os.path.join(geo.REPO, "build", "furniture", "points.json")
TRACE_Z_M = 300.0

GLOW_BASE = (0.8, 0.8, 0.78)      # матовое стекло днём
GLOW_RGB = (1.0, 0.8, 0.55)       # тёплый белый вечером (гип.: на фото вечером фонари жёлтые)
GLOW_ON = 25.0                    # яркость свечения вечером (параметр Glow), подобрать по кадру M6
LIGHTS_ON = False                 # днём свет и свечение выключены
LIGHT = {"lumens": 1500.0, "radius_m": 9.0, "kelvin": 3500.0, "source_m": 0.05}   # гипотеза: светодиод 15–20 Вт

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
mel = unreal.MaterialEditingLibrary
P = unreal.MaterialProperty
X = palette_krom.expr


def glow_material():
    """M_KromLampGlow (матовое стекло + свечение GlowColor × Glow) и его MI_KromLampGlow; Glow — по LIGHTS_ON."""
    mat = palette_krom.fresh_material(GLOW_MAT)
    base = X(mat, unreal.MaterialExpressionConstant3Vector, -500, -200, constant=unreal.LinearColor(*GLOW_BASE, 1))
    mel.connect_material_property(base, "", P.MP_BASE_COLOR)
    mel.connect_material_property(X(mat, unreal.MaterialExpressionConstant, -500, 0, r=0.35), "", P.MP_ROUGHNESS)
    color = X(mat, unreal.MaterialExpressionVectorParameter, -800, 200, parameter_name="GlowColor",
              default_value=unreal.LinearColor(*GLOW_RGB, 1))
    glow = X(mat, unreal.MaterialExpressionScalarParameter, -800, 400, parameter_name="Glow", default_value=0.0)
    mul = X(mat, unreal.MaterialExpressionMultiply, -500, 300)
    mel.connect_material_expressions(color, "", mul, "A")
    mel.connect_material_expressions(glow, "", mul, "B")
    mel.connect_material_property(mul, "", P.MP_EMISSIVE_COLOR)
    for flag in ("used_with_nanite", "used_with_instanced_static_meshes"):
        mat.set_editor_property(flag, True)
    mel.recompile_material(mat)
    assets.save_loaded_asset(mat)
    if assets.does_asset_exist(GLOW_MI):
        mi = unreal.load_asset(GLOW_MI)
    else:
        mi = tools.create_asset(GLOW_MI.rsplit("/", 1)[1], MAT_DIR, unreal.MaterialInstanceConstant,
                                unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, mat)
    mel.set_material_instance_scalar_parameter_value(mi, "Glow", GLOW_ON if LIGHTS_ON else 0.0)
    mel.update_material_instance(mi)
    assets.save_loaded_asset(mi)
    return mi


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
    """build/blender/<name>.glb → StaticMesh FURN_DIR/<name> (Nanite, без коллизии); слоты по mats (как trees_krom)."""
    glb = os.path.join(GLB_DIR, f"{name}.glb")
    if not os.path.exists(glb):
        raise RuntimeError(f"нет {glb} — сначала python scripts/bl_run.py scripts/blender/street_furniture.py")
    path = f"{FURN_DIR}/{name}"
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
    """Высота Landscape (м) трассой сверху; актор над землёй трасса проходит насквозь (как в trees_krom)."""

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


def lights_actor(positions, on):
    """Один актор «Furniture lamp lights»: корень в начале координат и по PointLightComponent на фонарь."""
    a = new_actor("Furniture lamp lights", [TAG, LIGHTS_TAG])
    root_h, root = add_component(actor_handle(a), unreal.SceneComponent, "lights root")
    root.set_mobility(unreal.ComponentMobility.MOVABLE)
    for x, y, z in positions:
        _, c = add_component(root_h, unreal.PointLightComponent, "lamp light")
        c.set_mobility(unreal.ComponentMobility.MOVABLE)
        c.set_world_location(unreal.Vector(x * 100, y * 100, z * 100), False, False)
        if hasattr(unreal, "LightUnits"):
            c.set_intensity_units(unreal.LightUnits.LUMENS)
            c.set_intensity(LIGHT["lumens"])
        else:                                   # единицы по умолчанию — канделы: 1 кд = 4π лм у точечного
            c.set_intensity(LIGHT["lumens"] / (4 * math.pi))
        c.set_attenuation_radius(LIGHT["radius_m"] * 100)
        c.set_source_radius(LIGHT["source_m"] * 100)
        c.set_use_temperature(True)
        c.set_temperature(LIGHT["kelvin"])
        c.set_cast_shadows(False)
        c.set_visibility(on)
    return a


def lights(on=True, save=False):
    """Вечер (M6): свет фонарей и свечение рассеивателей — вкл./выкл.; save — сохранить уровень и материал."""
    mi = unreal.load_asset(GLOW_MI)
    mel.set_material_instance_scalar_parameter_value(mi, "Glow", GLOW_ON if on else 0.0)
    mel.update_material_instance(mi)
    n = 0
    for a in actors.get_all_level_actors():
        if LIGHTS_TAG in a.tags:
            for c in a.get_components_by_class(unreal.PointLightComponent):
                c.set_visibility(on)
                n += 1
    if save:
        assets.save_loaded_asset(mi)
        unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[furniture_krom] lights {'on' if on else 'off'}: {n} источников, Glow {GLOW_ON if on else 0.0}")


def main():
    t0 = time.time()
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if world.get_path_name().split(".")[0] != LEVEL:
        levels.load_level(LEVEL)
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    with open(REPORT, encoding="utf-8") as f:
        report = json.load(f)
    with open(POINTS, encoding="utf-8") as f:
        data = json.load(f)
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    mats = {"glow": glow_material()}
    kinds = {k: v["asset"] for k, v in data["kinds"].items()}
    used = sorted({kinds[p["kind"]] for p in data["points"]})
    sms = {name: import_mesh(name, mats) for name in used}

    ground = Ground(world)
    transforms, lamps, count = {}, [], {}
    for p in data["points"]:
        name = kinds[p["kind"]]
        z = ground(p["x"], p["y"])
        if z is None:
            continue
        transforms.setdefault(name, []).append(unreal.Transform(
            unreal.Vector(p["x"] * 100, p["y"] * 100, z * 100), unreal.Rotator(roll=0, pitch=0, yaw=p["yaw_deg"]),
            unreal.Vector(1, 1, 1)))
        count[f"{p['kind']}/{p['source']}"] = count.get(f"{p['kind']}/{p['source']}", 0) + 1
        light_z = report.get(name, {}).get("light_z_m")
        if light_z:
            lamps.append((p["x"], p["y"], z + light_z))
    for name, ts in sorted(transforms.items()):
        hism_actor(sms[name], f"Furniture {name}").add_instances(ts, False, True)
    try:                     # свет — необязательная часть: без него малые формы всё равно сохраняются
        lights_actor(lamps, LIGHTS_ON)
    except Exception as e:  # noqa: BLE001
        unreal.log_warning(f"[furniture_krom] свет не поставлен: {e}")
        lamps = []

    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    unreal.log(f"[furniture_krom] done: {sum(len(ts) for ts in transforms.values())} экземпляров в "
               f"{len(transforms)} HISM, {len(lamps)} источников света ({'вкл' if LIGHTS_ON else 'выкл'}), "
               f"мимо Landscape {ground.misses}, по видам {dict(sorted(count.items()))}, {time.time() - t0:.0f} с")


if __name__ == "__main__":   # ue_run.py выполняет файл в словаре __main__; import furniture_krom — только lights()
    main()
