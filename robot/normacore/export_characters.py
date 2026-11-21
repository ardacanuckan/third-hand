"""Build a standalone character bundle to hand to another project.

    python3 robot/normacore/export_characters.py [OUT_DIR]       # default ~/Downloads

Writes OUT_DIR/third_hand_characters/ and OUT_DIR/third_hand_characters.zip. The bundle has no
dependency on this repo, NormaCore Station or any third-party package: characters.json (the data),
python/thc (planner + player, stdlib only), js/thc.js (planner + servo model), trajectories.json
(physics-simulated joint angles), docs and tests. Source of truth stays character.py.
"""
import json, pathlib, shutil, sys, zipfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import character as C  # noqa: E402

OUT = pathlib.Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else pathlib.Path.home() / "Downloads"
B = OUT / "third_hand_characters"
SRC = HERE / "bundle_src"                  # hand-written parts of the bundle (python, js, docs)
ANIM = HERE / "servo_sim" / "viewer" / "anim.json"


def main():
    anim = json.loads(ANIM.read_text())
    if B.exists():
        shutil.rmtree(B)
    shutil.copytree(SRC, B)
    chars = {}
    for n, p in C.PERSONALITIES.items():
        chars[n] = dict(archetype=p.archetype, laban=p.laban, acc_mult=p.acc, speed_mult=p.speed, size=p.size,
                        tempo=p.tempo, blend=p.blend, anticipation=p.anticipation, overshoot=p.overshoot,
                        tremor=p.tremor, posture=p.posture, breath=p.breath, breath_s=p.breath_s,
                        glance_s=p.glance_s, smooth=p.smooth)
    data = {
        "format": "third-hand-characters/1",
        "about": "Expressive characters for an 8-servo arm (ElRobot, Feetech STS3215). See README.md.",
        "joints": {
            "names": list(C.JOINTS),
            "meaning": {"j1": "base yaw: turn / look left-right", "j2": "shoulder pitch: lean forward (+) / back (-)",
                        "j3": "elbow pitch: neck height, + droops", "j4": "pitch: neck bend, + head down",
                        "j5": "roll: body twist", "j6": "wrist pitch: nod, + head down",
                        "j7": "wrist roll: head tilt", "j8": "gripper jaws: mouth, + opens"},
            "urdf_limits_rad": {j: [round(anim["engine"]["lo"][i], 4), round(anim["engine"]["hi"][i], 4)]
                                for i, j in enumerate(C.JOINTS)},
        },
        "units": {
            "position": "normalized 0..1 inside each joint's calibrated range (NormaCore Station's position_norm)",
            "offset_unit": C.U, "offset_unit_means": "gesture offsets are in units of this fraction of the range",
            "acc": "STS3215 register 0x29, 100 ticks/s^2 per unit (4096 ticks per turn)",
            "speed": "STS3215 register 0x2E, ticks/s",
            "beats": "keyframe length; seconds = beats * character tempo",
        },
        "neutral_default": {j: 0.5 for j in C.JOINTS},
        "limits": {"max_dev_from_neutral": C.MAX_DEV, "acc_cap": C.ACC_CAP, "speed_cap": C.SPEED_CAP,
                   "base_profile": {j: {"acc": a, "speed": s} for j, (a, s) in C.BASE.items()},
                   "sign": C.SIGN},
        "characters": chars,
        "gestures": {g: [[b, o] for b, o in k] for g, k in C.GESTURES.items() if g not in C.SCENES},
        "scenes": {g: [[b, o] for b, o in k] for g, k in C.SCENES.items()},
        "props": C.PROPS,
        # for the JS engine (same shape as the Character Studio's data) and the baked trajectories
        "engine": {**anim["engine"], "gestures": {g: [[b, o] for b, o in k] for g, k in C.GESTURES.items()}},
        "stand_rad": anim["stand"], "fps": anim["fps"],
    }
    (B / "characters.json").write_text(json.dumps(data, indent=1))
    traj = {"about": "Joint angles (rad, URDF convention, j1..j8) at fps, simulated in MuJoCo with the STS3215 "
                     "servo model from an upright standing pose (stand_rad). keys = seconds at which each keyframe "
                     "starts; peak_shoulder = highest shoulder load in % of 2.94 N*m stall.",
            "fps": anim["fps"], "joints": list(C.JOINTS), "stand_rad": anim["stand"],
            "clips": {k: {"q": v["q"], "keys": v.get("keys", []), "peak_shoulder": v["peak"]} for k, v in anim["clips"].items()}}
    (B / "trajectories.json").write_text(json.dumps(traj, separators=(",", ":")))
    zpath = OUT / "third_hand_characters.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(B.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(OUT))
    print(f"bundle: {B}\nzip:    {zpath} ({zpath.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
