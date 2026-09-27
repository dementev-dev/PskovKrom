"""ue_run.py — запуск Python в открытом редакторе UE снаружи (из терминала или агентом).

Использует штатный remote_execution.py из Python Editor Script Plugin. В проекте должна быть
включена Remote Execution (Project Settings → Python → Enable Remote Execution, см. DefaultEngine.ini).

    python scripts/ue_run.py scripts/hello_krom.py      # выполнить файл
    python scripts/ue_run.py -c "import unreal; print(unreal.SystemLibrary.get_engine_version())"

Код возврата 0 — скрипт отработал, 1 — ошибка в скрипте, 2 — редактор не найден.
Путь к движку берётся из UE_ROOT, по умолчанию D:/Games/Epic Games/UE_5.8.
"""
import argparse
import os
import sys
import time

UE_ROOT = os.environ.get("UE_ROOT", "D:/Games/Epic Games/UE_5.8")
sys.path.insert(0, os.path.join(UE_ROOT, "Engine/Plugins/Experimental/PythonScriptPlugin/Content/Python"))
import remote_execution as rex  # noqa: E402

PROJECT = "Krom"


PROBE = "__import__('unreal').get_editor_subsystem(__import__('unreal').UnrealEditorSubsystem) is not None"


def find_node(remote, timeout_s):
    """Ждёт, пока редактор с нашим проектом ответит на multicast ping. Если проект открыт в нескольких процессах
    (редактор и рендер MRQ отдельным процессом UnrealEditor-Cmd -game, D-042: Remote Execution включена и там), у
    каждого спрашивает PROBE — есть ли подсистемы редактора — и берёт редактор (2026-09-27: команда попала в рендер)."""
    deadline = time.time() + timeout_s
    found = []
    while time.time() < deadline:
        found = [n for n in remote.remote_nodes if n.get("project_name") == PROJECT]
        if found:
            time.sleep(1.0)  # дать ответить остальным процессам проекта
            found = [n for n in remote.remote_nodes if n.get("project_name") == PROJECT]
            break
        time.sleep(0.2)
    if len(found) == 1:
        return found[0]["node_id"]
    for node in found:
        try:
            remote.open_command_connection(node["node_id"])
            r = remote.run_command(PROBE, unattended=True, exec_mode=rex.MODE_EVAL_STATEMENT)
        finally:
            remote.close_command_connection()
        if r.get("success") and str(r.get("result")).strip() == "True":
            return node["node_id"]
    return None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", nargs="?", help="путь к .py-файлу")
    p.add_argument("-c", "--code", help="строка Python-кода вместо файла")
    p.add_argument("--timeout", type=float, default=5.0, help="сколько секунд искать редактор")
    args = p.parse_args()
    if bool(args.file) == bool(args.code):
        p.error("нужен либо файл, либо -c")

    command = args.code or os.path.abspath(args.file).replace("\\", "/")

    remote = rex.RemoteExecution()
    for stream in (sys.stdout, sys.stderr):  # консоль Windows в cp1251: чужие символы — «?», а не падение
        stream.reconfigure(errors="replace")

    remote.start()
    try:
        node_id = find_node(remote, args.timeout)
        if not node_id:
            print(f"[ue_run] редактор с проектом {PROJECT} не найден (открыт? Remote Execution включена?)", file=sys.stderr)
            return 2
        remote.open_command_connection(node_id)
        result = remote.run_command(command, unattended=True, exec_mode=rex.MODE_EXEC_FILE)
    finally:
        remote.stop()

    for line in result.get("output", []):
        stream = sys.stderr if line["type"] in ("Warning", "Error") else sys.stdout
        print(line["output"].rstrip(), file=stream)
    if not result["success"]:
        print(result["result"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
