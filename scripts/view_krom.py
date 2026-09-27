"""view_krom.py — снимок настоящего вьюпорта редактора в PNG: Lumen, облака, автоэкспозиция — как в окне.

В отличие от shot_krom.py (SceneCapture без Lumen, для проверки геометрии) снимает сам вьюпорт уровня через
EditorAppToolset.CaptureViewport (Unreal MCP) и сразу пишет файл. Размер — как у окна вьюпорта, поле зрения —
как у камеры вьюпорта (по умолчанию 90°). Камера вьюпорта после снимка остаётся в точке снимка.

    python scripts/ue_run.py -c "import sys; sys.path.insert(0, 'D:/PskovKrom/scripts'); import view_krom; view_krom.view('high_nw')"

Ракурсы — VIEWS из shot_krom (координаты в метрах). Снимок синхронный: файл готов сразу после вызова.
Сразу после смены света или тумана кеши Lumen, теней и автоэкспозиция догоняют сцену за несколько кадров
редактора: менять настройки одной командой ue_run, снимать — следующей (внутри одной команды тиков нет).
"""
import base64
import os
import sys

import unreal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shot_krom import REPO, VIEWS, look_at  # noqa: E402  (без reload: не сбрасывать очередь снимков shot_krom)


def clouds(on):
    """Облака (актор «Clouds» из level_krom.py) — вкл./выкл. В редакторе они выключены ради скорости вьюпорта:
    включить, снять следующей командой ue_run, выключить. Не сохранять уровень с включёнными облаками."""
    a = next((x for x in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
              if x.get_actor_label() == "Clouds"), None)
    if a is None:
        raise RuntimeError("нет актора Clouds — сначала level_krom.py")
    a.get_component_by_class(unreal.VolumetricCloudComponent).set_visibility(on)


def view(name, eye=None, target=None, out=None):
    """Снять вьюпорт из eye на target (м); вернуть путь к PNG."""
    if eye is None:
        eye, target = VIEWS[name]
    out = os.path.join(REPO, out) if out else os.path.join(REPO, "media", "renders", "views", f"{name}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t = unreal.Transform(unreal.Vector(*(v * 100 for v in eye)), look_at(eye, target), unreal.Vector(1, 1, 1))
    r = unreal.EditorAppToolset.get_default_object().call_method("CaptureViewport", args=(t, None, False))
    data = r.get_editor_property("image").get_editor_property("data")
    if not data:
        raise RuntimeError(f"view_krom: пустой снимок {name}")
    with open(out, "wb") as f:
        f.write(base64.b64decode(data))
    return out
