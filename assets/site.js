// One viewer for the whole page: the gallery swaps what it shows, so there is
// only ever one WebGL context, and #<id> deep-links to a subject.
(async () => {
  const $ = (id) => document.getElementById(id);
  const viewer = $("viewer");
  const grid = $("grid");

  const { featured, runs } = await (await fetch("data/gallery.json")).json();
  if (!runs.length) return;
  const index = new Map(runs.map((r, i) => [r.id, i]));
  let current = -1;

  // The viewer opens its controls guide for first-time visitors, over the
  // turntable; the page has its own hint, so start it closed (same origin, so
  // the viewer reads this storage; its help button still opens the guide).
  try {
    if (localStorage.getItem("controlsPanelOpen") === null) localStorage.setItem("controlsPanelOpen", "false");
  } catch {}

  const mb = (bytes) => `${(bytes / 1e6).toFixed(1)} MB`;

  const viewerUrl = (id) =>
    `viewer/index.html?content=${encodeURIComponent(`../splats/${id}.sog`)}` +
    `&settings=${encodeURIComponent(`../settings/${id}.json`)}&webgl`;

  function show(i, { scroll = false } = {}) {
    i = (i + runs.length) % runs.length;
    if (i === current) return;
    current = i;
    const run = runs[i];

    // replace() keeps the iframe's navigations out of the page's history
    const url = viewerUrl(run.id);
    if (viewer.contentWindow && viewer.src) viewer.contentWindow.location.replace(url);
    else viewer.src = url;

    $("run-id").textContent = run.id;
    $("input-img").src = run.input ? `inputs/${run.id}.webp` : "";
    $("input-img").closest("figure").hidden = !run.input;
    $("prompt").textContent = run.prompt ?? "";
    $("prompt").parentElement.hidden = !run.prompt;
    $("stat-count").textContent = run.gaussians.toLocaleString("en-US");
    $("stat-size").textContent = mb(run.sog_bytes);
    $("download").href = `splats/${run.id}.sog`;

    for (const card of grid.querySelectorAll(".card")) {
      card.setAttribute("aria-current", card.dataset.id === run.id ? "true" : "false");
    }
    history.replaceState(null, "", `#${run.id}`);
    if (scroll) $("stage").scrollIntoView({ block: "start" });
  }

  $("gallery-count").textContent = `${runs.length} subjects`;
  for (const run of runs) {
    const li = document.createElement("li");
    li.innerHTML = `
      <button type="button" class="card" data-id="${run.id}" aria-label="Subject ${run.id}">
        <img class="front" src="thumbs/${run.id}-front.webp" alt="" loading="lazy" decoding="async" width="480" height="720">
        <img class="back" src="thumbs/${run.id}-back.webp" alt="" loading="lazy" decoding="async" width="480" height="720">
        <span>${run.id}</span>
      </button>`;
    li.firstElementChild.addEventListener("click", () => show(index.get(run.id), { scroll: true }));
    grid.append(li);
  }

  $("prev").addEventListener("click", () => show(current - 1));
  $("next").addEventListener("click", () => show(current + 1));
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select")) return;
    if (e.key === "ArrowLeft") show(current - 1);
    if (e.key === "ArrowRight") show(current + 1);
  });

  const fromHash = () => index.get(location.hash.slice(1));
  window.addEventListener("hashchange", () => {
    const i = fromHash();
    if (i !== undefined) show(i, { scroll: true });
  });
  const linked = fromHash();
  show(linked ?? index.get(featured) ?? 0, { scroll: linked !== undefined });
})();
