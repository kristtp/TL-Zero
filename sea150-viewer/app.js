const MAP_SIZE = 7200;
const MAP_HALF = MAP_SIZE / 2;
const RESOURCE_BINS = ["data/textasset_0_47767.bin", "../analysis-assets/map-geometry/textasset_0_47767.bin"];
const STATIC_CSVS = ["data/static_units.csv", "../analysis-assets/map-geometry/static_units.csv"];
const STITCHED_IMGS = ["data/stitched_map.png", "../analysis-assets/survey-run/stitched_map.png"];
const STITCHED_PREVIEWS = ["data/stitched_map_preview.jpg", "../analysis-assets/survey-run/stitched_map_preview.jpg"];
const CONFIRMED_TRAP = { id: "ZeroOne", x: 1967, y: 1685, source: "Live capture 2026-09-11" };

// SHA-512 authentication hash for Stitched Layer access
// Matches 'ZeroOne' by default, or loaded from private/public inaccessible hash file
const AUTH_HASH_DEFAULT = "a50463443742fb282e67d6a086b361149417838b7079b3cbd323cb4a9ea8250788cd0d276d9a188520f922ed28c04740204ef8b9df45ea98bf968e329cd43494";
let targetAuthHash = AUTH_HASH_DEFAULT;

async function loadAuthHash() {
  try {
    const res = await fetch("data/auth.sha512?t=" + Date.now());
    if (res.ok) {
      const text = (await res.text()).trim().toLowerCase();
      if (text.length === 128) targetAuthHash = text;
    }
  } catch (_) {}
}
loadAuthHash();

async function sha512(str) {
  const buf = new TextEncoder().encode(str);
  const hashBuf = await crypto.subtle.digest("SHA-512", buf);
  const hashArr = Array.from(new Uint8Array(hashBuf));
  return hashArr.map(b => b.toString(16).padStart(2, "0")).join("");
}

const colors = { island: "#d49b27", plant: "#2fa66d", stone: "#748592" };
const canvas = document.querySelector("#mapCanvas");
const context = canvas.getContext("2d");
const frame = canvas.parentElement;
const state = {
  resources: [], wonders: [], traps: [CONFIRMED_TRAP], scale: 1, offsetX: 0, offsetY: 0,
  dragging: false, moved: false, lastX: 0, lastY: 0,
  showStitched: false, stitchedImage: null, stitchedAvailable: false,
  mouseX: null, mouseY: null, mouseOver: false
};
window.state = state;

function loadAddedTraps() {
  try {
    const stored = JSON.parse(localStorage.getItem("sea150-added-traps") || "[]");
    state.traps = [CONFIRMED_TRAP, ...stored.filter(item => Number.isFinite(item.x) && Number.isFinite(item.y))];
  } catch { state.traps = [CONFIRMED_TRAP]; }
  document.querySelector("#trapCount").textContent = state.traps.length;
}

function saveAddedTraps() {
  localStorage.setItem("sea150-added-traps", JSON.stringify(state.traps.slice(1)));
  document.querySelector("#trapCount").textContent = state.traps.length;
}

function resourceInfo(configId) {
  const group = Math.floor((configId - 140000) / 100);
  const suffix = configId % 100;
  const names = { 1: "Island beach", 2: "Giant plants", 3: "Stone" };
  const types = { 1: "island", 2: "plant", 3: "stone" };
  return { type: types[suffix] || "stone", name: names[suffix] || "Resource", level: (group - 1) * 3 + suffix };
}

async function fetchFirst(urls, asBinary = false) {
  for (const url of urls) {
    try {
      const res = await fetch(url);
      if (res.ok) return asBinary ? await res.arrayBuffer() : await res.text();
    } catch (_) {}
  }
  throw new Error("Could not load from any candidate URL: " + urls.join(", "));
}

async function loadResources() {
  const buffer = await fetchFirst(RESOURCE_BINS, true);
  const view = new DataView(buffer);
  const count = view.getUint32(0, true);
  const rows = [];
  for (let index = 0; index < count; index++) {
    const offset = 4 + index * 29;
    const worldX = view.getFloat32(offset, true);
    const worldZ = view.getFloat32(offset + 8, true);
    const configId = view.getInt32(offset + 24, true);
    rows.push({ index, x: worldX, y: worldZ, configId, ...resourceInfo(configId) });
  }
  return rows;
}

async function loadWonders() {
  const text = await fetchFirst(STATIC_CSVS, false);
  return text.trim().split(/\r?\n/).slice(1).map(line => {
    const values = line.split(",");
    return { index: +values[0], x: +values[1], y: +values[3], unitId: +values[4], mapId: +values[5] };
  });
}

