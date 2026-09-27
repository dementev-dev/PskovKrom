"""level_krom.py — основной уровень L_Krom (World Partition): небо, солнце, облака, дымка (D-013, D-024).

Запуск:  python scripts/ue_run.py scripts/level_krom.py
Идемпотентен: создаёт уровень, если его нет, открывает его и пересоздаёт свои акторы (тег generated:level_krom).

Свет — пресет времени суток из light_krom.py (по умолчанию «ясный день», D-024; рассвет в тумане и закат — D-028):
числа солнца и дымки живут там, здесь только акторы. Облака — VolumetricCloud с материалом движка, тени облаков
на земле. В редакторе
облака выключены (CLOUDS_VISIBLE): на RTX 3060 Laptop с ними вьюпорт тормозит. Для кадров — view_krom.clouds(True).
Дымка в два слоя:
  - у земли — растворяет край кольца горизонта в 18 км (horizon_krom.py, D-023). Свой цвет обязателен: без него
    туман берёт цвет от неба и выходит тёмно-синим — отсюда было «море» за краем мира. Цвет — в тех же единицах,
    что солнце: при другой яркости солнца его нужно менять вместе с ней;
  - высокий тонкий — затягивает небо у горизонта, иначе с высоты между небом и дымкой видна резкая черта.
Подбор — по снимкам вьюпорта (view_krom.py): SceneCapture (shot_krom.py) показывает дымку иначе.
Регион загрузки World Partition в редакторе — LocationVolume «LoadAll» на весь Landscape (load_all).
"""
import importlib
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import light_krom  # noqa: E402

importlib.reload(light_krom)

LEVEL = "/Game/Krom/Maps/L_Krom"
TAG = unreal.Name("generated:level_krom")
FOLDER = "Generated/level_krom"
CLOUDS_VISIBLE = False  # в редакторе — выкл. (скорость вьюпорта), для кадров и рендера включать
LOAD_HALF_M = 1100.0  # регион загрузки World Partition в редакторе: Landscape ±1008 м с запасом

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def current_level():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world().get_path_name().split(".")[0]


def open_level():
    if current_level() == LEVEL:
        return "already open"
    if unreal.get_editor_subsystem(unreal.EditorAssetSubsystem).does_asset_exist(LEVEL):
        levels.load_level(LEVEL)
        return "loaded"
    if not levels.new_level(LEVEL, True):
        raise RuntimeError(f"не удалось создать {LEVEL}")
    return "created"


def spawn(cls, label, location_m=(0, 0, 0), rotation=(0, 0, 0)):
    a = actors.spawn_actor_from_class(cls, unreal.Vector(*(v * 100.0 for v in location_m)),
                                      unreal.Rotator(roll=rotation[0], pitch=rotation[1], yaw=rotation[2]))
    a.set_actor_label(label)
    a.set_folder_path(FOLDER)
    a.set_editor_property("tags", [TAG])
    a.set_editor_property("is_spatially_loaded", False)  # всегда загружен, без стриминга ячеек
    return a


def build():
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)

    sun = spawn(unreal.DirectionalLight, "Sun", (0, 0, 50))  # направление и яркость — light_krom.apply
    light = sun.light_component
    light.set_editor_property("atmosphere_sun_light", True)
    light.set_editor_property("cast_cloud_shadows", True)

    spawn(unreal.SkyAtmosphere, "SkyAtmosphere")
    sky = spawn(unreal.SkyLight, "SkyLight", (0, 0, 10))
    sky.light_component.set_editor_property("real_time_capture", True)
    clouds = spawn(unreal.VolumetricCloud, "Clouds")  # материал движка m_SimpleVolumetricCloud, слой 5–15 км
    clouds.get_component_by_class(unreal.VolumetricCloudComponent).set_visibility(CLOUDS_VISIBLE)

    spawn(unreal.ExponentialHeightFog, "HeightFog")
    spawn(unreal.PostProcessVolume, "Post").set_editor_property("unbound", True)  # поправка экспозиции пресета
    light_krom.apply(light_krom.DEFAULT)

    # Точка появления игрока — к югу от собора, лицом на север.
    spawn(unreal.PlayerStart, "PlayerStart", (-60, 0, 1), rotation=(0, 0, 0))
    load_all()


def load_all():
    """Регион «всё» для World Partition в редакторе: LocationVolume на весь Landscape, загруженный.
    Без него после перезапуска редактор поднимает только ячейки у начала координат — 4 прокси Landscape из 64,
    остальное «под водой», а трасса земли (walls_krom, heroes_krom) промахивается. Объём, загруженный из Python,
    редактор между запусками не помнит (помнит только загруженные руками) — после запуска его загружает
    Krom/Content/Python/init_unreal.py. Объём спавнится через фабрику актёров: только так у него есть куб-браш
    (200 uu), spawn_actor_from_class даёт объём без формы."""
    vol = actors.spawn_actor_from_object(unreal.LocationVolume.static_class(), unreal.Vector(0, 0, 0))
    vol.set_actor_label("LoadAll")
    vol.set_folder_path(FOLDER)
    vol.set_editor_property("tags", [TAG])
    vol.set_editor_property("is_spatially_loaded", False)
    vol.set_actor_scale3d(unreal.Vector(LOAD_HALF_M, LOAD_HALF_M, LOAD_HALF_M / 4))  # куб ±100 uu → ±LOAD_HALF_M м
    vol.get_component_by_class(unreal.BrushComponent).set_editor_property("visible", False)  # рамка на полнеба
    vol.load()
    # на случай ячеек за пределами объёма — догружаем всё остальное до следующего перезапуска
    wpl = unreal.WorldPartitionBlueprintLibrary
    wpl.load_actors([d.get_editor_property("guid") for d in wpl.get_actor_descs()
                     if d.get_editor_property("is_spatially_loaded")])


state = open_level()
build()
levels.save_current_level()
unreal.log(f"[level_krom] {LEVEL}: {state}, light rebuilt, saved")
