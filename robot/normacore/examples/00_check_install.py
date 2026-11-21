"""Check the Python side and whether Station is listening. Needs no robot.

    python3 robot/normacore/examples/00_check_install.py
"""
import socket
from pathlib import Path

import _common  # noqa: F401  (imports elrobot, which imports the vendored station_py and protobufs)

here = Path(__file__).resolve().parent.parent
print("station_py and protobuf stubs: OK")
print((here / "vendor" / "VERSION.txt").read_text().splitlines()[0])
binary = here / "bin" / "station"
print(f"Station binary: {'found at ' + str(binary) if binary.exists() else 'missing, run install_station.sh'}")
for port, what in ((8888, "Python API"), (8889, "web UI")):
    s = socket.socket()
    s.settimeout(1.0)
    ok = s.connect_ex(("localhost", port)) == 0
    s.close()
    print(f"localhost:{port} ({what}): {'listening' if ok else 'not running'}")
