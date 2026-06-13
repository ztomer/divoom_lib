/* app_globals.js — Global state, utilities, connection actions, arranger render */
/* app.js — Main UI coordinator, free-form display wall arranger, and local configurations */

// ── 1. GLOBAL STATE INITIALIZATION ──
window.DivoomState = {
    appConnected: false,
    discoveredDevices: [],
    assignedSlots: {},
    selectedColor: "00FFCC",
    activeChannel: "clock",
    registeredLanDevices: [],
    loadedArtworks: [],
    selectedArtworkIndex: null,
    savedTickers: [],
    // R32 §C2: last image pushed to each device (address → image src).
    devicePreviews: {},
    // R46 #2: last-active element per device (address → {kind, src}).
    deviceActivity: {}
};

// R32 §C2: persist last-pushed previews across restarts via localStorage.
try {
    window.DivoomState.devicePreviews = JSON.parse(localStorage.getItem("divoomDevicePreviews") || "{}");
} catch (e) { window.DivoomState.devicePreviews = {}; }
try {
    window.DivoomState.deviceActivity = JSON.parse(localStorage.getItem("divoomDeviceActivity") || "{}");
} catch (e) { window.DivoomState.deviceActivity = {}; }

// ── 2. GLOBAL UTILITY FUNCTIONS ──
window.showToast = function(message, type = "success", transport = null) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.className = `toast ${type} show`;
    const suffix = transport ? `<span class="toast-transport">${transport}</span>` : '';
    toast.innerHTML = message + suffix;
    setTimeout(() => { toast.classList.remove("show"); }, 3000);
};

window.requireDevice = function() {
    if (!window.DivoomState.appConnected) {
        window.showToast("Connect a device first — scan and connect under Settings.", "error");
        return false;
    }
    return true;
};

window.deviceColor = function(key) {
    let h = 0, s = String(key || "");
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return `hsl(${h % 360}, 70%, 55%)`;
};

// ── R32 §C2 / R44 §7: last-pushed device preview ──────────────────────
// The device can't report its framebuffer, so we mirror the last frame this
// app (or a daemon live job) pushed. R44 §7: the product PNG stays as the
// device BODY; the frame is composited into the device's SCREEN region via the
// #banner-device-screen overlay, so the preview shows what's on the device now.
//
// Per-model screen rectangle (percent of the product image). The matrix sits in
// a different spot per model; tune here. Default covers the central LED area.
window._DEVICE_SCREEN_RECTS = {
    "tivoo-max": { x: 25, y: 20, w: 50, h: 44, r: 2 },
    "tivoo":     { x: 22, y: 20, w: 56, h: 48, r: 2 },
    "ditoo":     { x: 22, y: 27, w: 56, h: 45, r: 3 },
    "timoo":     { x: 20, y: 20, w: 60, h: 56, r: 2 },
    "timebox":   { x: 19, y: 19, w: 62, h: 62, r: 3 },
    "pixoo64":   { x: 12, y: 12, w: 76, h: 76, r: 2 },
    "pixoo":     { x: 15, y: 15, w: 70, h: 70, r: 2 },
};

window._applyDeviceScreenRect = function(name) {
    const overlay = document.getElementById("banner-device-screen");
    if (!overlay) return;
    const n = (name || "").toLowerCase();
    let rect = window._DEVICE_SCREEN_RECTS.pixoo;   // sensible default
    for (const key of Object.keys(window._DEVICE_SCREEN_RECTS)) {
        if (n.includes(key)) { rect = window._DEVICE_SCREEN_RECTS[key]; break; }
    }
    overlay.style.setProperty("--screen-x", rect.x + "%");
    overlay.style.setProperty("--screen-y", rect.y + "%");
    overlay.style.setProperty("--screen-w", rect.w + "%");
    overlay.style.setProperty("--screen-h", rect.h + "%");
    overlay.style.setProperty("--screen-radius", (rect.r || 2) + "px");
};

window._setScreenOverlayFrame = function(src) {
    const overlay = document.getElementById("banner-device-screen");
    if (!overlay) return;
    if (src) {
        overlay.style.backgroundImage = `url("${src}")`;
        overlay.classList.add("has-frame");
    } else {
        overlay.style.backgroundImage = "";
        overlay.classList.remove("has-frame");
    }
};

