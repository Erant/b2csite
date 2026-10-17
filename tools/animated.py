#!/usr/bin/env python3
"""Add one animated subject to the showcase.

An animated subject is a b2cgltf web subject (<name>.sog, SPEC 10.1) and one of
its web clips (<name>.clip.zip, SPEC 10.2), as b2canimate saves them with its
s0g button. The page plays them in viewer-anim/ (the SuperSplat viewer with the
b2c rig playback, see viewer-anim/VERSION); the .sog is also a plain splat, so
the usual viewers show it at rest. This writes

  splats/<id>.sog, clips/<id>.clip.zip   the two files, as they are
  settings/<id>.json                     the camera, from the bounds given below
  thumbs/<id>-{front,back}.webp          rest-pose renders
  inputs/<id>.webp                       the reference sheet, if given
  data/runs/<id>.json                    what the page lists, and data/gallery.json
                                         (build.py keeps this entry when it rewrites it)

Unlike a run's PLY, the web subject is stored upright in the b2crunner frame
(y up, the figure facing +z): no turn about z is needed, and the viewer shows
it unturned.

  python3 tools/animated.py --id 00157 --sog lara.sog --clip lara.clip.zip \\
      --input ref.png --prompt prompt.txt

A subject that depicts someone else's character is fan art: --character and
--owner name them, and the page then offers no download and does not put it
under CC BY 4.0.

  python3 tools/animated.py --id 00158 --sog vi.sog --clip vi.clip.zip \\
      --character "Vi from Arcane" --owner "Riot Games"
"""
import argparse
import json
import math
import shutil
import tempfile
from pathlib import Path

import build
from build import SITE, FOV, MARGIN, MARGIN_WIDTH, THUMB_SIZE, INPUT_MAX

# A running stride bobs and swings the arms wider than the rest pose.
BOB = 0.1
SWING = 1.25


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True)
    ap.add_argument("--sog", required=True, type=Path)
    ap.add_argument("--clip", required=True, type=Path)
    ap.add_argument("--input", type=Path, help="the reference sheet image")
    ap.add_argument("--prompt", type=Path, help="text file with the prompt")
    ap.add_argument("--character", help="the existing character it depicts (fan art: no download, not CC BY)")
    ap.add_argument("--owner", help="who owns that character")
    args = ap.parse_args()
    if bool(args.character) != bool(args.owner):
        ap.error("--character and --owner go together")
    rid = args.id

    st = build.splat_transform()
    for sub in ("splats", "clips", "settings", "thumbs", "inputs", "data/runs"):
        (SITE / sub).mkdir(parents=True, exist_ok=True)
    sog = SITE / "splats" / f"{rid}.sog"
    shutil.copy(args.sog, sog)
    shutil.copy(args.clip, SITE / "clips" / f"{rid}.clip.zip")

    with tempfile.TemporaryDirectory() as tmp:
        ply = Path(tmp) / "rest.ply"
        build.run([st, "-w", str(sog), str(ply)])
        lo, hi, count = build.ply_bounds(ply)
        centre = [round((a + b) / 2, 4) for a, b in zip(lo, hi)]
        size = dict(zip("xyz", (round(b - a, 3) for a, b in zip(lo, hi))))

        # the camera, as build.write_settings does, but in the unturned frame and
        # with room for the stride
        fit = {"halfHeight": round((size["y"] / 2 * MARGIN) + BOB, 4),
               "halfWidth": round(max(size["x"], size["z"]) / 2 * MARGIN_WIDTH * SWING, 4),
               "radius": round(max(size["x"], size["z"]) / 2 * SWING, 4)}
        distance = fit["halfHeight"] / math.tan(math.radians(FOV / 2))
        settings = build.viewer_settings(centre, distance, fit)
        # build.viewer_settings turns the centre for a turned splat; this one is not
        target = centre
        settings["cameras"] = [{"initial": {"position": [target[0], target[1], round(target[2] + distance, 4)],
                                            "target": target, "fov": FOV}}]
        (SITE / "settings" / f"{rid}.json").write_text(json.dumps(settings, indent=2) + "\n")

        # thumbnails: splat-transform's renderer, like build_run's, wants the turned splat
        turned = Path(tmp) / "turned.ply"
        build.run([st, "-w", str(ply), "-r", "0,0,180", str(turned)])
        cx, cy, cz = -centre[0], -centre[1], centre[2]
        thumb_distance = (size["y"] / 2 * 1.06) / math.tan(math.radians(15))
        for side, z in (("front", cz + thumb_distance), ("back", cz - thumb_distance)):
            raw = Path(tmp) / f"{side}.webp"
            build.run([st, "-w", str(turned), str(raw),
                       "--camera-pos", f"{cx},{cy},{z:.3f}", "--camera-target", f"{cx},{cy},{cz}",
                       "--camera-up", "0,1,0", "--camera-fov", "30",
                       "--resolution", f"{THUMB_SIZE[0]}x{THUMB_SIZE[1]}", "--background", "0,0,0,0"])
            build.save_webp(raw, SITE / "thumbs" / f"{rid}-{side}.webp", quality=82)

    input_size = None
    if args.input:
        input_size = build.save_webp(args.input, SITE / "inputs" / f"{rid}.webp", (INPUT_MAX, INPUT_MAX))
    meta = {
        "id": rid,
        "run": None,
        "prompt": args.prompt.read_text().strip() if args.prompt else None,
        "gaussians": count,
        "centre_m": centre,
        "size_m": size,
        "sog_bytes": sog.stat().st_size,
        "input": {"w": input_size[0], "h": input_size[1]} if input_size else None,
        "clip": {"file": f"clips/{rid}.clip.zip", "bytes": (SITE / "clips" / f"{rid}.clip.zip").stat().st_size},
    }
    if args.character:
        meta["fan_art"] = {"character": args.character, "owner": args.owner}
    (SITE / "data" / "runs" / f"{rid}.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"{rid}: {count} gaussians, centre {centre}, size {size}")
    curation = json.loads((build.TOOLS / "curation.json").read_text())
    build.write_gallery(curation, set(curation.get("exclude", [])))


if __name__ == "__main__":
    main()
