#!/usr/bin/env python3
"""Drive the Bench Screen (index.html in this folder) by writing guide_state.json.

Import the functions from your MCP server, or use the command line:

  python3 guide_control.py show D2 "Band goes to the lower pad."
  python3 guide_control.py placed D2
  python3 guide_control.py inspect "Checking the power stage."
  python3 guide_control.py flag C4 2 cold "reheat 3 s"
  python3 guide_control.py clear
  python3 guide_control.py done --led
  python3 guide_control.py reset

The page polls the file four times a second, so a change shows up within about 250 ms.
"""
import json
import os
import pathlib
import sys
import tempfile
import time

STATE = pathlib.Path(__file__).with_name("guide_state.json")
PARTS = ["D2", "R1", "D1", "C4", "C13"]  # build order, same as bench-screen.js


def _read():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {"ref": None, "mode": "idle", "placed": [], "flags": [], "message": ""}


def _write(state):
    state["t"] = time.time()
    fd, tmp = tempfile.mkstemp(dir=STATE.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)  # atomic, so the page never reads a half-written file
    return state


def _check(ref):
    if ref not in PARTS:
        raise ValueError(f"unknown part {ref!r}; expected one of {', '.join(PARTS)}")


def show(ref, message=""):
    """Light up the footprint where `ref` goes."""
    _check(ref)
    s = _read()
    s.update(ref=ref, mode="place", message=message)
    return _write(s)


def placed(ref):
    """Mark `ref` as soldered (filled step dot, body drawn on the board)."""
    _check(ref)
    s = _read()
    s["placed"] = [p for p in PARTS if p in set(s.get("placed", [])) | {ref}]
    return _write(s)


def inspect(message=""):
    s = _read()
    s.update(mode="inspect", message=message)
    return _write(s)


def flag(ref, pad, kind="cold", text=""):
    """Circle one pad, e.g. a cold joint the wrist camera found. kind: cold | bad | ok."""
    _check(ref)
    s = _read()
    flags = [f for f in s.get("flags", []) if not (f["ref"] == ref and f["pad"] == int(pad))]
    flags.append({"ref": ref, "pad": int(pad), "kind": kind, "text": text or kind})
    s.update(ref=ref, mode="reheat" if kind in ("cold", "bad") else "ok", flags=flags, message="")
    return _write(s)


def clear():
    s = _read()
    s["flags"] = []
    return _write(s)


def done(led=False, message=""):
    s = _read()
    s.update(ref=None, mode="done", placed=list(PARTS), flags=[], ledOn=bool(led), message=message)
    return _write(s)


def reset():
    return _write({"ref": None, "mode": "idle", "placed": [], "flags": [], "message": ""})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    cmd, rest = a[0], a[1:]
    if cmd == "show":
        out = show(rest[0], " ".join(rest[1:]))
    elif cmd == "placed":
        out = placed(rest[0])
    elif cmd == "inspect":
        out = inspect(" ".join(rest))
    elif cmd == "flag":
        out = flag(rest[0], rest[1], rest[2] if len(rest) > 2 else "cold", " ".join(rest[3:]))
    elif cmd == "clear":
        out = clear()
    elif cmd == "done":
        out = done(led="--led" in rest, message=" ".join(r for r in rest if r != "--led"))
    elif cmd == "reset":
        out = reset()
    else:
        sys.exit(f"unknown command {cmd!r}; run without arguments for help")
    print(json.dumps(out))
