// b2csite: the viewer's play / pause also plays and pauses the clip.
//
// The viewer's button (and Space) only drive its own camera track, the
// turntable; the clip plays on its own (the viewer's src/b2c). This holds the
// clip on its current frame when the viewer pauses, and resumes it from there
// when it plays. Orbiting by hand leaves the track but not the pause (the
// viewer keeps its paused flag), so a paused pose can be looked around, and a
// running subject keeps running while you look around it.
const viewer = await window.sse.viewer;
const b2c = await new Promise((resolve) => {
  const poll = () => (window.b2c?.clip ? resolve(window.b2c) : setTimeout(poll, 50));
  poll();
});

// ?b2cframe=N (the viewer's hold, for comparisons) wins
if (!new URLSearchParams(location.search).has("b2cframe")) {
  const { state, events } = viewer;
  let held = false;
  const sync = (hold) => {
    if (hold === held) return;
    held = hold;
    b2c.hold(hold ? Math.max(0, b2c.shown()) : null);
  };
  events.on("animationPaused:changed", (paused) => sync(paused));
  // before the turntable starts the viewer is paused in orbit mode; only a pause in the track counts
  sync(state.cameraMode === "anim" && state.animationPaused);
}

// Play after orbiting by hand returns to the turntable at the track's own time,
// so the camera swung round to wherever that was. Pick the track up at the
// point of its circle nearest the current view instead: the viewer's glide
// into the track then only evens out zoom and height. The track (the viewer's
// createRotateTrack) circles the settings camera's target from its start
// position, one turn per animationDuration, clockwise seen from above.
const settings = await window.sse.settings;
const initial = settings.cameras?.[0]?.initial;
if (initial && !settings.animTracks?.length) {
  const { state, events } = viewer;
  const [px, , pz] = initial.position;
  const [tx, , tz] = initial.target;
  const startAngle = Math.atan2(px - tx, pz - tz);
  const camera = window.app.root.findComponents("camera")[0].entity;
  events.on("cameraMode:changed", (mode, prev) => {
    if (mode !== "anim" || prev === "anim" || !state.loaded || !(state.animationDuration > 0)) return;
    const p = camera.getPosition();
    const turn = (startAngle - Math.atan2(p.x - tx, p.z - tz)) / (2 * Math.PI);
    viewer.seek((turn - Math.floor(turn)) * state.animationDuration);
  });
}