function getWindowRect() {
  const isMobile = frame.clientWidth <= 640;
  // On mobile, render the static box at 90% of screen width dynamically
  const size = isMobile 
    ? Math.round(frame.clientWidth * 0.90)
    : Math.max(200, Math.min(frame.clientWidth - 56, frame.clientHeight - 56));
  const x = Math.round((frame.clientWidth - size) / 2);
  const y = Math.round((frame.clientHeight - size) / 2);
  return { x, y, width: size, height: size };
}

function resize() {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(frame.clientWidth * ratio);
  canvas.height = Math.round(frame.clientHeight * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}

function fitMap() {
  const box = getWindowRect();
  state.scale = box.width / MAP_SIZE;
  state.offsetX = box.x;
  state.offsetY = box.y;
  draw();
}

function focus(x, y, scale = 0.55) {
  const box = getWindowRect();
  const boxCenterX = box.x + box.width / 2;
  const boxCenterY = box.y + box.height / 2;
  state.scale = scale;
  state.offsetX = boxCenterX - (x + MAP_HALF) * scale;
  state.offsetY = boxCenterY - (MAP_HALF - y) * scale;
  draw();
}

function screenPoint(x, y) { return [state.offsetX + (x + MAP_HALF) * state.scale, state.offsetY + (MAP_HALF - y) * state.scale]; }
function mapPoint(x, y) { return [(x - state.offsetX) / state.scale - MAP_HALF, MAP_HALF - (y - state.offsetY) / state.scale]; }
window.screenPoint = screenPoint;
window.mapPoint = mapPoint;
window.focus = focus;
window.fitMap = fitMap;

function drawSea(x, y, w, h) {
  const gradient = context.createLinearGradient(x, y, x + w, y + h);
  gradient.addColorStop(0, "#0d6278");
  gradient.addColorStop(0.52, "#168ba0");
  gradient.addColorStop(1, "#0b526b");
  context.fillStyle = gradient;
  context.fillRect(x, y, w, h);
  context.strokeStyle = "#ffffff12";
  context.lineWidth = 1;
  for (let waveY = y + 20; waveY < y + h; waveY += 28) {
    context.beginPath();
    for (let waveX = x - 20; waveX < x + w + 20; waveX += 24) {
      const curY = waveY + Math.sin((waveX + waveY) * 0.028) * 5;
      if (waveX === x - 20) context.moveTo(waveX, curY); else context.lineTo(waveX, curY);
    }
    context.stroke();
  }
}

function drawGrid() {
  if (!document.querySelector("#gridToggle").checked) return;
  context.lineWidth = 1;
  context.font = "10px Consolas";
  for (let value = -MAP_HALF; value <= MAP_HALF; value += 600) {
    const [x] = screenPoint(value, MAP_HALF);
    const [, y] = screenPoint(-MAP_HALF, value);
    context.strokeStyle = value % 1800 === 0 ? "#d8f4ef55" : "#d8f4ef24";
    context.beginPath(); context.moveTo(x, state.offsetY); context.lineTo(x, state.offsetY + MAP_SIZE * state.scale); context.stroke();
    context.beginPath(); context.moveTo(state.offsetX, y); context.lineTo(state.offsetX + MAP_SIZE * state.scale, y); context.stroke();
    if (state.scale > 0.08) {
      context.fillStyle = "#d8f4efaa";
      context.fillText(value, x + 3, state.offsetY + 13);
      context.fillText(value, state.offsetX + 3, y - 3);
    }
  }
}

function drawResources() {
  if (!document.querySelector("#resourcesToggle").checked) return;
  const enabled = new Set([...document.querySelectorAll(".resource-filter:checked")].map(input => input.dataset.type));
  for (const item of state.resources) {
    if (!enabled.has(item.type)) continue;
    const [x, y] = screenPoint(item.x, item.y);
    if (x < -8 || y < -8 || x > frame.clientWidth + 8 || y > frame.clientHeight + 8) continue;
    const radius = Math.max(1.5, Math.min(5, state.scale * 10));
    context.fillStyle = colors[item.type];
    context.globalAlpha = state.scale < 0.12 ? 0.72 : 0.9;
    context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill();
  }
  context.globalAlpha = 1;
}

function drawWonders() {
  if (!document.querySelector("#wondersToggle").checked) return;
  for (const item of state.wonders) {
    const [x, y] = screenPoint(item.x, item.y);
    const size = Math.max(7, Math.min(15, state.scale * 24));
    context.save(); context.translate(x, y); context.rotate(Math.PI / 4);
    context.fillStyle = item.unitId === 243001 ? "#f6d55c" : "#f1eee4";
    context.strokeStyle = "#173342"; context.lineWidth = 2;
    context.fillRect(-size / 2, -size / 2, size, size); context.strokeRect(-size / 2, -size / 2, size, size);
    context.restore();
  }
}

function drawTraps() {
  if (!document.querySelector("#trapsToggle").checked) return;
  for (const trap of state.traps) {
    const [x, y] = screenPoint(trap.x, trap.y);
    const radius = Math.max(8, Math.min(18, state.scale * 28));
    const isCurrent = trap.id === CONFIRMED_TRAP.id || (trap.x === CONFIRMED_TRAP.x && trap.y === CONFIRMED_TRAP.y);
    context.fillStyle = isCurrent ? "#2ca02c" : "#d62728";
    context.strokeStyle = "#fff7db";
    context.lineWidth = 3;
    context.beginPath(); context.arc(x, y, radius, 0, Math.PI * 2); context.fill(); context.stroke();
    context.fillStyle = "white"; context.font = `700 ${Math.max(10, radius)}px Georgia`;
    context.textAlign = "center"; context.textBaseline = "middle"; context.fillText("T", x, y + 1);
  }
  context.textAlign = "start"; context.textBaseline = "alphabetic";
}

function drawCrosshair() {
  if (!state.mouseOver || state.mouseX == null || state.mouseY == null) return;
  const x = Math.round(state.mouseX);
  const y = Math.round(state.mouseY);
  const width = frame.clientWidth;
  const height = frame.clientHeight;

  context.save();
  // Thin full-screen crosshair dashed lines
  context.lineWidth = 1;
  context.strokeStyle = "rgba(0, 240, 255, 0.45)";
  context.setLineDash([4, 4]);
  context.beginPath();
  context.moveTo(0, y); context.lineTo(width, y);
  context.moveTo(x, 0); context.lineTo(x, height);
  context.stroke();
  context.setLineDash([]);

  // Outer dark border for high contrast over any background
  const r = 13;
  context.lineWidth = 3;
  context.strokeStyle = "rgba(0, 0, 0, 0.85)";
  context.beginPath();
  context.arc(x, y, r, 0, Math.PI * 2);
  context.moveTo(x - r - 8, y); context.lineTo(x - 3, y);
  context.moveTo(x + 3, y); context.lineTo(x + r + 8, y);
  context.moveTo(x, y - r - 8); context.lineTo(x, y - 3);
  context.moveTo(x, y + 3); context.lineTo(x, y + r + 8);
  context.stroke();

  // Inner bright glowing reticle
  context.lineWidth = 1.5;
  context.strokeStyle = "#00f0ff";
  context.beginPath();
  context.arc(x, y, r, 0, Math.PI * 2);
  context.moveTo(x - r - 8, y); context.lineTo(x - 3, y);
  context.moveTo(x + 3, y); context.lineTo(x + r + 8, y);
  context.moveTo(x, y - r - 8); context.lineTo(x, y - 3);
  context.moveTo(x, y + 3); context.lineTo(x, y + r + 8);
  context.stroke();

  // Center targeting dot
  context.fillStyle = "#ffffff";
  context.beginPath();
  context.arc(x, y, 2.5, 0, Math.PI * 2);
  context.fill();

  context.restore();
}

function draw() {
  const width = frame.clientWidth;
  const height = frame.clientHeight;
  context.clearRect(0, 0, width, height);

  // 1. Fixed stage background (outside the viewing window)
  context.fillStyle = "#07171f";
  context.fillRect(0, 0, width, height);

  const box = getWindowRect();

  // 2. Confine all map layers strictly within the fixed viewing window (microscope aperture)
  context.save();
  context.beginPath();
  context.rect(box.x, box.y, box.width, box.height);
  context.clip();

  // Draw oceanic base inside the window
  context.fillStyle = "#09313d";
  context.fillRect(box.x, box.y, box.width, box.height);

  const [left, top] = screenPoint(-MAP_HALF, MAP_HALF);
  const mapScreenSize = MAP_SIZE * state.scale;

  if (state.showStitched && state.stitchedImage && state.stitchedImage.complete) {
    context.drawImage(state.stitchedImage, left, top, mapScreenSize, mapScreenSize);
  } else {
    drawSea(left, top, mapScreenSize, mapScreenSize);
  }

  // Subtle boundary outline of SEA 150 territory
  context.strokeStyle = "rgba(241, 223, 173, 0.4)";
  context.lineWidth = 1;
  context.strokeRect(left, top, mapScreenSize, mapScreenSize);

  drawGrid();
  drawResources();
  drawWonders();
  drawTraps();

  // Crosshair is only drawn if cursor is inside the window
  if (state.mouseX >= box.x && state.mouseX <= box.x + box.width &&
      state.mouseY >= box.y && state.mouseY <= box.y + box.height) {
    drawCrosshair();
  }

  context.restore();

  // 3. Fixed Window Outer Frame (Stationary like a microscope viewing frame)
  context.strokeStyle = "#f1dfad";
  context.lineWidth = 3;
  context.strokeRect(box.x, box.y, box.width, box.height);

  // Corner accents for the viewing frame
  const cornerLen = 14;
  context.strokeStyle = "#d49b27";
  context.lineWidth = 4;
  context.beginPath();
  // Top-left
  context.moveTo(box.x - 2, box.y + cornerLen);
  context.lineTo(box.x - 2, box.y - 2);
  context.lineTo(box.x + cornerLen, box.y - 2);
  // Top-right
  context.moveTo(box.x + box.width - cornerLen, box.y - 2);
  context.lineTo(box.x + box.width + 2, box.y - 2);
  context.lineTo(box.x + box.width + 2, box.y + cornerLen);
  // Bottom-left
  context.moveTo(box.x - 2, box.y + box.height - cornerLen);
  context.lineTo(box.x - 2, box.y + box.height + 2);
  context.lineTo(box.x + cornerLen, box.y + box.height + 2);
  // Bottom-right
  context.moveTo(box.x + box.width - cornerLen, box.y + box.height + 2);
  context.lineTo(box.x + box.width + 2, box.y + box.height + 2);
  context.lineTo(box.x + box.width + 2, box.y + box.height - cornerLen);
  context.stroke();
}

function nearestAt(mapX, mapY) {
  const candidates = [];
  if (document.querySelector("#resourcesToggle").checked) for (const item of state.resources) candidates.push({ kind: "Resource", item, distance: Math.hypot(item.x - mapX, item.y - mapY) });
  if (document.querySelector("#wondersToggle").checked) for (const item of state.wonders) candidates.push({ kind: "Goddess", item, distance: Math.hypot(item.x - mapX, item.y - mapY) });
  if (document.querySelector("#trapsToggle").checked) for (const item of state.traps) candidates.push({ kind: "Turtle trap", item, distance: Math.hypot(item.x - mapX, item.y - mapY) });
  return candidates.sort((a, b) => a.distance - b.distance)[0];
}

function inspect(hit) {
  const element = document.querySelector("#selection");
  if (!hit) return;
  const item = hit.item;
  let rows = `<dt>Coordinate</dt><dd>X:${item.x.toFixed(0)} Y:${item.y.toFixed(0)}</dd><dt>Click distance</dt><dd>${hit.distance.toFixed(1)}</dd>`;
  if (hit.kind === "Resource") rows += `<dt>Type</dt><dd>${item.name}</dd><dt>Level</dt><dd>${item.level}</dd><dt>Config</dt><dd>${item.configId}</dd>`;
  if (hit.kind === "Goddess") rows += `<dt>Unit ID</dt><dd>${item.unitId}</dd><dt>Region mask</dt><dd>${item.mapId}</dd>`;
  if (hit.kind === "Turtle trap") rows += `<dt>Owner</dt><dd>${item.id}</dd><dt>Source</dt><dd>${item.source}</dd>`;
  element.className = "selection";
  element.innerHTML = `<h2>${hit.kind}</h2><dl>${rows}</dl>`;
}

// Global suppression of browser page pinch zoom
window.addEventListener("wheel", event => {
  if (event.ctrlKey) {
    event.preventDefault();
  }
}, { passive: false });

let isTouchpadPinching = false;
let touchpadAnchorMap = [0, 0];
let touchpadScreenPos = [0, 0];
let touchpadResetTimer = null;
let isZoomCooldown = false;
let zoomCooldownTimer = null;

canvas.addEventListener("wheel", event => {
  event.preventDefault();

  state.dragging = false;
  isZoomCooldown = true;
  clearTimeout(zoomCooldownTimer);
  zoomCooldownTimer = setTimeout(() => { isZoomCooldown = false; }, 140);

  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;

  let zoomFactor;
  if (event.ctrlKey) {
    // Windows / Mac touchpad pinch gesture
    let dy = event.deltaY;
    if (event.deltaMode === 1) dy *= 16;
    else if (event.deltaMode === 2) dy *= 100;

    const clampedDelta = Math.max(-25, Math.min(25, dy));
    zoomFactor = Math.exp(-clampedDelta * 0.0035);

    if (!isTouchpadPinching) {
      isTouchpadPinching = true;
      touchpadScreenPos = [mouseX, mouseY];
      touchpadAnchorMap = mapPoint(mouseX, mouseY);
    }
    clearTimeout(touchpadResetTimer);
    touchpadResetTimer = setTimeout(() => { isTouchpadPinching = false; }, 160);
  } else {
    isTouchpadPinching = false;
    zoomFactor = event.deltaY < 0 ? 1.12 : 0.89;
  }

  const targetScale = Math.max(0.055, Math.min(1.8, state.scale * zoomFactor));

  const anchorScreen = isTouchpadPinching ? touchpadScreenPos : [mouseX, mouseY];
  const anchorMap = isTouchpadPinching ? touchpadAnchorMap : mapPoint(mouseX, mouseY);

  state.scale = targetScale;
  state.offsetX = anchorScreen[0] - (anchorMap[0] + MAP_HALF) * state.scale;
  state.offsetY = anchorScreen[1] - (MAP_HALF - anchorMap[1]) * state.scale;
  draw();
}, { passive: false });

canvas.addEventListener("dblclick", event => {
  event.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mouseX = event.clientX - rect.left;
  const mouseY = event.clientY - rect.top;
  const box = getWindowRect();

  // Only handle double click if inside the fixed viewing window
  if (mouseX < box.x || mouseX > box.x + box.width || mouseY < box.y || mouseY > box.y + box.height) return;

  const [mapX, mapY] = mapPoint(mouseX, mouseY);
  const targetScale = Math.min(1.8, Math.max(state.scale * 1.6, 0.45));
  focus(mapX, mapY, targetScale);
});

const activePointers = new Map();
let pinchStartDistance = 0;
let pinchStartScale = 1;
let pinchCenterMap = [0, 0];

canvas.addEventListener("pointerdown", event => {
  event.preventDefault();
  activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  try { canvas.setPointerCapture(event.pointerId); } catch (_) {}

  if (activePointers.size === 1) {
    state.dragging = true;
    state.moved = false;
    state.lastX = event.clientX;
    state.lastY = event.clientY;
  } else if (activePointers.size === 2) {
    state.dragging = false;
    state.moved = true; // prevent accidental click inspection
    const pts = Array.from(activePointers.values());
    pinchStartDistance = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    pinchStartScale = state.scale;

    const rect = canvas.getBoundingClientRect();
    const midScreenX = (pts[0].x + pts[1].x) / 2 - rect.left;
    const midScreenY = (pts[0].y + pts[1].y) / 2 - rect.top;
    pinchCenterMap = mapPoint(midScreenX, midScreenY);
  }
});

canvas.addEventListener("pointermove", event => {
  event.preventDefault();
  if (!activePointers.has(event.pointerId)) return;
  activePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

  const rect = canvas.getBoundingClientRect();
  state.mouseX = event.clientX - rect.left;
  state.mouseY = event.clientY - rect.top;

  const box = getWindowRect();
  const insideBox = state.mouseX >= box.x && state.mouseX <= box.x + box.width &&
                    state.mouseY >= box.y && state.mouseY <= box.y + box.height;
  state.mouseOver = insideBox;

  if (insideBox) {
    const [mapX, mapY] = mapPoint(state.mouseX, state.mouseY);
    document.querySelector("#cursorCoords").textContent = `X:${Math.round(mapX)} Y:${Math.round(mapY)}`;
  } else {
    document.querySelector("#cursorCoords").textContent = "X:— Y:—";
  }

  if (activePointers.size === 2) {
    const pts = Array.from(activePointers.values());
    const currentDist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
    if (pinchStartDistance > 10 && currentDist > 10) {
      const zoomFactor = currentDist / pinchStartDistance;
      const targetScale = Math.max(0.055, Math.min(1.8, pinchStartScale * zoomFactor));

      const currentMidX = (pts[0].x + pts[1].x) / 2 - rect.left;
      const currentMidY = (pts[0].y + pts[1].y) / 2 - rect.top;

      state.scale = targetScale;
      state.offsetX = currentMidX - (pinchCenterMap[0] + MAP_HALF) * state.scale;
      state.offsetY = currentMidY - (MAP_HALF - pinchCenterMap[1]) * state.scale;
      draw();
    }
    return;
  }

  if (isZoomCooldown) return;

  if (state.dragging && activePointers.size === 1) {
    const dx = event.clientX - state.lastX;
    const dy = event.clientY - state.lastY;
    if (Math.hypot(dx, dy) > 2) state.moved = true;
    state.offsetX += dx;
    state.offsetY += dy;
    state.lastX = event.clientX;
    state.lastY = event.clientY;
    draw();
  }
});

function endPointer(event) {
  activePointers.delete(event.pointerId);
  try { canvas.releasePointerCapture(event.pointerId); } catch (_) {}

  if (activePointers.size === 1) {
    const remaining = Array.from(activePointers.values())[0];
    state.dragging = true;
    state.moved = true;
    state.lastX = remaining.x;
    state.lastY = remaining.y;
  } else if (activePointers.size === 0) {
    state.dragging = false;
    pinchStartDistance = 0;
  }
}

canvas.addEventListener("pointerup", event => {
  const wasPinching = activePointers.size >= 2;
  endPointer(event);
  if (!state.moved && !wasPinching && activePointers.size === 0) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const box = getWindowRect();
    if (mouseX >= box.x && mouseX <= box.x + box.width &&
        mouseY >= box.y && mouseY <= box.y + box.height) {
      const [mapX, mapY] = mapPoint(mouseX, mouseY);
      inspect(nearestAt(mapX, mapY));
    }
  }
});