window.setDevicePreview = function(address, src) {
    if (!address || !src) return;
    window.DivoomState.devicePreviews[address] = src;
    try {
        localStorage.setItem("divoomDevicePreviews", JSON.stringify(window.DivoomState.devicePreviews));
    } catch (e) { /* quota — non-fatal */ }
    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    if (activeMac === address) {
        window._setScreenOverlayFrame(src);   // composite into the screen, not the whole body
    }
};

window.restoreDevicePreview = function(address, fallbackSrc) {
    const img = document.getElementById("banner-device-image");
    if (!img) return;
    // The product image is the device body; the live frame goes in the screen.
    img.src = fallbackSrc || "assets/pixoo.png";
    const name = (document.getElementById("banner-device-name")?.textContent || "").trim();
    window._applyDeviceScreenRect(name);
    window._setScreenOverlayFrame(window.DivoomState.devicePreviews[address] || null);
};

// ── R46 #2: per-device "last active element" preview ──────────────────────
// The device preview should show what each device is doing. Image content
// (live widgets, custom art, cover art) supplies a real frame; channels render
// on the device, so we draw a recognizable glyph for them.
window._channelPreviewSVG = function(kind, opts) {
    opts = opts || {};
    const a = opts.color || "#00ffcc";
    const k = (kind || "").toLowerCase();
    let inner;
    if (k === "clock") {
        inner = `<circle cx="32" cy="34" r="20" fill="none" stroke="#fff" stroke-width="3"/>`
              + `<line x1="32" y1="34" x2="32" y2="20" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`
              + `<line x1="32" y1="34" x2="43" y2="38" stroke="#fff" stroke-width="3" stroke-linecap="round"/>`;
    } else if (k === "visualizer" || k === "eq") {
        inner = `<rect x="13" y="36" width="8" height="16" fill="${a}"/><rect x="24" y="22" width="8" height="30" fill="${a}"/>`
              + `<rect x="35" y="30" width="8" height="22" fill="${a}"/><rect x="46" y="16" width="8" height="36" fill="${a}"/>`;
    } else if (k === "vj") {
        inner = `<path d="M32 11 L38 27 L55 32 L38 37 L32 53 L26 37 L9 32 L26 27 Z" fill="${a}"/>`;
    } else if (k === "scoreboard") {
        inner = `<text x="32" y="42" font-size="20" font-family="monospace" font-weight="bold" fill="#fff" text-anchor="middle">0:0</text>`;
    } else if (k === "text") {
        inner = `<text x="32" y="44" font-size="34" font-family="sans-serif" font-weight="bold" fill="#fff" text-anchor="middle">T</text>`;
    } else if (k === "ambient") {
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="${a}"/></svg>`;
        return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
    } else if (k === "design" || k === "custom") {
        inner = `<rect x="16" y="16" width="14" height="14" fill="${a}"/><rect x="34" y="16" width="14" height="14" fill="#fff"/>`
              + `<rect x="16" y="34" width="14" height="14" fill="#fff"/><rect x="34" y="34" width="14" height="14" fill="${a}"/>`;
    } else {
        inner = `<circle cx="32" cy="32" r="7" fill="#888"/>`;
    }
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#0a0b10"/>${inner}</svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
};

// Set a device's "last active" preview: kind="image" uses opts.src (a real
// frame); any channel kind draws its glyph. Persists via setDevicePreview and
// records the kind (for the appbar tooltip / the menubar previews, #3).
window.setDeviceActivity = function(mac, kind, opts) {
    if (!mac || mac === "None") return;
    opts = opts || {};
    const src = (kind === "image" && opts.src) ? opts.src : window._channelPreviewSVG(kind, opts);
    window.DivoomState.deviceActivity = window.DivoomState.deviceActivity || {};
    window.DivoomState.deviceActivity[mac] = { kind: kind, src: src, at: Date.now() };
    try { localStorage.setItem("divoomDeviceActivity", JSON.stringify(window.DivoomState.deviceActivity)); } catch (e) {}
    window.setDevicePreview(mac, src);
};

window._activeDeviceMac = function() {
    return (document.getElementById("banner-device-mac")?.textContent || "").trim();
};

// R46 #5: a re-scan replaced discoveredDevices wholesale, so a device the
// daemon is busy STREAMING to (connected → not advertising → scan misses it)
// vanished from the selector. Union the fresh scan with the known devices by
// address (fresh data wins) so an in-use device stays selectable.
window.mergeDiscoveredDevices = function(fresh) {
    const byAddr = {};
    (window.DivoomState.discoveredDevices || []).forEach(d => {
        if (d && d.address) byAddr[d.address] = d;
    });
    (fresh || []).forEach(d => {
        if (d && d.address) byAddr[d.address] = Object.assign(byAddr[d.address] || {}, d);
    });
    window.DivoomState.discoveredDevices = Object.values(byAddr);
    return window.DivoomState.discoveredDevices;
};

// ── R32 §C3: per-device switch dots overlaid on the preview ───────────
window.renderDeviceDots = function() {
    const host = document.getElementById("device-dots");
    if (!host) return;
    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    const entries = [];
    (window.DivoomState.discoveredDevices || []).forEach(d => {
        if (d.address) entries.push({ value: d.address, name: d.name || "Bluetooth Screen" });
    });
    (window.DivoomState.registeredLanDevices || []).forEach(d => {
        if (d.ip) entries.push({ value: `LAN:${d.ip}`, name: `Wi-Fi: ${d.ip}` });
    });
    if (Object.keys(window.DivoomState.assignedSlots || {}).length > 0) {
        entries.push({ value: "MatrixWall", name: "Virtual Wall" });
    }
    host.innerHTML = "";
    entries.forEach(e => {
        const isActive = e.value === activeMac;
        const dot = document.createElement("span");
        // Recycle the connectivity-dot class so the look (size, glow, inactive
        // dimming) stays identical; color comes from the per-device hue. The
        // glow uses currentColor, so set both background and color.
        dot.className = "transport-dot " + (isActive ? "active" : "inactive");
        const color = window.deviceColor(e.value);
        dot.style.background = color;
        dot.style.color = color;
        // R34 §2: lets connectDevice find this dot and pulse it while connecting.
        dot.dataset.value = e.value;
        dot.title = e.name;
        dot.setAttribute("role", "tab");
        dot.setAttribute("aria-selected", isActive ? "true" : "false");
        dot.addEventListener("click", () => window.connectDevice(e.name, e.value));
        host.appendChild(dot);
    });
};

window.getDeviceDimensions = function(name) {
    const n = (name || "").toLowerCase();
    if (n.includes("tivoo-max") || n.includes("tivoo max")) return { width: 160, height: 140, size: 16, image: "assets/tivoo_max.png" };
    if (n.includes("timoo")) return { width: 80, height: 80, size: 16, image: "assets/timoo.png" };
    if (n.includes("ditoo")) return { width: 90, height: 90, size: 16, image: "assets/ditoo.png" };
    if (n.includes("timebox") || n.includes("evo")) return { width: 100, height: 100, size: 16, image: "assets/timebox.png" };
    if (n.includes("pixoo") && n.includes("64")) return { width: 260, height: 260, size: 64, image: "assets/pixoo.png" };
    return { width: 200, height: 200, size: 16, image: "assets/pixoo.png" };
};

// ── 3. CONNECTION ACTIONS ──
// updateSidebarSpeakerIcon was removed — speaker status now lives in
// Settings → Devices tables. Kept as a no-op for backward compatibility.
window.updateSidebarSpeakerIcon = function(_hasSpeaker) {
    return;
};

window.connectDevice = function(name, address) {
    window.showToast(`Connecting to ${name}...`, "success");
    const statusDot = document.getElementById("global-status-dot");
    if (statusDot) { statusDot.className = "transport-dot connecting"; statusDot.removeAttribute("style"); }
    // R35 §2: pulse the sidebar device dot being connected, in the device's
    // own accent color (CSS var --dot-pulse-color, amber fallback for the
    // global dot). Cleared by re-render on success or explicitly on failure.
    const deviceDot = document.querySelector(
        `#device-dots .transport-dot[data-value="${(window.CSS && CSS.escape) ? CSS.escape(address) : address}"]`);
    if (deviceDot) {
        deviceDot.classList.add("connecting");
        // Pulse in the device's accent color (CSS var, fallback amber).
        deviceDot.style.setProperty("--dot-pulse-color", window.deviceColor(address));
    }

    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.connect_single_device(address).then(res => {
            if (res) {
                window.DivoomState.appConnected = true;
                const type = address === "MatrixWall" ? "wall" : (address.startsWith("LAN:") ? "lan" : "ble");
                const label = type === "wall" ? " Wall" : (type === "lan" ? " LAN" : " BLE");
                window.showToast(`Connected to ${name}!`, "success", label);
                if (statusDot) { statusDot.className = `transport-dot active ${type}`; statusDot.removeAttribute("style"); }
                
                document.getElementById("banner-device-name").textContent = name;
                document.getElementById("banner-device-mac").textContent = address;
                // R32 §C2: prefer the last-pushed preview; fall back to the
                // product icon when this device hasn't been pushed to yet.
                const dims = window.getDeviceDimensions(name);
                window.restoreDevicePreview(address, dims.image);
                if (window.renderDeviceDots) window.renderDeviceDots();
                if (window.loadDeviceName) window.loadDeviceName();
                if (window.restoreActiveWidgetForDevice) window.restoreActiveWidgetForDevice(address);
                // banner-device-res and banner-device-speaker moved to Settings → Devices.
                // Their textContent assignments are intentionally skipped here.
                const isSpk = name.toLowerCase().includes("timoo") || name.toLowerCase().includes("ditoo") || name.toLowerCase().includes("tivoo");
                window.updateSidebarSpeakerIcon(isSpk);
                const sidebarSelect = document.getElementById("sidebar-device-select");
                if (sidebarSelect) sidebarSelect.value = address;
                if (window.updateSyncTargetList) window.updateSyncTargetList();
                if (window.updateChannelButtonsVisibility) window.updateChannelButtonsVisibility(name);
            } else {
                window.DivoomState.appConnected = false;
                // BLE Hardening P1: show the daemon's actionable reason (asleep /
                // BT off / held by the phone app), not a generic failure.
                if (window.pywebview?.api?.get_last_connect_error) {
                    window.pywebview.api.get_last_connect_error().then(msg => {
                        window.showToast(msg && msg.trim()
                            ? `${name}: ${msg}` : `Failed to connect to ${name}`, "error");
                    });
                } else {
                    window.showToast(`Failed to connect to ${name}`, "error");
                }
                if (statusDot) { statusDot.className = "transport-dot inactive"; statusDot.removeAttribute("style"); }
                // R34 §2: stop the pulse + restore the per-device hue.
                if (window.renderDeviceDots) window.renderDeviceDots();
                document.getElementById("banner-device-name").textContent = "None";
                document.getElementById("banner-device-mac").textContent = "None";
                window.updateSidebarSpeakerIcon(false);
                if (window.updateSyncTargetList) window.updateSyncTargetList();
                if (window.updateChannelButtonsVisibility) window.updateChannelButtonsVisibility("None");
            }
        });
    }
};

