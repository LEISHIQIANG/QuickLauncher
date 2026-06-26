"""Repack screenshot_ocr.qlzip with keepalive frame fix."""

import hashlib
import os
import zipfile

plugin_dir = "plugins/screenshot_ocr"
qlzip_path = ".plugins/screenshot_ocr.qlzip"

tmp = qlzip_path + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for root, dirs, files in os.walk(plugin_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, plugin_dir)
            arcname = "screenshot_ocr/" + rel.replace("\\", "/")
            zout.write(fpath, arcname)

os.replace(tmp, qlzip_path)

h = hashlib.sha256()
with open(qlzip_path, "rb") as f:
    while True:
        chunk = f.read(8192)
        if not chunk:
            break
        h.update(chunk)
print(f"New SHA256: {h.hexdigest()}")
