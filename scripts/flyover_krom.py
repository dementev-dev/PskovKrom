"""flyover_krom.py — черновик облёта SEQ_Flyover: Level Sequence с камерой по опорным точкам (M6).

Запуск:  python scripts/ue_run.py scripts/flyover_krom.py
Раскадровка без рендера (кадры вьюпорта в опорных и промежуточных точках):
    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import flyover_krom"
    (запуск модуля и есть сборка; для раскадровки — flyover_krom.storyboard(шаг, с) после сборки)

Маршрут — WAYPOINTS: (секунда, глаз, цель, фокусное), метры плана (X — север, Y — восток, Z от земли у собора).
Между опорами глаз и цель идут по кривой Катмулла — Рома, ключи камеры — каждые KEY_STEP с: так нет рывков
и перекрутов поворота, которые дала бы интерполяция поворотов между редкими ключами. Маршрут — черновик
агента: какие места и в каком порядке показывать, решает владелец.

Камера — CineCameraActor в уровне (тег generated:flyover_krom), в последовательности — possessable с дорожкой
трансформации и дорожкой смены камер. Идемпотентен: пересоздаёт камеру и ассет последовательности.
"""
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEQ_DIR, SEQ_NAME = "/Game/Krom/Cinematics", "SEQ_Flyover"
TAG = unreal.Name("generated:flyover_krom")
FOLDER = "Generated/flyover_krom"
FPS = 24
TICK = 24000   # разрешение тиков: доли кадра нужны MRQ для временных сэмплов (при TICK = FPS рендер встаёт в ошибку)
KEY_STEP = 0.25
APERTURE = 8.0  # f/8: без размытия, весь план резкий

# (с, глаз, цель, фокусное мм) — v2.1 (2026-09-27, правки по превью): с северо-запада к Стрелке, низко вдоль западной стены,
# к Ольгинскому мосту, над Довмонтовым городом к Святым воротам, вдоль Псковы (Козьмы и Дамиана, мост 2024 г.),
# финал — с северо-востока на весь Кром. Порядок и длительность — решение владельца (D-033).
WAYPOINTS = [
    (0.0, (820.0, -620.0, 160.0), (150.0, -80.0, 10.0), 28.0),
    (10.0, (520.0, -380.0, 45.0), (300.0, -160.0, 10.0), 28.0),
    (18.0, (380.0, -250.0, 6.0), (240.0, -120.0, 12.0), 28.0),
    (28.0, (170.0, -190.0, 10.0), (60.0, -80.0, 18.0), 28.0),
    (38.0, (-60.0, -220.0, 22.0), (0.0, -20.0, 25.0), 28.0),
    (48.0, (-330.0, -160.0, 40.0), (20.0, 0.0, 20.0), 32.0),
    (58.0, (-250.0, 50.0, 50.0), (-165.0, 125.0, 4.0), 30.0),   # над Довмонтовым городом на Святые ворота и Пскову
    (68.0, (0.0, 120.0, 70.0), (125.0, 292.0, 10.0), 32.0),      # вдоль Псковы: Козьмы и Дамиана с Примостья, Запсковье
    (78.0, (200.0, 90.0, 25.0), (240.0, 0.0, -8.0), 28.0),       # мост 2024 г. и восточная стена
    (90.0, (600.0, 350.0, 220.0), (0.0, -20.0, 0.0), 28.0),      # финал: с северо-востока на весь Кром
]

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)


def catmull(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                 for a, b, c, d in zip(p0, p1, p2, p3))


def sample(t):
    """(глаз, цель, фокусное) в момент t, с."""
    w = WAYPOINTS
    t = min(max(t, w[0][0]), w[-1][0])
    i = max(k for k in range(len(w) - 1) if w[k][0] <= t) if t < w[-1][0] else len(w) - 2
    u = (t - w[i][0]) / (w[i + 1][0] - w[i][0])
    pts = [w[max(i - 1, 0)], w[i], w[i + 1], w[min(i + 2, len(w) - 1)]]
    eye = catmull(*(p[1] for p in pts), u)
    tgt = catmull(*(p[2] for p in pts), u)
    focal = w[i][3] + (w[i + 1][3] - w[i][3]) * u
    return eye, tgt, focal