// ── BLE Hardening P6: appbar connection heartbeat ─────────────────────────
// The connect/disconnect handlers set the dot at transition time, but a link
// can DROP mid-session (device sleeps, RF blip). Poll the daemon's honest
// connection_state so the dot reflects DEGRADED (amber) and a genuine drop,
// not a stale solid "connected".
window._activeTransportType = function() {
    const mac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    if (mac === "MatrixWall") return "wall";
    if (mac.startsWith("LAN:")) return "lan";
    return "ble";
};

window.refreshConnectionState = function() {
    if (!window.DivoomState.appConnected) return;
    const api = window.pywebview && window.pywebview.api;
    if (!api || !api.get_connection_state) return;
    api.get_connection_state().then(raw => {
        let s;
        try { s = JSON.parse(raw); } catch (e) { return; }
        const dot = document.getElementById("global-status-dot");
        if (!dot) return;
        const state = s && s.state;
        if (state === "degraded") {
            // Reports connected but a write/drop just failed — show amber, keep
            // appConnected (the daemon's live-job self-heal may revive it).
            dot.className = "transport-dot active degraded";
            dot.removeAttribute("style");
            dot.title = "Link degraded — reconnecting";
        } else if (s && s.connected) {
            const type = window._activeTransportType();
            dot.className = `transport-dot active ${type}`;
            dot.removeAttribute("style");
            dot.title = "";
        } else {
            // Genuinely dropped while we thought we were connected.
            window.DivoomState.appConnected = false;
            dot.className = "transport-dot inactive";
            dot.removeAttribute("style");
            dot.title = "Disconnected";
        }
    }).catch(() => {});
};

