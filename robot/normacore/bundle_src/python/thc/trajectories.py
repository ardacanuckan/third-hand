"""Pre-computed joint trajectories (radians, 30 fps) from the physics simulation, for robots that only
take position targets: stream frame after frame at the given fps.

    from thc import trajectories
    clip = trajectories.load()["trickster/kick_ball"]      # {"q": [[j1..j8 rad], ...], "keys": [...], "peak_shoulder": %}
    for frame in trajectories.frames("trickster/kick_ball"):  # yields (t_seconds, {joint: rad})
        ...
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent.parent / "trajectories.json"


@lru_cache(maxsize=1)
def _data(path: str = str(PATH)) -> dict:
    return json.loads(Path(path).read_text())


def load(path: str | Path = PATH) -> dict:
    """All clips, keyed 'character/move'."""
    return _data(str(path))["clips"]


def names(path: str | Path = PATH) -> list[str]:
    return sorted(load(path))


def frames(clip: str, path: str | Path = PATH):
    d = _data(str(path))
    fps, joints = d["fps"], d["joints"]
    for k, q in enumerate(d["clips"][clip]["q"]):
        yield k / fps, dict(zip(joints, q))
