"""shot_krom.py — снимок сцены в PNG с заданной точки: SceneCapture2D → render target → файл.

Вьюпорт редактора в фоне не перерисовывается, поэтому HighResShot из скрипта не срабатывает; захват сцены
от фокуса окна не зависит. Захват идёт в тиках редактора (post-tick callback), а не сразу в вызове: при
захвате прямо из Python-команды Nanite рисует только грубые кластеры — у героев пропадают окна, луковицы
выходят кубами. Поэтому shot() ставит снимок в очередь и сразу возвращает путь, файл появляется через
несколько кадров (старый файл удаляется заранее: пока его нет, снимок не готов).
Точки — локальные метры (D-013): x — север, y — восток, z — вверх.

    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); \
        import shot_krom; shot_krom.shot('zavelichye')"
    ... shot_krom.shot('my', eye=(-250, -650, 60), target=(0, -20, 5), out='media/renders/x.png')

Без out файл ложится в media/renders/shots/<имя>.png.
"""
import math
import os

import unreal

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE = (1600, 900)
FOV = 50.0
FRAMES = 3   # захватов на снимок: первый кадр после появления камеры бывает неполным

# ракурсы-кандидаты (REFERENCES, «Ракурсы-кандидаты») и служебные виды: (глаз, цель), метры
VIEWS = {
    "zavelichye": ((-250.0, -650.0, 25.0), (20.0, -40.0, 20.0)),     # с Завеличья через Великую
    "olginsky": ((-380.0, -130.0, 35.0), (40.0, 0.0, 15.0)),         # с Ольгинского моста
    "mouth": ((420.0, -330.0, 12.0), (120.0, -60.0, 15.0)),          # от устья Псковы на Кутекрому
    "top": ((20.0, 0.0, 900.0), (20.05, 0.0, 0.0)),                  # сверху, север — вверх кадра
    "oblique": ((-700.0, 350.0, 380.0), (20.0, -20.0, 0.0)),         # общий вид с юго-востока
    "high_nw": ((-1800.0, 1500.0, 450.0), (2500.0, -3000.0, 0.0)),   # с высоты на северо-запад: Кром, дельта, озеро
    # с высоты глаз (земля + 1,7 м) — для материалов (M4)
    "yard_cathedral": ((-40.0, 5.0, 0.55), (0.0, 0.0, 12.0)),        # южный фасад собора со двора
    "yard_belfry": ((-45.6, -17.7, 0.5), (-35.5, 50.7, 22.0)),       # колокольня, точка фото belfry_yard
    "yard_kutekroma": ((151.7, -76.1, 1.15), (235.0, -120.5, 8.0)),  # Кутекрома, точка фото kutekroma_yard
    "yard_wall": ((30.0, -45.0, 1.85), (42.0, -63.0, 4.0)),           # западная стена изнутри, ≈15 м
    "gate_persi": ((-130.0, 78.0, -8.35), (-106.2, 73.5, -4.0)),     # Великие ворота с газона Довмонтова города
}

_queue = []      # снимки в очереди: dict(name, eye, target, out, size, fov)
_state = {"handle": None, "cap": None, "rt": None, "frame": 0}

# Колбэк тика переживает reload модуля, а _state — нет: без handle старый колбэк не снять, и он ошибается
# на каждом тике (так было после cameras_krom.py). Поэтому handle живёт и в модуле unreal: при reload
# прежний колбэк снимается.
if getattr(unreal, "_shot_krom_handle", None) is not None:
    unreal.unregister_slate_post_tick_callback(unreal._shot_krom_handle)
unreal._shot_krom_handle = None


def look_at(eye, target):
    dx, dy, dz = (t - e for t, e in zip(target, eye))
    return unreal.Rotator(roll=0, pitch=math.degrees(math.atan2(dz, math.hypot(dx, dy))),
                          yaw=math.degrees(math.atan2(dy, dx)))


