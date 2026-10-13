#!/usr/bin/env python3
"""Build the showcase's media from b2crunner run folders.

For every run under each --src (a folder of run directories, each with
ply/scene.ply and log.txt) this writes:

  splats/<id>.sog          the splat, SOG-compressed at full SH3, turned upright
                           for PlayCanvas viewers (the runs are y-down)
  settings/<id>.json       viewer settings: background and a camera framing it
  thumbs/<id>-front.webp   transparent renders from the photograph's side and
  thumbs/<id>-back.webp    from behind
  inputs/<id>.webp         the reference sheet the run started from
  data/gallery.json        what the page lists, in id order, minus the
                           excluded runs in tools/curation.json

and, once, viewer/ (the SuperSplat viewer splat-transform ships).

Needs Node on PATH and the pinned splat-transform (`npm ci` in tools/), and
a WebGPU adapter for the SH compression (any Vulkan GPU).
"""
import argparse
import array
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

SITE = Path(__file__).resolve().parent.parent
TOOLS = SITE / "tools"

# The vertical field of view the subject's height fills on a landscape stage
# (viewer/autoframe.js widens it when the stage is too narrow for the subject),
# the margin around the subject, and the stage background (sRGB 0-1).
#
# Frames: the run's camera that saw the photograph sits at the origin, looking
# down -z at the subject, y down. The SOG is written turned 180 degrees about
# z, so in the viewer (and splat-transform's renderer) the subject stands y-up,
# its centre c is at (-cx, -cy, cz) and the photograph's side faces +z.
# (splat-transform and the viewer each turn about z on their own as well; the
# two cancel.)
FOV = 35.0
MARGIN = 1.08
MARGIN_WIDTH = 1.2
BACKGROUND = [0.078, 0.078, 0.086]
THUMB_SIZE = (480, 720)
INPUT_MAX = 1400


def splat_transform():
    exe = os.environ.get("SPLAT_TRANSFORM") or TOOLS / "node_modules/.bin/splat-transform"
    if not Path(exe).exists():
        sys.exit(f"splat-transform not found at {exe}: run `npm ci` in tools/ or set SPLAT_TRANSFORM")
    return str(exe)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"failed: {' '.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")


def parse_src(spec):
    """PATH or PATH+OFFSET: a source folder and what to add to its run numbers."""
    m = re.fullmatch(r"(.+?)(?:\+(\d+))?", spec)
    return Path(m.group(1)), int(m.group(2) or 0)


def find_runs(sources):
    """{id: run dir} across (folder, offset) sources; a rerun of the same id
    replaces the older run."""
    runs = {}
    for src, offset in sources:
        for d in sorted(src.iterdir()):
            m = re.search(r"_(\d{5})(?:-|$)", d.name)
            ply = d / "ply" / "scene.ply"
            if not m or not ply.exists():
                continue
            rid = f"{int(m.group(1)) + offset:05d}"
            if rid not in runs or ply.stat().st_mtime > (runs[rid] / "ply" / "scene.ply").stat().st_mtime:
                runs[rid] = d
    return runs


