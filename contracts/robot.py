"""Robot interface shared by robot/ (ARM) and agent/ (BRAIN).

DRAFT until the Sat 12:00 checkpoint. After that, change it only with ARM and BRAIN
agreeing, and record the change in docs/06-contracts.md.

Both the real ElRobot driver and the fake robot implement `Robot`. Joint values are
Station's normalized position_norm (0..1) unless a name says otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

Camera = Literal["side", "wrist"]
Slot = Literal["A1", "A2", "A3", "B1", "B2", "B3"]
JOINTS = ("j1", "j2", "j3", "j4", "j5", "j6", "j7", "j8")  # j7 rotates the gripper, j8 opens/closes the jaws


@dataclass(frozen=True)
class FetchResult:
    ok: bool          # the motion finished without a servo fault
    gripped: bool     # a load was sensed when the jaws closed
    seconds: float    # wall time of the whole motion
    note: str = ""    # short human-readable detail for logs and for Claude


@runtime_checkable
class Robot(Protocol):
    def home(self) -> None:
        """Move to the taught home pose."""

    def park(self) -> None:
        """Move over the parts tray, clear of the soldering iron."""

    def go_pose(self, name: str) -> None:
        """Move to any taught pose by name; raises KeyError for an unknown pose."""

    def gripper(self, norm: float) -> None:
        """Set the jaws (j8). Open is about 0.78; the value is clamped to the calibrated range."""

    def fetch_cup(self, slot: Slot) -> FetchResult:
        """Whole motion: open, approach the cup, grip, lift, carry to the handover zone, release, return home."""

    def go_inspect(self, area: str = "power") -> None:
        """Put the wrist camera over a board area for joint inspection."""

    def camera_jpeg(self, cam: Camera, max_px: int = 640) -> bytes:
        """Latest frame from a camera as JPEG, longest side at most max_px."""

    def joints(self) -> dict[str, float]:
        """Current j1..j8 from the motor bus (never from camera frames)."""

    def stop(self) -> None:
        """Abort the current motion and hold position."""
