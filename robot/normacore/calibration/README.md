# calibration: A4 sheets and scripts for the ElRobot's cameras

Print `calibration_sheets.pdf` at **100 % / Actual size** on matte paper and check a 100 mm bar.

| Page | Sheet | Used for |
|---|---|---|
| 1 | Instructions | |
| 2 | ChArUco 9×6, 28 mm squares | side camera lens (30–60 cm away) |
| 3 | ChArUco 15×10, 12 mm squares | wrist camera lens (5–20 cm away) |
| 4 | Bench mat: 6 markers, 9 touch targets T1–T9, mm grid | side camera position in the robot frame |
| 5 | Colour and scale card | white balance, exposure, mm per pixel |
| 6 | 16 marker stickers (cups A1–B3, handover, iron stand, PCB corners, base) | self-labelling images for a vision model |

Every marker id is unique (OpenCV `DICT_5X5_1000`); `boards.json` says what each id is and where it is in mm.

```bash
pip install opencv-contrib-python numpy reportlab          # for make_sheets.py / calibrate.py (not for capture.py)

python3 capture.py --tag side                               # Enter = shot (frames + joints), q = quit; 20-30 shots
python calibrate.py intrinsics --tag side --cam cam1        # the wrist camera is the one that shows the jaws
python3 capture.py --tag wrist && python calibrate.py intrinsics --tag wrist --cam cam0
python3 capture.py --tag mat                                # one shot of the bench mat, D mm in front of the base
python calibrate.py extrinsics --tag mat --cam cam1 --intr side --mat-distance D
python calibrate.py labels --tag dataset_1                  # every marker in every image -> labels.json
```

Results land in `cameras/*.json` (camera matrix, distortion, RMS, camera position in the robot frame:
metres, x to the robot's right, y forward, z up). Calibrate at the resolution the robot uses
(`resize_target` in station.yaml, 448 now); a new resolution, zoom or focus needs a new calibration.

`test_calibrate.py` renders synthetic photos of pages 2 and 4 through a known distorted camera and checks
the pipeline: focal length within 1.7 %, centre within 2 px, side camera position within 10 mm.

Not done here: hand-eye calibration of the wrist camera. It needs the arm's joint readings mapped to
URDF angles (the calibrated 0..1 range per joint), which nobody has measured on the real arm yet. The
touch targets on the bench mat are the way to measure it: jog the jaws onto T1–T9 and save the poses.
