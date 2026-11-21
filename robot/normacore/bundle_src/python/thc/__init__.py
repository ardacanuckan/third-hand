"""Third Hand characters: expressive personalities for an 8-servo arm. Standard library only.

    from thc import Library, play
    lib = Library.load()
    play(lib.plan("smooth", "air_kiss"), send=my_send, read=my_read)
"""
from .planner import Character, Library, Step
from .player import aplay, move_time, play
from . import trajectories, units

__all__ = ["Library", "Character", "Step", "play", "aplay", "move_time", "units", "trajectories"]
__version__ = "1.0.0"
