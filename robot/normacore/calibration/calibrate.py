"""Calibrate the ElRobot's cameras from the printed sheets (needs opencv-contrib-python, numpy).

    python calibrate.py intrinsics --tag side  --cam cam1       # lens: focal length, centre, distortion
    python calibrate.py intrinsics --tag wrist --cam cam0
    python calibrate.py extrinsics --tag mat --cam cam1 --intr side --mat-distance 120
                                                                # where the side camera is, in the robot's frame
    python calibrate.py labels --tag dataset_1                  # marker detections -> labels.json for training

Results go to cameras/<name>.json. Robot frame (as in sim/core.js): metres, x to the robot's right,
y forward, z up from the table. --mat-distance is D: bottom edge of the bench mat to the base centre, mm.
"""
import argparse, json, pathlib, sys
import cv2
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
META = json.loads((HERE / "boards.json").read_text())
DICT = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, META["dictionary"]))
OUT = HERE / "cameras"


def detector():
    p = cv2.aruco.DetectorParameters()
    p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return cv2.aruco.ArucoDetector(DICT, p)


def board(name):
    b = META["charuco"][name]
    nx, ny = b["squares"]
    return cv2.aruco.CharucoBoard((nx, ny), b["square_mm"] / 1000, b["marker_mm"] / 1000, DICT,
                                  np.array(b["ids"], dtype=np.int32))


def images(tag, cam):
    files = sorted((HERE / "captures" / tag).glob(f"*_{cam}.jpg" if cam else "*.jpg"))
    if not files:
        sys.exit(f"No images in captures/{tag} for {cam or 'any camera'}. Take some with capture.py first.")
    return files


def intrinsics(tag, cam, board_name, min_corners=8, save_as=None, quiet=False):
    """ChArUco -> camera matrix and distortion. Returns the result dict."""
    brd = board(board_name)
    cd = cv2.aruco.CharucoDetector(brd)
    obj, img, used, size = [], [], [], None
    cover = np.zeros((4, 4), int)
    for f in images(tag, cam):
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        size = g.shape[::-1]
        cc, ci, _, _ = cd.detectBoard(g)
        if ci is None or len(ci) < min_corners:
            continue
        o, i = brd.matchImagePoints(cc, ci)
        obj.append(o); img.append(i); used.append(f.name)
        for x, y in i.reshape(-1, 2):
            cover[min(3, int(y / size[1] * 4)), min(3, int(x / size[0] * 4))] += 1
    if len(obj) < 6:
        sys.exit(f"Only {len(obj)} usable images (need 6+, ideally 20+). Fill the frame with the board from more angles.")
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(obj, img, size, None, None)
    per = []
    for o, i, r, t in zip(obj, img, rvecs, tvecs):
        p, _ = cv2.projectPoints(o, r, t, K, dist)
        per.append(float(np.sqrt(np.mean(np.sum((p.reshape(-1, 2) - i.reshape(-1, 2)) ** 2, axis=1)))))
    res = {"camera": cam, "board": board_name, "image_size": list(size), "images_used": len(obj),
           "rms_px": round(float(rms), 4), "K": K.tolist(), "dist": dist.ravel().tolist(),
           "fov_deg": [round(float(np.degrees(2 * np.arctan(size[0] / (2 * K[0, 0])))), 1),
                       round(float(np.degrees(2 * np.arctan(size[1] / (2 * K[1, 1])))), 1)],
           "worst_images": sorted(zip(per, used), reverse=True)[:5], "coverage_4x4": cover.tolist()}
    OUT.mkdir(exist_ok=True)
    (OUT / f"{save_as or tag}.json").write_text(json.dumps(res, indent=1))
    if not quiet:
        print(f"{cam}: {len(obj)} images, RMS {rms:.3f} px, fx {K[0, 0]:.1f} fy {K[1, 1]:.1f} "
              f"cx {K[0, 2]:.1f} cy {K[1, 2]:.1f}, FOV {res['fov_deg'][0]}x{res['fov_deg'][1]} deg")
        empty = int((cover == 0).sum())
        if rms > 1.0: print("  RMS above 1 px: drop blurred shots (see worst_images) and recalibrate.")
        if empty: print(f"  {empty} of 16 image regions have no corners: add shots with the board near the edges.")
        print(f"  saved cameras/{save_as or tag}.json")
    return res


def mat_points(distance_mm):
    """Bench-mat marker corners in the robot frame (m), keyed by id."""
    pts = {}
    for mid, corners in META["bench_mat"]["markers"].items():
        pts[int(mid)] = np.array([[x / 1000, (distance_mm + y) / 1000, 0.0] for x, y in corners], np.float32)
    return pts