def rotation(eye, tgt):
    dx, dy, dz = (b - a for a, b in zip(eye, tgt))
    return math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx))


def build():
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
    path = f"{SEQ_DIR}/{SEQ_NAME}"
    if assets.does_asset_exist(path):  # тот же ассет, очищенный: удалённый держится в памяти, и создать заново нельзя
        seq = unreal.load_asset(path)
        for b in seq.get_bindings():
            b.remove()
        for t in seq.get_tracks():
            seq.remove_track(t)
    else:
        seq = unreal.AssetToolsHelpers.get_asset_tools().create_asset(SEQ_NAME, SEQ_DIR, unreal.LevelSequence,
                                                                      unreal.LevelSequenceFactoryNew())
    duration = WAYPOINTS[-1][0]
    frames = int(round(duration * FPS))
    seq.set_display_rate(unreal.FrameRate(FPS, 1))
    seq.set_tick_resolution(unreal.FrameRate(TICK, 1))  # ключи ниже — в кадрах показа (time_unit по умолчанию)
    seq.set_playback_start(0)
    seq.set_playback_end(frames)

    eye, tgt, focal = sample(0.0)
    cam = actors.spawn_actor_from_class(unreal.CineCameraActor, unreal.Vector(*(v * 100 for v in eye)))
    cam.set_actor_label("CAM_Flyover")
    cam.set_folder_path(FOLDER)
    cam.set_editor_property("tags", [TAG])
    cam.set_editor_property("is_spatially_loaded", False)
    cc = cam.get_cine_camera_component()
    fs = cc.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    cc.set_editor_property("focus_settings", fs)
    cc.set_editor_property("current_aperture", APERTURE)

    binding = seq.add_possessable(cam)
    track = binding.add_track(unreal.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range(0, frames)
    ch = section.get_all_channels()  # Location.X…Z, Rotation.X…Z (крен, тангаж, рыскание), Scale — имена с суффиксом
    loc = ch[0:3]
    pitch_ch, yaw_ch = ch[4], ch[5]
    comp_binding = seq.add_possessable(cc)
    focal_track = comp_binding.add_track(unreal.MovieSceneFloatTrack)
    focal_track.set_property_name_and_path("CurrentFocalLength", "CurrentFocalLength")
    focal_section = focal_track.add_section()
    focal_section.set_range(0, frames)
    focal_ch = focal_section.get_all_channels()[0]

    prev_yaw = None
    n = int(round(duration / KEY_STEP))
    for k in range(n + 1):
        t = k * KEY_STEP
        f = unreal.FrameNumber(int(round(t * FPS)))
        eye, tgt, focal = sample(t)
        pitch, yaw = rotation(eye, tgt)
        if prev_yaw is not None:  # без скачков через ±180°
            yaw += 360.0 * round((prev_yaw - yaw) / 360.0)
        prev_yaw = yaw
        for c, v in zip(loc, eye):
            c.add_key(f, v * 100.0)
        pitch_ch.add_key(f, pitch)
        yaw_ch.add_key(f, yaw)
        focal_ch.add_key(f, focal)

    cut_track = seq.add_track(unreal.MovieSceneCameraCutTrack)
    cut = cut_track.add_section()
    cut.set_range(0, frames)
    cut.set_camera_binding_id(seq.get_binding_id(binding))
    assets.save_loaded_asset(seq)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
    unreal.log(f"[flyover_krom] {path}: {duration:.0f} с, {frames} кадров, ключей {n + 1}")
    return seq


def storyboard(step=5.0, prefix="flyover"):
    """Кадры вьюпорта по маршруту каждые step с (облака и Lumen догоняют — снимать дважды) → пути PNG."""
    import view_krom
    out = []
    t = 0.0
    while t <= WAYPOINTS[-1][0] + 1e-6:
        eye, tgt, _ = sample(t)
        out.append(view_krom.view(f"{prefix}_{t:04.0f}", eye=eye, target=tgt,
                                  out=f"media/renders/views/{prefix}_{int(t):03d}.png"))
        t += step
    return out


build()