canvas.addEventListener("pointercancel", endPointer);

canvas.addEventListener("pointerleave", () => {
  state.mouseOver = false;
  document.querySelector("#cursorCoords").textContent = "X:— Y:—";
  draw();
});

// Native iOS/Safari & Mobile gesture event suppressors
canvas.addEventListener("gesturestart", e => e.preventDefault());
canvas.addEventListener("gesturechange", e => e.preventDefault());
canvas.addEventListener("gestureend", e => e.preventDefault());
canvas.addEventListener("touchstart", e => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
canvas.addEventListener("touchmove", e => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });

function isStitchedAuthenticated() {
  return sessionStorage.getItem("sea150_auth") === "unlocked";
}

function openPasswordModal(onSuccess) {
  const modal = document.querySelector("#passwordModal");
  const input = document.querySelector("#passwordInput");
  const err = document.querySelector("#passwordError");
  if (!modal || !input) return;

  modal.style.display = "flex";
  input.value = "";
  if (err) err.style.display = "none";
  input.focus();

  const cleanup = () => {
    modal.style.display = "none";
    document.querySelector("#closeModalButton")?.removeEventListener("click", onCancel);
    document.querySelector("#cancelPasswordButton")?.removeEventListener("click", onCancel);
    document.querySelector("#passwordForm")?.removeEventListener("submit", onSubmit);
  };

  const onCancel = () => {
    cleanup();
    const toggle = document.querySelector("#stitchedToggle");
    if (toggle) toggle.checked = false;
  };

  const onSubmit = async (e) => {
    e?.preventDefault();
    const entered = input.value;
    const hashed = await sha512(entered);
    if (hashed === targetAuthHash) {
      sessionStorage.setItem("sea150_auth", "unlocked");
      cleanup();
      if (onSuccess) onSuccess();
    } else {
      if (err) err.style.display = "block";
      input.select();
    }
  };

  document.querySelector("#closeModalButton")?.addEventListener("click", onCancel);
  document.querySelector("#cancelPasswordButton")?.addEventListener("click", onCancel);
  document.querySelector("#passwordForm")?.addEventListener("submit", onSubmit);
}

