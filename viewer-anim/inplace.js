// b2csite: run on the spot, and keep the CPU sort in order.
//
// A running clip carries the subject through the scene (body_world travels
// metres along z), which a turntable camera cannot follow, and the clip jumps
// back to its start when it loops. This takes the travel out of body_world's
// horizontal track in the parsed clip before it is posed, so the subject runs
// where autoframe.js and the camera expect it. Only the trend goes: a moving
// average about a stride long, so each stride's surge stays. body_world is
// the pelvis here, and pinning it exactly read as a camera bolted to the hips.
// The window shrinks to nothing at the clip's ends, so the loop does not jump.
// Height and heading are left alone, so the bounce of a stride stays.
//
// It also keeps the sorter's bounds around the posed splats. On WebGL the
// engine sorts on the CPU, and spreads its sort keys over the distances to the
// corners of the resource's bounds, which are the rest pose's. A splat posed
// beyond the far corner gets key 0, so all such splats are drawn in arbitrary
// order among themselves: from behind, the head leans out of the rest box and
// its far side was drawn over its crown. The bounds grow to every pose the
// sorter is given (the viewer's src/b2c feeds it resource.centers, bumping
// centersVersion).
const b2c = await new Promise((resolve) => {
  const poll = () => (window.b2c?.clip && window.app ? resolve(window.b2c) : setTimeout(poll, 50));
  poll();
});
const { clip, subject } = b2c;
const J = subject.skeleton.joints.length;
const joint = 0; // body_world: the skeleton's travelling joint, a child of the skeleton root
const HALF_WINDOW = 5; // frames each side: +-0.17 s at 30 fps, about one stride in all
const t = clip.t, n = clip.nframes;
const track = (axis) => Array.from({ length: n }, (_, f) => t[(f * J + joint) * 3 + axis]);
for (const axis of [0, 2]) {
  const v = track(axis);
  for (let f = 0; f < n; f++) {
    const h = Math.min(HALF_WINDOW, f, n - 1 - f);
    let mean = 0;
    for (let k = f - h; k <= f + h; k++) mean += v[k];
    mean /= 2 * h + 1;
    t[(f * J + joint) * 3 + axis] = v[0] + v[f] - mean;
  }
}

const resource = window.app.root.findComponents("gsplat")[0].resource;
const aabb = resource.aabb; // copied into each world state the engine builds
const lo = aabb.getMin().clone(), hi = aabb.getMax().clone();
const MARGIN = 0.02;
let seen = -1;
window.app.on("update", () => {
  if (resource.centersVersion === seen) return;
  seen = resource.centersVersion;
  const c = resource.centers;
  let x0 = lo.x, y0 = lo.y, z0 = lo.z, x1 = hi.x, y1 = hi.y, z1 = hi.z;
  for (let i = 0; i < c.length; i += 3) {
    const x = c[i], y = c[i + 1], z = c[i + 2];
    if (x < x0) x0 = x; else if (x > x1) x1 = x;
    if (y < y0) y0 = y; else if (y > y1) y1 = y;
    if (z < z0) z0 = z; else if (z > z1) z1 = z;
  }
  if (x0 < lo.x || y0 < lo.y || z0 < lo.z || x1 > hi.x || y1 > hi.y || z1 > hi.z) {
    lo.set(x0 - MARGIN, y0 - MARGIN, z0 - MARGIN);
    hi.set(x1 + MARGIN, y1 + MARGIN, z1 + MARGIN);
    aabb.setMinMax(lo, hi);
    // the sorter reads a copy taken when a world state is built: ask for a new one
    seen = ++resource.centersVersion;
  }
});