window.startConnectionHeartbeat = function() {
    if (window._connHeartbeat) return;
    window._connHeartbeat = setInterval(window.refreshConnectionState, 4000);
};

window.updateDeviceSelectorDropdown = function() {
    const sel = document.getElementById("sidebar-device-select");
    if (!sel) return;
    sel.innerHTML = '<option value="">Select Screen...</option>';
    const curr = document.getElementById("banner-device-mac")?.textContent || "";
    
    const addOpt = (val, txt) => {
        const opt = document.createElement("option");
        opt.value = val; opt.textContent = txt;
        if (curr === val) opt.selected = true;
        sel.appendChild(opt);
    };
    
    // R32 §C1: user-facing names are clean — no "BLE:" transport prefix.
    // The transport is already conveyed by the connectivity dots; the name
    // alone (e.g. "Pixoo64") reads better in the selector.
    window.DivoomState.discoveredDevices.forEach(d => addOpt(d.address, d.name));
    window.DivoomState.registeredLanDevices.forEach(d => addOpt(`LAN:${d.ip}`, d.ip));
    if (Object.keys(window.DivoomState.assignedSlots || {}).length > 0) addOpt("MatrixWall", " Virtual Wall");
    // R32 §C3: the dots mirror the (now hidden) select's options.
    if (window.renderDeviceDots) window.renderDeviceDots();
};

