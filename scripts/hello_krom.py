"""hello_krom.py — smoke test: Python в редакторе UE работает, соглашения по осям и масштабу понятны.

Запуск в редакторе:  Output Log → Cmd → Python →  py "D:/PskovKrom/scripts/hello_krom.py"
Снаружи:             python scripts/ue_run.py scripts/hello_krom.py
Идемпотентен: удаляет всё, что создал ранее (тег generated:hello_krom), и создаёт заново.

Создаёт:
  - куб 1×1×1 м в начале координат (будущий центр Троицкого собора);
  - «стрелку на север»: вытянутый брусок 10 м вдоль +X;
  - «стрелку на восток»: брусок 5 м вдоль +Y.
"""
import unreal

TAG = unreal.Name("generated:hello_krom")
CUBE = "/Engine/BasicShapes/Cube.Cube"  # базовый куб = 100 uu = 1 м

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def cleanup():
    removed = 0
    for a in actors.get_all_level_actors():
        if TAG in a.tags:
            actors.destroy_actor(a)
            removed += 1
    unreal.log(f"[hello_krom] removed {removed} old actors")


def box(label, location_m, size_m):
    """Бокс с центром в location_m (метры) и размерами size_m (метры)."""
    loc = unreal.Vector(*(v * 100.0 for v in location_m))
    a = actors.spawn_actor_from_class(unreal.StaticMeshActor, loc)
    a.static_mesh_component.set_static_mesh(unreal.load_asset(CUBE))
    a.set_actor_scale3d(unreal.Vector(*size_m))  # базовый куб 1 м → scale = размер в метрах
    a.set_actor_label(label)
    a.set_folder_path("Generated/hello_krom")
    a.set_editor_property("tags", [TAG])
    return a


cleanup()
box("Origin_1m", (0, 0, 0.5), (1, 1, 1))
box("North_+X_10m", (5, 0, 0.1), (10, 0.3, 0.2))
box("East_+Y_5m", (0, 2.5, 0.1), (0.3, 5, 0.2))
unreal.log("[hello_krom] done: origin cube, +X north (10 m), +Y east (5 m)")
