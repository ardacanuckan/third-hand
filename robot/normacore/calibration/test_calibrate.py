"""End-to-end check of calibrate.py on synthetic photos of the printed sheets, from a camera whose
lens and position we know. Needs pdftoppm (poppler) to render the bench mat page.

    python test_calibrate.py
"""
import json, shutil, subprocess, tempfile, pathlib
import cv2
import numpy as np
import calibrate as C

HERE = pathlib.Path(__file__).resolve().parent
rng = np.random.default_rng(7)
W, H = 597, 448                                              # Station resize_target 448, 4:3
K = np.array([[420.0, 0, 301.0], [0, 418.0, 221.0], [0, 0, 1]])
DIST = np.array([-0.12, 0.035, 0.0005, -0.0004, 0.0])


def look_at(cam, target, up=(0, 0, 1)):
    z = np.array(target, float) - cam; z /= np.linalg.norm(z)
    x = np.cross(z, up); x /= np.linalg.norm(x); y = np.cross(z, x)
    R = np.stack([x, y, z])                                  # world -> camera
    return R, -R @ np.array(cam, float)


def render(texture, A, R, t, blur=0.8, noise=2.0):
    """texture pixel (u, v) -> world plane point A @ [u, v, 1] (z = 0); photo with lens distortion."""
    Hm = K @ np.column_stack([R[:, 0], R[:, 1], t]) @ A      # texture px -> undistorted image px
    undist = cv2.warpPerspective(texture, Hm, (W, H), flags=cv2.INTER_AREA, borderValue=170)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    pts = cv2.undistortPoints(np.stack([xs.ravel(), ys.ravel()], 1).reshape(-1, 1, 2), K, DIST, P=K).reshape(H, W, 2)
    img = cv2.remap(undist, pts[..., 0], pts[..., 1], cv2.INTER_LINEAR, borderValue=170)
    img = cv2.GaussianBlur(img, (0, 0), blur)
    return np.clip(img + rng.normal(0, noise, img.shape), 0, 255).astype(np.uint8)


def test_intrinsics(folder):
    b = C.META["charuco"]["charuco_side"]; nx, ny = b["squares"]; sq = b["square_mm"]
    ppm = 8
    tex = C.board("charuco_side").generateImage((int(nx * sq * ppm), int(ny * sq * ppm)), marginSize=0, borderBits=1)
    tex = cv2.copyMakeBorder(tex, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    # texture px -> board plane (m), board centred at the origin
    A = np.array([[1 / ppm / 1000, 0, -(tex.shape[1] / 2) / ppm / 1000],
                  [0, -1 / ppm / 1000, (tex.shape[0] / 2) / ppm / 1000], [0, 0, 1]])
    n = 0
    for k in range(22):
        dist = rng.uniform(0.32, 0.55)
        cam = np.array([rng.uniform(-0.12, 0.12), rng.uniform(-0.1, 0.1), dist])
        target = np.array([rng.uniform(-0.06, 0.06), rng.uniform(-0.04, 0.04), 0])
        tilt = rng.uniform(-0.6, 0.6, 2)
        cam = cam + np.array([np.sin(tilt[0]) * dist, np.sin(tilt[1]) * dist, 0])
        R, t = look_at(cam, target, up=(0, 1, 0))
        img = render(tex, A, R, t)
        cv2.imwrite(str(folder / f"{k:04d}_cam1.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90]); n += 1
    res = C.intrinsics(folder.name, "cam1", "charuco_side", save_as="_test_side", quiet=True)
    Ke = np.array(res["K"])
    errs = {"fx": Ke[0, 0] / K[0, 0] - 1, "fy": Ke[1, 1] / K[1, 1] - 1, "cx_px": Ke[0, 2] - K[0, 2], "cy_px": Ke[1, 2] - K[1, 2]}
    print(f"intrinsics: {res['images_used']}/{n} images, RMS {res['rms_px']:.2f} px; fx {errs['fx'] * 100:+.2f} %, "
          f"fy {errs['fy'] * 100:+.2f} %, cx {errs['cx_px']:+.1f} px, cy {errs['cy_px']:+.1f} px, k1 {res['dist'][0]:+.3f} (true {DIST[0]})")
    assert abs(errs["fx"]) < 0.02 and abs(errs["fy"]) < 0.02 and abs(errs["cx_px"]) < 6 and abs(errs["cy_px"]) < 6
    return res


def test_extrinsics(folder, distance_mm=120.0):
    pdf = HERE / "calibration_sheets.pdf"
    tmp = pathlib.Path(tempfile.mkdtemp())
    subprocess.run(["pdftoppm", "-r", "200", "-f", "4", "-l", "4", "-gray", "-png", str(pdf), str(tmp / "mat")], check=True)
    tex = cv2.imread(str(next(tmp.glob("mat*.png"))), cv2.IMREAD_GRAYSCALE)
    shutil.rmtree(tmp)
    ppmm = tex.shape[1] / 210.0
    # page px (u right, v down) -> sheet mm (x = u/ppmm - 105, y = 297 - v/ppmm) -> robot frame m
    A = np.array([[1 / ppmm / 1000, 0, -0.105], [0, -1 / ppmm / 1000, (distance_mm + 297) / 1000], [0, 0, 1]])
    cam_true = np.array([0.36, -0.02, 0.33])                 # sim/core.js LAYOUT.sideCam
    R, t = look_at(cam_true, [-0.01, 0.15, 0.02] if False else [0.0, (distance_mm + 150) / 1000, 0.0])
    cv2.imwrite(str(folder / "0000_cam1.jpg"), render(tex, A, R, t, blur=0.6), [cv2.IMWRITE_JPEG_QUALITY, 90])
    res = C.extrinsics(folder.name, "cam1", "_test_side", distance_mm, save_as="_test_extr", quiet=True)
    err_mm = np.linalg.norm(np.array(res["camera_position_m"]) - cam_true) * 1000
    print(f"extrinsics: {res['markers_used']} markers, reprojection {res['reprojection_px']:.2f} px; camera found at "
          f"{np.array(res['camera_position_m']) * 1000} mm, true {cam_true * 1000} mm -> off by {err_mm:.1f} mm")
    assert err_mm < 15
    return res


if __name__ == "__main__":
    caps = HERE / "captures"
    folders = [caps / "_test_side", caps / "_test_mat"]
    for f in folders: f.mkdir(parents=True, exist_ok=True)
    try:
        test_intrinsics(folders[0])
        test_extrinsics(folders[1])
        C.labels("_test_mat")
        print("all calibration checks passed")
    finally:
        for f in folders: shutil.rmtree(f, ignore_errors=True)
        for n in ("_test_side", "_test_extr"):
            (C.OUT / f"{n}.json").unlink(missing_ok=True)
