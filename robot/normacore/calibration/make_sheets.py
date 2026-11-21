"""Print-ready A4 calibration sheets for the ElRobot's cameras, and boards.json describing every marker.

    python make_sheets.py            # -> calibration_sheets.pdf + boards.json (needs opencv-contrib-python, reportlab)

Pages
  1  How to use these sheets
  2  ChArUco board, 28 mm squares   -> side camera intrinsics (camera ~30-60 cm away)
  3  ChArUco board, 12 mm squares   -> wrist camera intrinsics (camera ~5-20 cm away)
  4  Bench mat                      -> where the side camera sits in the robot's frame; touch targets
  5  Colour and scale card          -> white balance, exposure, mm per pixel; corner markers find it
  6  Marker stickers                -> label cups, handover zone, PCB corners for auto-labelled images

All markers come from OpenCV's DICT_5X5_1000; every id is used once across the set, so one detector
call finds everything and boards.json says what each id is and where it sits (mm).
Print at 100 % / "Actual size" on matte paper; check the 100 mm bars with a ruler.
"""
import io, json, pathlib
import cv2
import numpy as np
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = pathlib.Path(__file__).resolve().parent
DICT_NAME = "DICT_5X5_1000"
DICT = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))
INK = (0.08, 0.09, 0.10)
GREY = (0.45, 0.47, 0.50)

BOARDS = {
    "charuco_side":  dict(squares=[9, 6], square_mm=28.0, marker_mm=21.0, first_id=0),
    "charuco_wrist": dict(squares=[15, 10], square_mm=12.0, marker_mm=9.0, first_id=100),
}
MAT = dict(marker_mm=30.0, ids=[200, 201, 202, 203, 204, 205])     # bench mat markers
CARD = dict(marker_mm=16.0, ids=[220, 221, 222, 223])               # colour card corner markers
STICKERS = [("A1", 300), ("A2", 301), ("A3", 302), ("B1", 303), ("B2", 304), ("B3", 305),
            ("handover", 306), ("iron stand", 307), ("PCB corner 1", 308), ("PCB corner 2", 309),
            ("PCB corner 3", 310), ("PCB corner 4", 311), ("robot base", 312), ("spare", 313),
            ("spare", 314), ("spare", 315)]
STICKER_MM = 20.0