function setStitchedMode(enabled) {
  if (enabled && !isStitchedAuthenticated()) {
    openPasswordModal(() => setStitchedMode(true));
    return;
  }
  state.showStitched = enabled;
  const toggle = document.querySelector("#stitchedToggle");
  const btn = document.querySelector("#toggleStitchedButton");
  if (toggle) toggle.checked = enabled;
  if (btn) {
    btn.textContent = enabled ? "Switch to Synthetic Map" : "Switch to Stitched Map";
    btn.classList.toggle("active", enabled);
  }
  draw();
}

let lastStitchedMod = null;
let lastStitchedLen = null;
let isCheckingStitched = false;

function loadStitchedImage() {
  const tryLoad = (idx) => {
    if (idx >= STITCHED_IMGS.length) {
      state.stitchedAvailable = false;
      const badge = document.querySelector("#stitchedStatus");
      if (badge) badge.textContent = "Offline";
      return;
    }
    const img = new Image();
    img.onload = () => {
      state.stitchedImage = img;
      state.stitchedAvailable = true;
      const badge = document.querySelector("#stitchedStatus");
      if (badge) badge.textContent = "Live";
      draw();
    };
    img.onerror = () => tryLoad(idx + 1);
    img.src = `${STITCHED_IMGS[idx]}?t=${Date.now()}`;
  };
  tryLoad(0);
}

