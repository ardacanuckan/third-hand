"""Write the ElRobot URDF packed in sim/elrobot-model.js to elrobot.urdf (meshes are not needed)."""
import json, pathlib
here = pathlib.Path(__file__).resolve().parent
s = (here.parents[2] / "sim" / "elrobot-model.js").read_text()
(here / "elrobot.urdf").write_text(json.loads(s[s.index("{"):s.rindex("}") + 1])["urdf"])
print("wrote", here / "elrobot.urdf")