// ── 4. FREE-FORM DISPLAY WALL ARRANGER CANVAS ──
const arrangerCanvas = document.getElementById("arranger-canvas");

window.syncArrangerToPython = function() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_wall_slots(JSON.stringify(window.DivoomState.assignedSlots));
    }
    if (window.updateSyncTargetList) window.updateSyncTargetList();
    // R32 §C3: wall slots changed → the MatrixWall dot may appear/disappear.
    if (window.renderDeviceDots) window.renderDeviceDots();
};

window.renderArrangerCanvas = function() {
    if (!arrangerCanvas) return;
    arrangerCanvas.innerHTML = "";

    Object.keys(window.DivoomState.assignedSlots).forEach(mac => {
        const slot = window.DivoomState.assignedSlots[mac];
        if (!slot || !slot.name || !mac || mac === "undefined") {
            delete window.DivoomState.assignedSlots[mac];
            return;
        }
        const node = document.createElement("div");
        node.className = "arranger-node";
        const accent = window.deviceColor(mac);
        Object.assign(node.style, {
            left: `${slot.x}px`, top: `${slot.y}px`,
            width: `${slot.width}px`, height: `${slot.height}px`,
            borderColor: accent
        });
        node.style.setProperty("--node-accent", accent);
        node.title = `${slot.name} — ${mac}`;
        
        const previewInner = slot.preview ? `<img src="${slot.preview}" class="arranger-node-preview" alt="">` : "";
        node.innerHTML = `
            <span class="arranger-node-chip" style="background:${accent}"></span>
            <div class="arranger-node-screen">${previewInner}</div>
            <div class="arranger-node-remove" data-mac="${mac}">×</div>
        `;
        
        let isDragging = false, startX, startY, startLeft, startTop;
        
        node.addEventListener("mousedown", (e) => {
            if (e.target.classList.contains("arranger-node-remove")) {
                delete window.DivoomState.assignedSlots[mac];
                window.renderArrangerCanvas();
                window.syncArrangerToPython();
                e.stopPropagation();
                return;
            }
            isDragging = true;
            node.classList.add("dragging");
            startX = e.clientX; startY = e.clientY;
            startLeft = parseInt(node.style.left) || 0;
            startTop = parseInt(node.style.top) || 0;
            e.preventDefault();
        });
        
        document.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const deltaX = e.clientX - startX, deltaY = e.clientY - startY;
            let newLeft = startLeft + deltaX, newTop = startTop + deltaY;
            const maxLeft = arrangerCanvas.clientWidth - node.clientWidth;
            const maxTop = arrangerCanvas.clientHeight - node.clientHeight;
            newLeft = Math.max(0, Math.min(newLeft, maxLeft));
            newTop = Math.max(0, Math.min(newTop, maxTop));
            
            node.style.left = `${newLeft}px`;
            node.style.top = `${newTop}px`;
            window.DivoomState.assignedSlots[mac].x = newLeft;
            window.DivoomState.assignedSlots[mac].y = newTop;
        });
        
        document.addEventListener("mouseup", () => {
            if (isDragging) {
                isDragging = false;
                node.classList.remove("dragging");
                window.syncArrangerToPython();
            }
        });
        arrangerCanvas.appendChild(node);
    });
};