def charuco(name):
    b = BOARDS[name]
    nx, ny = b["squares"]
    ids = np.arange(b["first_id"], b["first_id"] + (nx * ny) // 2, dtype=np.int32)
    return cv2.aruco.CharucoBoard((nx, ny), b["square_mm"] / 1000, b["marker_mm"] / 1000, DICT, ids)


def image_reader(img):
    ok, png = cv2.imencode(".png", img)
    return ImageReader(io.BytesIO(png.tobytes()))


def draw_marker(c, mid, x, y, size):
    """Vector ArUco marker, lower-left corner at (x, y) in points, side `size` points."""
    bits = DICT.generateImageMarker(mid, 7)                   # 7x7 cells: 1 border + 5 data + 1 border
    cell = size / 7
    c.setFillColorRGB(1, 1, 1); c.rect(x - cell, y - cell, size + 2 * cell, size + 2 * cell, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    for r in range(7):
        for k in range(7):
            if bits[r, k] < 128:
                c.rect(x + k * cell, y + (6 - r) * cell, cell + 0.01, cell + 0.01, fill=1, stroke=0)


def scale_bar(c, x, y, length_mm=100, label=True):
    c.setStrokeColorRGB(*INK); c.setLineWidth(0.6)
    c.line(x, y, x + length_mm * mm, y)
    for k in range(0, length_mm + 1, 10):
        h = 3 * mm if k % 50 == 0 else 1.6 * mm
        c.line(x + k * mm, y, x + k * mm, y + h)
    if label:
        c.setFont("Helvetica", 7); c.setFillColorRGB(*GREY)
        c.drawString(x, y - 3.2 * mm, f"{length_mm} mm: measure this to check the print scale")


def footer(c, w, text):
    c.setFont("Helvetica", 7); c.setFillColorRGB(*GREY)
    c.drawString(12 * mm, 7 * mm, text)
    c.drawRightString(w - 12 * mm, 7 * mm, "Third Hand · ElRobot camera calibration · print at 100 %, matte paper")


def page_board(c, name, title, use):
    w, h = landscape(A4); c.setPageSize((w, h))
    b = BOARDS[name]; nx, ny = b["squares"]
    bw, bh = nx * b["square_mm"], ny * b["square_mm"]
    px_per_mm = 20
    img = charuco(name).generateImage((int(bw * px_per_mm), int(bh * px_per_mm)), marginSize=0, borderBits=1)
    x0 = (w - bw * mm) / 2; y0 = (h - bh * mm) / 2 + 4 * mm
    c.drawImage(image_reader(img), x0, y0, bw * mm, bh * mm)
    c.setFont("Helvetica-Bold", 10); c.setFillColorRGB(*INK)
    c.drawString(x0, y0 + bh * mm + 4 * mm, title)
    c.setFont("Helvetica", 8); c.setFillColorRGB(*GREY)
    c.drawString(x0, y0 + bh * mm + 0.8 * mm,
                 f"{name}: {nx} x {ny} squares of {b['square_mm']:g} mm, markers {b['marker_mm']:g} mm, "
                 f"{DICT_NAME} ids {b['first_id']}-{b['first_id'] + nx * ny // 2 - 1}. {use}")
    scale_bar(c, x0, y0 - 9 * mm)
    footer(c, w, "Keep it flat: tape it to a clipboard or a sheet of foam board. Do not fold.")


def page_instructions(c):
    w, h = A4; c.setPageSize(A4)
    y = h - 22 * mm
    def line(txt, size=10, bold=False, gap=5.2, col=INK):
        nonlocal y
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size); c.setFillColorRGB(*col)
        c.drawString(18 * mm, y, txt); y -= gap * mm
    line("ElRobot camera calibration sheets", 18, True, 9)
    line("Print every page at 100 % (\"Actual size\", not \"Fit to page\") on matte paper. Check a 100 mm bar with a ruler.", 9, col=GREY)
    line("Glossy paper reflects the lamps and hides markers. Keep boards flat: tape them to foam board or a clipboard.", 9, col=GREY, gap=9)
    steps = [
        ("Page 2 · Side camera lens (intrinsics)", [
            "Hold the board in front of the side camera, 30-60 cm away. Take 20-30 shots: tilted up to",
            "45 degrees, near every corner and edge of the image, near and far. Never blurred.",
            "python capture.py --tag side   then   python calibrate.py intrinsics --tag side"]),
        ("Page 3 · Wrist camera lens (intrinsics)", [
            "Lay the board on the table. Torque off, move the wrist camera over it by hand, 5-20 cm away,",
            "from many angles. 20-30 shots with the corners and edges of the image covered.",
            "python capture.py --tag wrist   then   python calibrate.py intrinsics --tag wrist"]),
        ("Page 4 · Bench mat (side camera in the robot's frame)", [
            "Tape the mat flat in front of the arm: its arrow points away from the robot, its centre line on",
            "the robot's forward axis, the bottom edge D mm in front of the base centre (measure D).",
            "One shot from the side camera:  python calibrate.py extrinsics --tag mat --mat-distance D",
            "The crosshairs T1-T9 are touch targets: jog the jaws onto each and save the pose to check",
            "the arm's own coordinates against the camera's."]),
        ("Page 5 · Colour and scale card", [
            "Put it in view of each camera at the start of a session: white balance, exposure, mm per pixel.",
            "Its four corner markers let a script find it and read the patches automatically."]),
        ("Page 6 · Marker stickers", [
            "Cut them out and stick them on the cups (A1-B3), the handover zone, the PCB fixture corners and",
            "the robot base. Every capture then labels itself: the markers say what is where, in pixels and",
            "in mm, which is the training data a vision model needs. Keep stickers flat; 20 mm square."]),
    ]
    for head, body in steps:
        line(head, 11, True, 5.6)
        for b in body:
            line(b, 9, gap=4.6, col=INK if not b.startswith("python") else (0.1, 0.35, 0.45))
        y -= 3 * mm
    line("Same resolution always", 11, True, 5.6)
    for b in ["Calibrate at the size the robot will use: station.yaml usb-video resize_target (448 now).",
              "Changing it, the zoom or the focus means calibrating again."]:
        line(b, 9, gap=4.6)
    footer(c, w, "Every marker id is unique across all pages (OpenCV DICT_5X5_1000); boards.json lists them.")


def page_mat(c):
    w, h = A4; c.setPageSize(A4)
    m = MAT["marker_mm"]
    # sheet frame: origin = centre of the bottom edge, x right, y away from the robot (mm)
    def P(x, y): return (105 + x) * mm, y * mm
    pos = {200: (-75, 30), 201: (75, 30), 202: (-75, 262), 203: (75, 262), 204: (-75, 146), 205: (75, 146)}
    # faint 10 mm grid
    c.setStrokeColorRGB(0.86, 0.87, 0.89); c.setLineWidth(0.25)
    for gx in range(-100, 101, 10): c.line(*P(gx, 8), *P(gx, 289))
    for gy in range(10, 290, 10): c.line(*P(-100, gy), *P(100, gy))
    # centre line and arrow
    c.setStrokeColorRGB(*INK); c.setLineWidth(0.5); c.setDash(3, 2); c.line(*P(0, 0), *P(0, 297)); c.setDash()
    c.setFillColorRGB(*INK)
    p = c.beginPath(); p.moveTo(*P(0, 287)); p.lineTo(*P(-4, 279)); p.lineTo(*P(4, 279)); p.close(); c.drawPath(p, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 8); c.drawCentredString(*P(0, 291), "AWAY FROM THE ROBOT")
    c.setFont("Helvetica", 7.5); c.setFillColorRGB(*GREY)
    c.drawCentredString(*P(0, 2.5), "Bottom edge: D mm in front of the robot base centre. Centre line on the robot's forward axis.")
    markers = {}
    for mid, (cx, cy) in pos.items():
        x, y = P(cx - m / 2, cy - m / 2)
        draw_marker(c, mid, x, y, m * mm)
        c.setFont("Helvetica", 6.5); c.setFillColorRGB(*GREY)
        c.drawCentredString(*P(cx, cy - m / 2 - 6.5), f"id {mid} · centre ({cx:+g}, {cy:g}) mm")
        # corners in the sheet frame, OpenCV order: top-left, top-right, bottom-right, bottom-left (as seen printed)
        markers[mid] = [[cx - m / 2, cy + m / 2], [cx + m / 2, cy + m / 2], [cx + m / 2, cy - m / 2], [cx - m / 2, cy - m / 2]]
    # touch targets
    targets = {}
    k = 1
    for ty in (80, 146, 212):
        for tx in (-50, 0, 50):
            x, y = P(tx, ty)
            c.setStrokeColorRGB(*INK); c.setLineWidth(0.5)
            c.circle(x, y, 4 * mm, stroke=1, fill=0); c.line(x - 6 * mm, y, x + 6 * mm, y); c.line(x, y - 6 * mm, x, y + 6 * mm)
            # labels on the side away from the nearest marker column
            side = (lambda X, Y, s: c.drawRightString(X - 4.6 * mm, Y, s)) if tx > 0 else (lambda X, Y, s: c.drawString(X + 4.6 * mm, Y, s))
            c.setFont("Helvetica-Bold", 7); c.setFillColorRGB(*INK); side(x, y + 3 * mm, f"T{k}")
            c.setFont("Helvetica", 6); c.setFillColorRGB(*GREY); side(x, y - 5 * mm, f"({tx:+d}, {ty})")
            targets[f"T{k}"] = [tx, ty]; k += 1
    scale_bar(c, *P(-50, 112), label=False)
    c.setFont("Helvetica", 6.5); c.setFillColorRGB(*GREY); c.drawString(*P(-50, 107.5), "100 mm")
    c.setFont("Helvetica-Bold", 9); c.setFillColorRGB(*INK); c.drawString(*P(-100, 283), "Bench mat")
    c.setFont("Helvetica", 6.5); c.setFillColorRGB(*GREY)
    c.drawString(*P(-100, 279), "sheet frame: origin bottom-edge centre, x right, y away (mm)")
    return {"marker_mm": m, "markers": {str(k): v for k, v in markers.items()}, "targets": targets,
            "frame": "origin at the centre of the bottom edge; x to the right, y away from the robot; mm; flat on the table (z = 0)"}


def page_card(c):
    w, h = landscape(A4); c.setPageSize((w, h))
    cw, ch = 220, 140                          # card outline (mm), centred
    ox, oy = (297 - cw) / 2, (210 - ch) / 2 + 6
    def P(x, y): return (ox + x) * mm, (oy + y) * mm
    c.setStrokeColorRGB(*GREY); c.setLineWidth(0.4); c.rect(*P(0, 0), cw * mm, ch * mm, stroke=1, fill=0)
    mk = CARD["marker_mm"]; corners = {}
    for mid, (x, y) in zip(CARD["ids"], [(4, ch - 4 - mk), (cw - 4 - mk, ch - 4 - mk), (cw - 4 - mk, 4), (4, 4)]):
        draw_marker(c, mid, *P(x, y), mk * mm)
        corners[str(mid)] = [[x, y + mk], [x + mk, y + mk], [x + mk, y], [x, y]]
    # grey ramp (sRGB values printed under each patch)
    greys = [245, 200, 160, 122, 85, 52, 20]
    pw, ph = 22, 22
    gx0 = (cw - len(greys) * pw) / 2
    patches = []
    for i, gv in enumerate(greys):
        x, y = gx0 + i * pw, 82
        c.setFillColorRGB(gv / 255, gv / 255, gv / 255); c.rect(*P(x, y), pw * mm, ph * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6); c.setFillColorRGB(*GREY); c.drawCentredString(*P(x + pw / 2, y - 4), f"{gv}")
        patches.append({"name": f"grey{gv}", "rgb": [gv] * 3, "box_mm": [x, y, pw, ph]})
    colours = [("red", (200, 40, 40)), ("green", (40, 150, 60)), ("blue", (40, 70, 190)), ("cyan", (40, 170, 200)),
               ("magenta", (190, 50, 150)), ("yellow", (235, 200, 40)), ("skin", (215, 165, 135)), ("solder", (170, 172, 175))]
    cx0 = (cw - len(colours) * pw) / 2
    for i, (nm, rgb) in enumerate(colours):
        x, y = cx0 + i * pw, 44
        c.setFillColorRGB(*(v / 255 for v in rgb)); c.rect(*P(x, y), pw * mm, ph * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 6); c.setFillColorRGB(*GREY); c.drawCentredString(*P(x + pw / 2, y - 4), nm)
        patches.append({"name": nm, "rgb": list(rgb), "box_mm": [x, y, pw, ph]})
    # resolution wedge: line pairs 0.5 .. 3 mm
    x = 30
    for lw in (3, 2, 1.5, 1, 0.75, 0.5):
        c.setFillColorRGB(0, 0, 0)
        for k in range(4): c.rect(*P(x + k * 2 * lw, 14), lw * mm, 14 * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 5.5); c.setFillColorRGB(*GREY); c.drawCentredString(*P(x + 4 * lw, 10.5), f"{lw:g} mm")
        x += 8 * lw + 7
    scale_bar(c, *P(cw - 4 - 100 - 24, 33), label=False)
    c.setFont("Helvetica", 6); c.setFillColorRGB(*GREY); c.drawString(*P(cw - 128 - 14, 33.3), "100 mm")
    c.setFont("Helvetica-Bold", 10); c.setFillColorRGB(*INK); c.drawString(*P(26, ch - 10), "Colour and scale card")
    c.setFont("Helvetica", 7); c.setFillColorRGB(*GREY)
    c.drawString(*P(26, ch - 15), "Printer colours vary: use the greys for white balance and exposure; the colours as a consistent reference.")
    footer(c, w, "Card frame: origin at the card's bottom-left corner, mm. boards.json lists every patch.")
    return {"size_mm": [cw, ch], "marker_mm": mk, "markers": corners, "patches": patches}


def page_stickers(c):
    w, h = A4; c.setPageSize(A4)
    cols, cellw, cellh = 4, 44, 40
    x0, y0 = (210 - cols * cellw) / 2, 297 - 30
    c.setFont("Helvetica-Bold", 11); c.setFillColorRGB(*INK); c.drawString(x0 * mm, (297 - 18) * mm, "Marker stickers (20 mm)")
    c.setFont("Helvetica", 7.5); c.setFillColorRGB(*GREY)
    c.drawString(x0 * mm, (297 - 22.5) * mm, "Cut along the grey lines. Stick flat and upright where the cameras can see them.")
    out = {}
    for k, (label, mid) in enumerate(STICKERS):
        r, col = divmod(k, cols)
        cx, cy = x0 + col * cellw, y0 - (r + 1) * cellh
        c.setStrokeColorRGB(0.75, 0.77, 0.8); c.setLineWidth(0.3); c.setDash(2, 2)
        c.rect(cx * mm, cy * mm, cellw * mm, cellh * mm, stroke=1, fill=0); c.setDash()
        draw_marker(c, mid, (cx + (cellw - STICKER_MM) / 2) * mm, (cy + 13) * mm, STICKER_MM * mm)
        c.setFont("Helvetica-Bold", 8); c.setFillColorRGB(*INK); c.drawCentredString((cx + cellw / 2) * mm, (cy + 6.5) * mm, label)
        c.setFont("Helvetica", 6); c.setFillColorRGB(*GREY); c.drawCentredString((cx + cellw / 2) * mm, (cy + 2.5) * mm, f"id {mid}")
        out[str(mid)] = label
    scale_bar(c, x0 * mm, 20 * mm)
    footer(c, w, "Ids 313-315 are spares: give them a meaning in boards.json before use.")
    return {"marker_mm": STICKER_MM, "labels": out}


def main():
    pdf = HERE / "calibration_sheets.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    c.setTitle("ElRobot camera calibration sheets"); c.setAuthor("Third Hand")
    page_instructions(c); c.showPage()
    page_board(c, "charuco_side", "Side camera: lens calibration board", "Hold 30-60 cm from the side camera.")
    c.showPage()
    page_board(c, "charuco_wrist", "Wrist camera: lens calibration board", "Lay flat; the wrist camera looks down from 5-20 cm.")
    c.showPage()
    mat = page_mat(c); c.showPage()
    card = page_card(c); c.showPage()
    stickers = page_stickers(c); c.showPage()
    c.save()
    meta = {"dictionary": DICT_NAME,
            "charuco": {k: {**v, "ids": list(range(v["first_id"], v["first_id"] + v["squares"][0] * v["squares"][1] // 2))}
                        for k, v in BOARDS.items()},
            "bench_mat": mat, "colour_card": card, "stickers": stickers}
    (HERE / "boards.json").write_text(json.dumps(meta, indent=1))
    print("wrote", pdf, "and boards.json")


if __name__ == "__main__":
    main()