def ply_bounds(path):
    """1st and 99th percentile of x, y, z, and the vertex count."""
    data = Path(path).read_bytes()
    end = data.index(b"end_header\n") + len(b"end_header\n")
    header = data[:end].decode("ascii", "replace")
    if "binary_little_endian" not in header or "property double" in header:
        sys.exit(f"{path}: expected a little-endian all-float PLY")
    n = int(re.search(r"element vertex (\d+)", header).group(1))
    stride = header.count("property float")
    values = array.array("f")
    values.frombytes(data[end:end + n * stride * 4])
    lo, hi = [], []
    for axis in range(3):
        col = sorted(values[axis::stride])
        lo.append(col[n // 100])
        hi.append(col[(99 * n) // 100])
    return lo, hi, n


def reference_input(run_dir, uploads_root):
    """The reference image (and its prompt) the run's log says it started from."""
    log = (run_dir / "log.txt").read_text(errors="replace")
    m = re.search(r"starting from reference image (\S+)", log)
    if not m:
        return None, None
    p = m.group(1)
    if p.startswith("/data/"):
        p = str(Path(uploads_root) / p[len("/data/"):])
    image = Path(p)
    prompt_file = image.with_suffix(".txt")
    prompt = prompt_file.read_text().strip() if prompt_file.exists() else None
    return (image if image.exists() else None), prompt


def viewer_settings(centre, distance, fit):
    target = [round(-centre[0], 4), round(-centre[1], 4), round(centre[2], 4)]
    position = [target[0], target[1], round(target[2] + distance, 4)]
    return {
        "version": 2,
        "tonemapping": "linear",
        "highPrecisionRendering": False,
        "background": {"color": BACKGROUND},
        "postEffectSettings": {
            "sharpness": {"enabled": False, "amount": 0},
            "bloom": {"enabled": False, "intensity": 0.1, "blurLevel": 2},
            "grading": {"enabled": False, "brightness": 1, "contrast": 1, "saturation": 1, "tint": [1, 1, 1]},
            "vignette": {"enabled": False, "intensity": 0.5, "inner": 0.3, "outer": 0.75, "curvature": 1},
            "fringing": {"enabled": False, "intensity": 0.5},
        },
        "animTracks": [],
        "cameras": [{"initial": {"position": position, "target": target, "fov": FOV}}],
        "annotations": [],
        "startMode": "default",
        # read by viewer/autoframe.js, not by the viewer
        "b2cFit": fit,
    }


def write_settings(rid, centre, size):
    """Put the camera where FOV frames the subject's height, and hand
    autoframe.js the half extents it keeps in view at any stage aspect. The
    turntable swings the depth across the screen too, so the half width is the
    larger of the two horizontal extents."""
    fit = {"halfHeight": round(size["y"] / 2 * MARGIN, 4),
           # hands and fingertips lie past the 99th percentile, sideways
           "halfWidth": round(max(size["x"], size["z"]) / 2 * MARGIN_WIDTH, 4),
           # how far the turntable can bring a part of the subject towards the camera
           "radius": round(max(size["x"], size["z"]) / 2, 4)}
    distance = fit["halfHeight"] / math.tan(math.radians(FOV / 2))
    (SITE / "settings" / f"{rid}.json").write_text(json.dumps(viewer_settings(centre, distance, fit), indent=2) + "\n")


def save_webp(src, dst, size=None, quality=85):
    im = Image.open(src)
    if size:
        im.thumbnail(size, Image.LANCZOS)
    im.save(dst, "WEBP", quality=quality, method=6)
    return im.size


def build_run(st, rid, run_dir, uploads_root, force):
    ply = run_dir / "ply" / "scene.ply"
    sog = SITE / "splats" / f"{rid}.sog"
    meta_file = SITE / "data" / "runs" / f"{rid}.json"
    if not force and sog.exists() and meta_file.exists() and sog.stat().st_mtime > ply.stat().st_mtime:
        meta = json.loads(meta_file.read_text())
        write_settings(rid, meta["centre_m"], meta["size_m"])
        return meta

    lo, hi, count = ply_bounds(ply)
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    centre = [round(c, 4) for c in centre]
    size = dict(zip("xyz", (round(b - a, 3) for a, b in zip(lo, hi))))
    # Only the turn upright, no translation: the viewer settings aim the
    # camera at the subject instead.
    run([st, "-w", str(ply), "-r", "0,0,180", str(sog)])

    write_settings(rid, centre, size)

    thumb_distance = (size["y"] / 2 * 1.06) / math.tan(math.radians(15))
    cx, cy, cz = -centre[0], -centre[1], centre[2]
    with tempfile.TemporaryDirectory() as tmp:
        for side, z in (("front", cz + thumb_distance), ("back", cz - thumb_distance)):
            raw = Path(tmp) / f"{side}.webp"
            run([st, "-w", str(sog), str(raw),
                 "--camera-pos", f"{cx},{cy},{z:.3f}", "--camera-target", f"{cx},{cy},{cz}", "--camera-up", "0,1,0",
                 "--camera-fov", "30", "--resolution", f"{THUMB_SIZE[0]}x{THUMB_SIZE[1]}",
                 "--background", "0,0,0,0"])
            save_webp(raw, SITE / "thumbs" / f"{rid}-{side}.webp", quality=82)

    image, prompt = reference_input(run_dir, uploads_root)
    input_size = None
    if image:
        input_size = save_webp(image, SITE / "inputs" / f"{rid}.webp", (INPUT_MAX, INPUT_MAX))
    else:
        print(f"  {rid}: no reference image found", file=sys.stderr)

    meta = {
        "id": rid,
        "run": run_dir.name,
        "prompt": prompt,
        "gaussians": count,
        "centre_m": centre,
        "size_m": size,
        "sog_bytes": sog.stat().st_size,
        "input": {"w": input_size[0], "h": input_size[1]} if input_size else None,
    }
    meta_file.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def build_viewer(st, sample_sog):
    """Unpack splat-transform's own HTML viewer into viewer/ (without its sample splat)."""
    with tempfile.TemporaryDirectory() as tmp:
        run([st, "-w", str(sample_sog), str(Path(tmp) / "index.html"), "--unbundled"])
        out = SITE / "viewer"
        out.mkdir(exist_ok=True)
        for name in ("index.js", "index.css"):
            shutil.copy(Path(tmp) / name, out / name)
        # autoframe.js (ours, kept in viewer/) runs after the viewer's bootstrap
        html = (Path(tmp) / "index.html").read_text()
        tag = '        <script type="module" src="./autoframe.js"></script>\n'
        if "</body>" not in html:
            sys.exit("viewer index.html has no </body> to put autoframe.js before")
        (out / "index.html").write_text(html.replace("    </body>", tag + "    </body>", 1))
    version = subprocess.run([st, "--version"], capture_output=True, text=True).stdout.strip()
    (SITE / "viewer" / "VERSION").write_text(version + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Each batch numbers its runs from 00001; the offset moves a later batch
    # past the ids the earlier ones already use.
    ap.add_argument("--src", action="append", type=parse_src,
                    help="folder of b2crunner run directories, optionally +OFFSET to add to its run "
                         "numbers (repeatable; default: /mnt/data/plys and /mnt/data/run2+74)")
    ap.add_argument("--uploads-root", default="/mnt/data/b2crunner",
                    help="host folder mounted as /data in the runner (for the logged reference image path)")
    ap.add_argument("--only", nargs="*", help="build just these ids")
    ap.add_argument("--force", action="store_true", help="rebuild even when the outputs are newer than the PLY")
    ap.add_argument("--viewer", action="store_true", help="re-unpack the viewer")
    args = ap.parse_args()

    st = splat_transform()
    for sub in ("splats", "settings", "thumbs", "inputs", "data/runs"):
        (SITE / sub).mkdir(parents=True, exist_ok=True)

    curation = json.loads((TOOLS / "curation.json").read_text())
    exclude = set(curation.get("exclude", []))
    runs = find_runs(args.src or [parse_src("/mnt/data/plys"), parse_src("/mnt/data/run2+74")])
    todo = sorted(r for r in runs if r not in exclude and (not args.only or r in args.only))
    for i, rid in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {rid}  {runs[rid].name}")
        build_run(st, rid, runs[rid], args.uploads_root, args.force)

    if args.viewer or not (SITE / "viewer" / "index.js").exists():
        sample = next((SITE / "splats").glob("*.sog"), None)
        if sample:
            build_viewer(st, sample)

    # Excluded runs lose their media, so nothing unlisted gets published.
    for rid in exclude:
        for f in (f"splats/{rid}.sog", f"settings/{rid}.json", f"thumbs/{rid}-front.webp",
                  f"thumbs/{rid}-back.webp", f"inputs/{rid}.webp", f"data/runs/{rid}.json"):
            (SITE / f).unlink(missing_ok=True)

    # The gallery: every built run that is not excluded, whether built now or before.
    entries = []
    for meta_file in sorted((SITE / "data" / "runs").glob("*.json")):
        meta = json.loads(meta_file.read_text())
        if meta["id"] not in exclude and (SITE / "splats" / f"{meta['id']}.sog").exists():
            entries.append(meta)
    # Ids in curation "order" lead, in that order; the rest follow by id.
    order = {rid: i for i, rid in enumerate(curation.get("order", []))}
    entries.sort(key=lambda e: (order.get(e["id"], len(order)), e["id"]))
    featured = curation.get("featured")
    if featured not in {e["id"] for e in entries}:
        featured = entries[0]["id"] if entries else None
    (SITE / "data" / "gallery.json").write_text(json.dumps({"featured": featured, "runs": entries}, indent=1) + "\n")
    total = sum(e["sog_bytes"] for e in entries)
    print(f"gallery: {len(entries)} runs, {total / 1e6:.0f} MB of splats")


if __name__ == "__main__":
    main()
