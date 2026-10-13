# b2csite

The showcase page for [b2crunner](https://github.com/Erant/b2crunner): a gallery of
splats it produced, viewed in the browser. It is a static site for GitHub Pages:
everything is served from the repo root on `main`. `.nojekyll` makes Pages serve the
files as they are.

```
index.html, assets/      the page
viewer/                  the SuperSplat viewer, unpacked by splat-transform (VERSION),
                         plus autoframe.js, which keeps the subject framed at any size
splats/<id>.sog          SOG-compressed splats (full SH3, upright for PlayCanvas)
settings/<id>.json       per-splat viewer settings (camera on the subject, its extents)
thumbs/<id>-{front,back}.webp   gallery renders
inputs/<id>.webp         the reference sheet each run started from
data/gallery.json        what the page lists; data/runs/<id>.json per run
tools/                   the build (not served content, just harmless if it is)
```

## Building the media

```bash
cd tools && npm ci && cd ..           # the pinned @playcanvas/splat-transform
python3 tools/build.py                 # every run under /mnt/data/plys and /mnt/data/run2
python3 tools/build.py --only 00018    # one run
python3 tools/build.py --viewer        # re-unpack the viewer after bumping splat-transform
```

Needs Node 18+ and Pillow. The SH compression runs on WebGPU, which needs a Vulkan GPU
on the host. A run is skipped when its outputs are newer than its `scene.ply`
(`--force` rebuilds). Run folders are read from `--src`, and the reference image path
in each run's `log.txt` is mapped from the runner's `/data` to `--uploads-root`.

Every batch numbers its runs from 00001, so a later batch is given an offset that moves
it past the ids already in use: `--src /mnt/data/run2+74` publishes its run 00001 as
00075. The default sources are `/mnt/data/plys` and `/mnt/data/run2+74`; pass `--src`
(repeatable) to change them.

## Curating

`tools/curation.json` picks the subject the page opens on (`featured`), the runs that
lead the gallery (`order`; the rest follow by id) and the runs to leave out (`exclude`). The next build deletes an excluded run's media, so nothing
unlisted is published.

## Previewing locally

```bash
python3 -m http.server 8000           # then http://localhost:8000/
```

The page needs to be served over HTTP: `fetch` does not work from `file://`.

## Publishing

Push to a GitHub repo, then turn on Settings → Pages → Deploy from a branch → `main`, `/ (root)`.
For a user site at `<user>.github.io`, name the repo that. Size limits: about 1 GB per
site, 100 MB per file, and a soft limit of 100 GB of traffic a month. A splat is
5–8 MB.