async function checkStitchedUpdate() {
  if (isCheckingStitched) return;
  isCheckingStitched = true;
  try {
    for (const url of STITCHED_PREVIEWS) {
      try {
        const res = await fetch(`${url}?t=${Date.now()}`);
        if (res.ok) {
          const mod = res.headers.get("Last-Modified");
          const len = res.headers.get("Content-Length");
          if (mod !== lastStitchedMod || len !== lastStitchedLen) {
            lastStitchedMod = mod;
            lastStitchedLen = len;
            loadStitchedImage();
          }
          break;
        }
      } catch (_) {}
    }
  } catch (_) {
  } finally {
    isCheckingStitched = false;
  }
}
window.checkStitchedUpdate = checkStitchedUpdate;
window.loadStitchedImage = loadStitchedImage;

function initDirectory() {
  const searchInput = document.querySelector("#directorySearch");
  const countElement = document.querySelector("#directoryResultsCount");
  const listElement = document.querySelector("#directoryList");
  if (!searchInput || !listElement) return;

  function renderDirectory() {
    const query = (searchInput.value || "").toLowerCase().trim();
    const all = [];
    state.traps.forEach(t => all.push({ kind: "Turtle Trap", name: t.id || "Trap", x: t.x, y: t.y, color: "#2ca02c" }));
    state.wonders.forEach(w => all.push({ kind: "Goddess", name: w.unitId === 243001 ? "Great Wonder" : `Goddess #${w.index}`, x: w.x, y: w.y, color: "#f6d55c" }));
    state.resources.forEach(r => all.push({ kind: "Resource", name: `${r.name} Lv.${r.level}`, x: r.x, y: r.y, color: colors[r.type] }));

    const filtered = query ? all.filter(item => 
      item.name.toLowerCase().includes(query) ||
      item.kind.toLowerCase().includes(query) ||
      `${Math.round(item.x)}`.includes(query) ||
      `${Math.round(item.y)}`.includes(query)
    ) : all.slice(0, 80);

    if (countElement) {
      countElement.textContent = `Showing ${filtered.length.toLocaleString()} of ${all.length.toLocaleString()} objects`;
    }

    listElement.innerHTML = filtered.slice(0, 150).map(item => `
      <div class="dir-item" data-x="${item.x}" data-y="${item.y}" style="display: flex; justify-content: space-between; padding: 4px 6px; cursor: pointer; border-bottom: 1px solid #14323b;">
        <span><i style="display:inline-block; width:8px; height:8px; border-radius:50%; background:${item.color}; margin-right:6px;"></i>${item.name}</span>
        <span style="font-family:Consolas,monospace; color:#8ec3c7;">${Math.round(item.x)}, ${Math.round(item.y)}</span>
      </div>
    `).join("");

    listElement.querySelectorAll(".dir-item").forEach(el => {
      el.addEventListener("click", () => {
        focus(Number(el.dataset.x), Number(el.dataset.y), 0.85);
      });
    });
  }

  searchInput.addEventListener("input", renderDirectory);
  renderDirectory();
}