def shot(name, eye=None, target=None, out=None, size=SIZE, fov=FOV):
    """Поставить снимок в очередь; вернуть путь к PNG (появится через FRAMES кадров редактора)."""
    if eye is None:
        eye, target = VIEWS[name]
    out = os.path.join(REPO, out) if out else os.path.join(REPO, "media", "renders", "shots", f"{name}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)
    _queue.append(dict(name=name, eye=eye, target=target, out=out, size=size, fov=fov))
    if _state["handle"] is None:
        _state["handle"] = unreal._shot_krom_handle = unreal.register_slate_post_tick_callback(_tick)
    return out


def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _start(job):
    world = _world()
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    cap = actors.spawn_actor_from_class(unreal.SceneCapture2D, unreal.Vector(*(v * 100 for v in job["eye"])),
                                        look_at(job["eye"], job["target"]))
    rt = unreal.RenderingLibrary.create_render_target2d(world, job["size"][0], job["size"][1],
                                                       unreal.TextureRenderTargetFormat.RTF_RGBA8)
    c = cap.capture_component2d
    c.set_editor_property("texture_target", rt)
    c.set_editor_property("fov_angle", job["fov"])
    c.set_editor_property("capture_source", unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR)
    c.set_editor_property("capture_every_frame", False)
    # Lumen в захвате не считается — без этого небо не подсвечивает тени и они чёрные
    pp = c.get_editor_property("post_process_settings")
    pp.set_editor_property("override_dynamic_global_illumination_method", True)
    pp.set_editor_property("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.NONE)
    pp.set_editor_property("override_reflection_method", True)
    pp.set_editor_property("reflection_method", unreal.ReflectionMethod.SCREEN_SPACE)
    c.set_editor_property("post_process_settings", pp)
    _state.update(cap=cap, rt=rt, frame=0)


def _finish(job):
    unreal.RenderingLibrary.export_render_target(_world(), _state["rt"], os.path.dirname(job["out"]),
                                                 os.path.basename(job["out"]))
    unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(_state["cap"])
    _state.update(cap=None, rt=None, frame=0)
    unreal.log(f"[shot_krom] {job['name']}: {job['out']}")


def _tick(_dt):
    try:
        if not _queue:
            if _state["handle"] is not None:
                unreal.unregister_slate_post_tick_callback(_state["handle"])
            _state["handle"] = unreal._shot_krom_handle = None
            unreal.log("[shot_krom] очередь пуста")
            return
        job = _queue[0]
        if _state["cap"] is None:
            _start(job)
        _state["cap"].capture_component2d.capture_scene()
        _state["frame"] += 1
        if _state["frame"] >= FRAMES:
            _finish(_queue.pop(0))
    except Exception as e:  # ошибка в тике не должна повторяться каждый кадр
        unreal.log_error(f"[shot_krom] {e}")
        _queue.clear()
        if _state["cap"] is not None:
            unreal.get_editor_subsystem(unreal.EditorActorSubsystem).destroy_actor(_state["cap"])
        _state.update(cap=None, rt=None, frame=0)


def shot_photos(manifest="refs/photos/commons/manifest.json", eye_m=1.7, width=1200):
    """Модель с точек съёмки фото-референсов (photo_refs.py): тот же угол обзора и пропорции кадра.

    Глаз — над землёй или над водой (что выше) на eye_m, если в манифесте не задана отметка eye_z.
    Угол обзора — из фокусного в пересчёте на 35 мм (по умолчанию 50 мм). Снимки — media/renders/compare/<id>_model.png
    (в очереди; photo_refs.py compare их дожидается).
    """
    import json
    world = _world()
    meta = json.load(open(os.path.join(REPO, "refs", "dem", "heightmap_L_Krom.json"), encoding="utf-8"))
    water_z = meta["water_level_z_m"]
    outs = []
    for m in json.load(open(os.path.join(REPO, manifest), encoding="utf-8")):
        x, y = m["camera_xy"]
        if m.get("eye_z") is not None:
            z = m["eye_z"]
        else:
            hit = unreal.SystemLibrary.line_trace_single(
                world, unreal.Vector(x * 100, y * 100, 30000), unreal.Vector(x * 100, y * 100, -30000),
                unreal.TraceTypeQuery.ECC_VISIBILITY, False, [], unreal.DrawDebugTrace.NONE, True)
            ground = hit.to_tuple()[5].z / 100.0 if hit else water_z
            z = max(ground, water_z) + eye_m
        w, h = m["size"]
        f35 = m.get("focal35") or 50
        film_w = 36.0 if w >= h else 24.0  # у портретного кадра по ширине — короткая сторона
        fov = math.degrees(2 * math.atan(film_w / (2 * f35)))
        outs.append(shot(m["id"], (x, y, z), tuple(m["target"]), out=f"media/renders/compare/{m['id']}_model.png",
                         size=(width, round(width * h / w)), fov=fov))
    return outs
