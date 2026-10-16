// b2csite: the viewer's play / pause also plays and pauses the clip.
//
// The viewer's button (and Space) only drive its own camera track, the
// turntable; the clip plays on its own (the viewer's src/b2c). This holds the
// clip on its current frame while the viewer is paused in its track, which is
// what the pause button sets, and resumes it from there on play. Orbiting by
// hand leaves the track without pausing, so the subject keeps moving while
// you look around it.
const viewer = await window.sse.viewer;
const b2c = await new Promise((resolve) => {
  const poll = () => (window.b2c?.clip ? resolve(window.b2c) : setTimeout(poll, 50));
  poll();
});

// ?b2cframe=N (the viewer's hold, for comparisons) wins
if (!new URLSearchParams(location.search).has("b2cframe")) {
  const { state, events } = viewer;
  let held = false;
  const sync = () => {
    const hold = state.cameraMode === "anim" && state.animationPaused;
    if (hold === held) return;
    held = hold;
    b2c.hold(hold ? Math.max(0, b2c.shown()) : null);
  };
  events.on("cameraMode:changed", sync);
  events.on("animationPaused:changed", sync);
  sync();
}