def extrinsics(tag, cam, intr_name, distance_mm, save_as=None, quiet=False):
    """Bench mat -> camera pose in the robot frame."""
    intr = json.loads((OUT / f"{intr_name}.json").read_text())
    K, dist = np.array(intr["K"]), np.array(intr["dist"])
    ref = mat_points(distance_mm)
    det = detector()
    obj, img = [], []
    for f in images(tag, cam):
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        corners, ids, _ = det.detectMarkers(g)
        if ids is None:
            continue
        for c, i in zip(corners, ids.ravel()):
            if int(i) in ref:
                obj.append(ref[int(i)]); img.append(c.reshape(4, 2))
    if len(obj) < 2:
        sys.exit("Fewer than 2 bench-mat markers seen. Check the mat is in view, flat and evenly lit.")
    obj = np.concatenate(obj); img = np.concatenate(img).astype(np.float32)
    ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
    rvec, tvec = cv2.solvePnPRefineLM(obj, img, K, dist, rvec, tvec)
    p, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
    err = float(np.sqrt(np.mean(np.sum((p.reshape(-1, 2) - img) ** 2, axis=1))))
    R, _ = cv2.Rodrigues(rvec)
    cam_pos = (-R.T @ tvec).ravel()                                  # camera centre in the robot frame
    look = R.T @ np.array([0, 0, 1.0])                               # optical axis in the robot frame
    res = {"camera": cam, "intrinsics": intr_name, "mat_distance_mm": distance_mm, "markers_used": len(obj) // 4,
           "reprojection_px": round(err, 3), "R_robot_to_cam": R.tolist(), "t_robot_to_cam": tvec.ravel().tolist(),
           "camera_position_m": [round(float(v), 4) for v in cam_pos],
           "looking_along": [round(float(v), 3) for v in look]}
    OUT.mkdir(exist_ok=True)
    (OUT / f"{save_as or cam + '_extrinsics'}.json").write_text(json.dumps(res, indent=1))
    if not quiet:
        x, y, z = cam_pos
        print(f"{cam}: {len(obj) // 4} markers, reprojection {err:.2f} px. Camera at x {x * 1000:.0f} mm, "
              f"y {y * 1000:.0f} mm, height {z * 1000:.0f} mm (robot frame), looking along {res['looking_along']}")
        print(f"  saved cameras/{save_as or cam + '_extrinsics'}.json")
    return res


def labels(tag):
    """Every marker in every image -> labels.json: what it is (from boards.json) and where (pixels)."""
    names = {}
    for k, v in META["stickers"]["labels"].items(): names[int(k)] = v
    for k in META["bench_mat"]["markers"]: names[int(k)] = f"bench mat {k}"
    for k in META["colour_card"]["markers"]: names[int(k)] = "colour card"
    for bname, b in META["charuco"].items():
        for i in b["ids"]: names[i] = bname
    det = detector()
    out = []
    for f in images(tag, None):
        g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
        corners, ids, _ = det.detectMarkers(g)
        side = json.loads((f.parent / (f.name.split("_")[0] + ".json")).read_text()) if (f.parent / (f.name.split("_")[0] + ".json")).exists() else {}
        items = []
        for c, i in zip(corners or [], ids.ravel() if ids is not None else []):
            pts = c.reshape(4, 2)
            x0, y0 = pts.min(0); x1, y1 = pts.max(0)
            items.append({"id": int(i), "label": names.get(int(i), "unknown"), "corners_px": pts.round(1).tolist(),
                          "box_px": [round(float(x0), 1), round(float(y0), 1), round(float(x1 - x0), 1), round(float(y1 - y0), 1)]})
        out.append({"image": f.name, "size": list(g.shape[::-1]), "joints": side.get("joints", {}), "markers": items})
    path = HERE / "captures" / tag / "labels.json"
    path.write_text(json.dumps(out, indent=1))
    seen = sum(len(o["markers"]) for o in out)
    print(f"{len(out)} images, {seen} markers labelled -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("intrinsics"); a.add_argument("--tag", required=True); a.add_argument("--cam", required=True)
    a.add_argument("--board", help="charuco_side or charuco_wrist (default from the tag)")
    e = sub.add_parser("extrinsics"); e.add_argument("--tag", required=True); e.add_argument("--cam", required=True)
    e.add_argument("--intr", required=True, help="name of the intrinsics file, e.g. side")
    e.add_argument("--mat-distance", type=float, required=True, help="mat bottom edge to base centre, mm")
    l = sub.add_parser("labels"); l.add_argument("--tag", required=True)
    args = ap.parse_args()
    if args.cmd == "intrinsics":
        intrinsics(args.tag, args.cam, args.board or ("charuco_wrist" if "wrist" in args.tag else "charuco_side"))
    elif args.cmd == "extrinsics":
        extrinsics(args.tag, args.cam, args.intr, args.mat_distance)
    else:
        labels(args.tag)
