"""Make the arm act a character. Dry run by default (prints the timed plan, no robot needed).

    python3 robot/normacore/examples/10_character.py                        # list characters and gestures
    python3 robot/normacore/examples/10_character.py trickster yes          # dry run: the plan
    python3 robot/normacore/examples/10_character.py trickster yes --live   # on the arm
    python3 robot/normacore/examples/10_character.py sleepy idle --live     # 10 s of idle breathing/glances

First teach a "neutral" pose (arm upright, clear of everything) with 07_poses.py, or the arm uses
wherever it stands as neutral. Keep a hand on the power switch, and keep hands and the iron away.
"""
import asyncio
import sys

import _common  # noqa: F401  (puts robot/normacore on the path)
from character import GESTURES, PERSONALITIES, idle, idle_plan, perform, plan
from elrobot import ElRobot


def show(name: str, gesture: str) -> None:
    p = PERSONALITIES[name]
    steps = idle_plan(p, 10) if gesture == "idle" else plan(p, gesture)
    print(f"{p.name}: {p.archetype}  [{p.laban}]")
    for s in steps[:40]:
        goals = " ".join(f"{j}={v:.3f}" for j, v in sorted(s.goals.items()))
        acc = " ".join(f"{j}:{s.acc[j]}" for j in sorted(s.goals))
        print(f"  t={s.t:5.2f}s {'wait ' if s.wait_arrival else '     '}{goals}   acc {acc}")
    if len(steps) > 40:
        print(f"  ... {len(steps) - 40} more steps")


async def live(name: str, gesture: str) -> None:
    async with await ElRobot.connect() as arm:
        if input(f"Perform {name} / {gesture} on bus {arm.follower}? Hands clear? [y/N] ").lower() != "y":
            return
        await arm.torque(True)
        if gesture == "idle":
            await idle(arm, name, 10)
        else:
            await perform(arm, name, gesture)
        await arm.hold()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("characters:", ", ".join(PERSONALITIES))
        print("gestures:  ", ", ".join(GESTURES), "+ idle")
        for p in PERSONALITIES.values():
            print(f"  {p.name:10s} {p.archetype}  [{p.laban}]")
        sys.exit(0)
    name, gesture = args[0], args[1]
    if "--live" in sys.argv:
        asyncio.run(live(name, gesture))
    else:
        show(name, gesture)