document.querySelectorAll("input").forEach(input => input.addEventListener("change", draw));
document.querySelector("#toggleStitchedButton")?.addEventListener("click", () => setStitchedMode(!state.showStitched));
document.querySelector("#stitchedToggle")?.addEventListener("change", e => setStitchedMode(e.target.checked));
document.querySelector("#fitButton").addEventListener("click", fitMap);
document.querySelector("#zoomReset")?.addEventListener("click", fitMap);
document.querySelector("#trapButton").addEventListener("click", () => focus(1967, 1685));

// Left Controls Sidebar Collapse / Expand Toggle
function toggleControlsSidebar(forceState) {
  const workspace = document.querySelector(".workspace");
  const tabBtn = document.querySelector("#sidebarTabToggle");
  const isCurrentlyCollapsed = workspace.classList.contains("controls-collapsed");
  const willCollapse = forceState !== undefined ? forceState : !isCurrentlyCollapsed;

  if (willCollapse) {
    workspace.classList.add("controls-collapsed");
    if (tabBtn) {
      tabBtn.textContent = "▶";
      tabBtn.title = "Expand Controls";
    }
  } else {
    workspace.classList.remove("controls-collapsed");
    if (tabBtn) {
      tabBtn.textContent = "◀";
      tabBtn.title = "Collapse Controls";
    }
  }

  setTimeout(() => {
    resize();
    fitMap();
  }, 120);
}

