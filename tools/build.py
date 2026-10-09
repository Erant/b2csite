#!/usr/bin/env python3
"""Build the showcase's media from b2crunner run folders.

For every run under --src (a folder of run directories, each with ply/scene.ply
and log.txt) this writes:

  splats/<id>.sog          the splat, SOG-compressed at full SH3, turned y-up
                           and centred on the origin (the runs are y-down)
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

# The viewer's field of view (on the wider axis), the widest stage it frames
# for, and the stage background (sRGB 0-1). The viewer shows the photograph's
# side from +z (splat-transform's renderer from -z).
FOV = 35.0
STAGE_ASPECT = 1.4
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


def find_runs(src):
    """{id: run dir}; a rerun of the same id replaces the older run."""
    runs = {}
    for d in sorted(Path(src).iterdir()):
        m = re.search(r"_(\d{5})(?:-|$)", d.name)
        ply = d / "ply" / "scene.ply"
        if not m or not ply.exists():
            continue
        rid = m.group(1)
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


def viewer_settings(distance):
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
        "cameras": [{"initial": {"position": [0, 0, round(distance, 3)], "target": [0, 0, 0], "fov": FOV}}],
        "annotations": [],
        "startMode": "default",
    }


def write_settings(rid, height):
    """Frame the subject's height with a margin. The viewer applies its field of
    view to the wider axis, so on a landscape stage (up to STAGE_ASPECT) the
    vertical view is narrower than FOV."""
    half = math.tan(math.radians(FOV / 2)) / STAGE_ASPECT
    distance = (height / 2 * 1.08) / half
    (SITE / "settings" / f"{rid}.json").write_text(json.dumps(viewer_settings(distance), indent=2) + "\n")


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
        write_settings(rid, meta["height_m"])
        return meta

    lo, hi, count = ply_bounds(ply)
    centre = [(a + b) / 2 for a, b in zip(lo, hi)]
    height = hi[1] - lo[1]
    # 180 degrees about x turns the y-down run y-up (and puts the photograph's
    # camera on -z); the translation then centres the subject on the origin.
    # splat-transform applies -t in PlayCanvas's frame, which is the file's
    # turned 180 degrees about z, so x and y go in negated.
    shift = f"{centre[0]:.4f},{-centre[1]:.4f},{centre[2]:.4f}"
    run([st, "-w", str(ply), "-r", "180,0,0", "-t", shift, str(sog)])

    write_settings(rid, height)

    thumb_distance = (height / 2 * 1.06) / math.tan(math.radians(15))
    with tempfile.TemporaryDirectory() as tmp:
        for side, z in (("front", -thumb_distance), ("back", thumb_distance)):
            raw = Path(tmp) / f"{side}.webp"
            run([st, "-w", str(sog), str(raw),
                 "--camera-pos", f"0,0,{z:.3f}", "--camera-target", "0,0,0", "--camera-up", "0,1,0",
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
        "height_m": round(height, 3),
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
        for name in ("index.html", "index.js", "index.css"):
            shutil.copy(Path(tmp) / name, out / name)
    version = subprocess.run([st, "--version"], capture_output=True, text=True).stdout.strip()
    (SITE / "viewer" / "VERSION").write_text(version + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="/mnt/data/plys", help="folder of b2crunner run directories")
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
    runs = find_runs(args.src)
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
