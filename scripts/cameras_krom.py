"""cameras_krom.py — ракурсы-кандидаты как CineCameraActor и их снимки (M2).

Запуск:  python scripts/ue_run.py scripts/cameras_krom.py
Ракурсы — docs/REFERENCES.md, «Ракурсы-кандидаты». Точки — локальные метры (D-013). Глаз стоит на высоте
человека над Landscape (трасса) или на заданной отметке — над водой и на мосту, которых в рельефе нет.

Идемпотентен: пересоздаёт свои камеры (тег generated:cameras_krom) и снимки
media/renders/shots/cam_<имя>.png (через shot_krom). Сохраняет уровень.
"""
import importlib
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shot_krom  # noqa: E402

shot_krom = importlib.reload(shot_krom)

TAG = unreal.Name("generated:cameras_krom")
FOLDER = "Generated/cameras_krom"
EYE_M = 1.7
FILMBACK_W_MM = 23.76  # «16:9 Digital Film», по умолчанию у CineCamera

# имя → (глаз xy, отметка глаза: None — земля + EYE_M, число — абсолютная Z, м), цель xyz, фокусное, мм, что это
CAMERAS = {
    "Zavelichye": ((-213.0, -271.0), None, (10.0, -20.0, 25.0), 28.0,
                   "Завеличье у Ольгина креста (OSM node 998181505), на 25 м вглубь — на бровке: сам крест "
                   "в модели попал на откос берега. Открыточный вид через Великую"),
    "OlginskyBridge": ((-364.0, -116.0), -4.0, (40.0, 0.0, 20.0), 30.0,
                       "середина Ольгинского моста, глаз ≈9 м над водой (гип.)"),
    "PskovaMouth": ((415.0, -300.0), -11.2, (240.0, -110.0, 12.0), 30.0,
                    "с воды Великой напротив устья Псковы: Плоская, Кутекрома, стена к собору"),
}

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
levels = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def ground(world, x, y):
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(x * 100, y * 100, 30000), unreal.Vector(x * 100, y * 100, -30000),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, [], unreal.DrawDebugTrace.NONE, True)
    if hit is None or not isinstance(hit.to_tuple()[9], unreal.LandscapeProxy):
        raise RuntimeError(f"нет Landscape под ({x}, {y})")
    return hit.to_tuple()[5].z / 100.0


def main():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
    for name, (xy, z, target, focal, note) in CAMERAS.items():
        eye = (xy[0], xy[1], ground(world, *xy) + EYE_M if z is None else z)
        cam = actors.spawn_actor_from_class(unreal.CineCameraActor, unreal.Vector(*(v * 100 for v in eye)),
                                            shot_krom.look_at(eye, target))
        cam.set_actor_label(f"CAM_{name}")
        cam.set_folder_path(FOLDER)
        cam.set_editor_property("tags", [TAG])
        cam.set_editor_property("is_spatially_loaded", False)
        cam.get_cine_camera_component().set_editor_property("current_focal_length", focal)
        fov = math.degrees(2 * math.atan(FILMBACK_W_MM / (2 * focal)))
        shot_krom.shot(f"cam_{name}", eye, target, out=f"media/renders/shots/cam_{name}.png", fov=fov)
        unreal.log(f"[cameras_krom] CAM_{name}: глаз ({eye[0]:.0f}, {eye[1]:.0f}, {eye[2]:.1f}) м, "
                   f"{focal:.0f} мм (FOV {fov:.0f}°) — {note}")
    levels.save_current_level()


main()