// Right Inspector Sidebar Collapse / Expand Toggle
function toggleInspectorSidebar(forceState) {
  const workspace = document.querySelector(".workspace");
  const tabBtn = document.querySelector("#inspectorTabToggle");
  const isCurrentlyCollapsed = workspace.classList.contains("inspector-collapsed");
  const willCollapse = forceState !== undefined ? forceState : !isCurrentlyCollapsed;

  if (willCollapse) {
    workspace.classList.add("inspector-collapsed");
    if (tabBtn) {
      tabBtn.textContent = "◀";
      tabBtn.title = "Expand Directory";
    }
  } else {
    workspace.classList.remove("inspector-collapsed");
    if (tabBtn) {
      tabBtn.textContent = "▶";
      tabBtn.title = "Collapse Directory";
    }
  }

  setTimeout(() => {
    resize();
    fitMap();
  }, 120);
}

document.querySelector("#sidebarTabToggle")?.addEventListener("click", () => toggleControlsSidebar());
document.querySelector("#inspectorTabToggle")?.addEventListener("click", () => toggleInspectorSidebar());

// On mobile (< 640px), auto-collapse both sidebars so static box renders at 90% width dynamically
if (window.innerWidth <= 640) {
  setTimeout(() => {
    toggleControlsSidebar(true);
    toggleInspectorSidebar(true);
  }, 50);
}

