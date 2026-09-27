"""init_unreal.py — выполняется редактором при запуске (Content/Python). PskovKrom, D-013: L_Krom держим
загруженным целиком.

Регион загрузки World Partition — LocationVolume «LoadAll» из scripts/level_krom.py. Редактор помнит между
запусками только регионы, загруженные руками; объём, загруженный из Python, после перезапуска снова выгружен,
и из 64 прокси Landscape видны 4 (проверено 2026-09-26). Поэтому раз в CHECK_S секунд: если открыт L_Krom,
а LoadAll не загружен, — загрузить. Ссылку на мир не храним, чтобы не держать его в памяти при смене уровня.
"""
import time

import unreal

LEVEL = "/Game/Krom/Maps/L_Krom."
CHECK_S = 3.0
_next = [0.0]


def _keep_krom_loaded(_dt):
    now = time.monotonic()
    if now < _next[0]:
        return
    _next[0] = now + CHECK_S
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_editor_world() if sub is not None else None
    if world is None or not world.get_path_name().startswith(LEVEL):
        return
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if isinstance(a, unreal.LocationVolume) and a.get_actor_label() == "LoadAll":
            if not a.is_loaded():
                a.load()
                unreal.log("[init_unreal] L_Krom: регион LoadAll загружен")
            return


# В процессе без редактора (рендер MRQ отдельным процессом UnrealEditor-Cmd -game, D-042) подсистем редактора нет:
# get_editor_subsystem возвращает None, и тик только сыпал бы ошибки в лог — не регистрируем.
if unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem) is not None:
    unreal.register_slate_post_tick_callback(_keep_krom_loaded)
