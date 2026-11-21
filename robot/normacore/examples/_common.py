"""Shared setup for the examples: import elrobot from the folder above and turn on logging."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

from elrobot import JAWS_OPEN, JOINTS, ElRobot, RobotError  # noqa: E402,F401