document.querySelector("#zoomIn")?.addEventListener("click", () => {
  const box = getWindowRect();
  const [cx, cy] = mapPoint(box.x + box.width / 2, box.y + box.height / 2);
  focus(cx, cy, Math.min(1.8, state.scale * 1.3));
});
document.querySelector("#zoomOut")?.addEventListener("click", () => {
  const box = getWindowRect();
  const [cx, cy] = mapPoint(box.x + box.width / 2, box.y + box.height / 2);
  focus(cx, cy, Math.max(0.055, state.scale / 1.3));
});

// 4-Direction D-Pad Controls with continuous press support
let panInterval = null;

function startContinuousPan(dir) {
  stopContinuousPan();
  const panStep = () => {
    const speed = Math.max(8, Math.min(28, 140 * state.scale));
    switch (dir) {
      case "up":
        state.offsetY -= speed; // Swipe up -> Moves South (-Y)
        break;
      case "down":
        state.offsetY += speed; // Swipe down -> Moves North (+Y)
        break;
      case "left":
        state.offsetX -= speed; // Swipe left -> Moves East (+X)
        break;
      case "right":
        state.offsetX += speed; // Swipe right -> Moves West (-X)
        break;
    }
    draw();
  };
  panStep();
  panInterval = setInterval(panStep, 22);
}

function stopContinuousPan() {
  if (panInterval) {
    clearInterval(panInterval);
    panInterval = null;
  }
}

function bindPanButton(buttonId, dir) {
  const btn = document.querySelector(buttonId);
  if (!btn) return;
  btn.addEventListener("pointerdown", e => {
    e.preventDefault();
    try { btn.setPointerCapture(e.pointerId); } catch (_) {}
    startContinuousPan(dir);
  });
  const stop = (e) => {
    try { btn.releasePointerCapture(e.pointerId); } catch (_) {}
    stopContinuousPan();
  };
  btn.addEventListener("pointerup", stop);
  btn.addEventListener("pointercancel", stop);
  btn.addEventListener("pointerleave", stop);
}

bindPanButton("#panUp", "up");
bindPanButton("#panDown", "down");
bindPanButton("#panLeft", "left");
bindPanButton("#panRight", "right");

document.querySelector("#addTrapButton").addEventListener("click", () => {
  const x = Number(document.querySelector("#trapX").value);
  const y = Number(document.querySelector("#trapY").value);
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < -MAP_HALF || x > MAP_HALF || y < -MAP_HALF || y > MAP_HALF) return;
  state.traps.push({ id: `Observed ${state.traps.length}`, x, y, source: "Manual live observation" });
  saveAddedTraps(); draw();
  document.querySelector("#trapX").value = ""; document.querySelector("#trapY").value = "";
});
document.querySelector("#clearTrapsButton").addEventListener("click", () => { state.traps = [CONFIRMED_TRAP]; saveAddedTraps(); draw(); });
window.addEventListener("resize", resize);

loadAddedTraps();
loadStitchedImage();
setInterval(checkStitchedUpdate, 1500);

Promise.all([loadResources(), loadWonders()]).then(([resources, wonders]) => {
  state.resources = resources; state.wonders = wonders;
  document.querySelector("#resourceCount").textContent = resources.length.toLocaleString();
  document.querySelector("#wonderCount").textContent = wonders.length;
  document.querySelector("#statusText").textContent = "SEA 150 geometry ready";
  initDirectory();
  resize(); fitMap();
}).catch(error => {
  document.querySelector("#statusText").textContent = "Geometry load failed";
  console.error(error);
});