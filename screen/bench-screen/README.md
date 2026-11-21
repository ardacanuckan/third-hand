# Bench Screen

A monitor next to the bench shows the SOL-MIO v1.3 board, drawn from its Altium data, and lights up the
footprint where the next part goes. The robot's jaws are too wide to point at 0603 and 1206 parts, so the arm
only fetches parts and checks joints with its camera; the screen does the pointing.

## Run

```bash
cd bench-screen
python3 -m http.server 8077
```

Open http://localhost:8077 on the bench monitor and press F for fullscreen.

- **R** turns the board 180° if your view of the real board is upside down.
- **← →** step through the parts by hand when nothing is driving the page.

## Drive it from Claude

The page follows `guide_state.json`. Write it with `guide_control.py`, from a shell or from your MCP server:

```python
from guide_control import show, placed, inspect, flag, clear, done

@mcp.tool()
def show_footprint(ref: str) -> str:
    """Light up where a part goes on the bench screen (D2, R1, D1, C4, C13)."""
    show(ref)
    return f"{ref} is lit up on the bench screen"

@mcp.tool()
def mark_joint(ref: str, pad: int, kind: str = "cold", text: str = "") -> str:
    """Circle a pad the wrist camera flagged (kind: cold, bad or ok)."""
    flag(ref, pad, kind, text)
    return f"{ref} pad {pad} marked {kind}"
```

Shell examples:

```bash
python3 guide_control.py show D2 "Band goes to the lower pad."
python3 guide_control.py placed D2
python3 guide_control.py flag C4 2 cold "reheat 3 s"
python3 guide_control.py done --led
```

## Before the demo

- Fill in the R1 value and the D1 colour in `TARGETS` at the top of `bench-screen.js`; they were not in the board data.
- Check the capacitor and LED polarity marks against your silkscreen. The screen only says "match it to the
  silkscreen" because the footprint data does not say which pad is minus.
- Board data: `solmio-board.js`, taken from the Muscle_MB2 Altium project (outline, holes, 93 part placements).
