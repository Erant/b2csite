// b2csite: keep the subject framed at any stage size.
//
// The viewer sets the camera's fov every update, on the wider axis, so a tall
// figure overflows a wide stage and a wide one a narrow stage. After that
// update this replaces it with the vertical fov that fits the subject's half
// extents (settings.b2cFit, written by tools/build.py) at the camera's start
// distance and the canvas's current aspect. The turntable swings parts of the
// subject up to fit.radius nearer the camera, where they project larger, so
// the height is fitted at that nearest distance. It is recomputed every frame,
// so window resizes reframe at once. Zoom still works: it moves the camera,
// the fov stays.
const settings = await window.sse.settings;
const fit = settings.b2cFit;
const initial = settings.cameras?.[0]?.initial;

if (fit && initial) {
    const [px, py, pz] = initial.position;
    const [tx, ty, tz] = initial.target;
    const distance = Math.hypot(px - tx, py - ty, pz - tz);

    // the viewer publishes window.app on its first frame
    const app = await new Promise((resolve) => {
        const poll = () => (window.app ? resolve(window.app) : setTimeout(poll, 50));
        poll();
    });
    const camera = app.root.findComponents('camera')[0];

    // registered after the viewer's own 'update' handler, so this runs after it
    app.on('update', () => {
        if (app.xr?.active) return;
        const { width, height } = app.graphicsDevice;
        if (!width || !height) return;
        const near = distance - (fit.radius ?? 0);
        const tanHeight = fit.halfHeight / near;
        const tanWidth = fit.halfWidth / Math.sqrt(distance * distance - fit.halfWidth * fit.halfWidth);
        camera.horizontalFov = false;
        camera.fov = (2 * Math.atan(Math.max(tanHeight, (tanWidth * height) / width)) * 180) / Math.PI;
    });
}
