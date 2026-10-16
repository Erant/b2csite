// b2csite: play / pause for the clip.
//
// The turntable is off in this viewer: index.html starts it with noanim and
// hides its play / pause and timeline, which only drive the camera's track.
// The subject's own motion is the animation, and the camera moves only when
// you move it. This puts a play / pause button for the clip where the
// viewer's was, and takes Space before the viewer does (the viewer's Space
// would start the turntable). Pausing holds the clip on its frame and playing
// resumes from there; a paused pose can be looked around.
const viewer = await window.sse.viewer;
const b2c = await new Promise((resolve) => {
  const poll = () => (window.b2c?.clip ? resolve(window.b2c) : setTimeout(poll, 50));
  poll();
});

const icon = (name) => `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">
  <g class="sse-stroke"><use href="#${name}" /></g><g class="sse-fill"><use href="#${name}" /></g></svg>`;
const button = document.createElement("button");
button.className = "sse-controlButton";
document.querySelector(".sse-buttonGroup").prepend(button);

// ?b2cframe=N (the viewer's hold, for comparisons) starts paused on that frame
let playing = !new URLSearchParams(location.search).has("b2cframe");
const show = () => {
  button.innerHTML = icon(playing ? "pauseIcon" : "playIcon");
  button.title = button.ariaLabel = playing ? "Pause (Space)" : "Play (Space)";
};
const toggle = () => {
  playing = !playing;
  b2c.hold(playing ? null : Math.max(0, b2c.shown()));
  show();
};
show();

button.addEventListener("click", () => {
  toggle();
  button.blur(); // a focused button would also take the next Space as a click
});

// capture phase on window, so this runs before the viewer's own shortcut listener
window.addEventListener(
  "keydown",
  (event) => {
    if (event.key !== " " || event.ctrlKey || event.altKey || event.metaKey) return;
    if (!viewer.state.inputEnabled || viewer.state.cameraMode === "walk") return;
    if (event.target.closest?.("input, textarea, select, [contenteditable]")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!event.repeat) toggle();
  },
  true,
);
