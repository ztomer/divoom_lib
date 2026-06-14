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

// ── R49: flat face-on screen preview ──────────────────────────────────
// The device can't report its framebuffer, so we mirror the last frame this
// app (or a daemon live job) pushed. R49: the product photos are 3/4
// perspective renders, so compositing a frame onto them landed it crooked.
// We now show the frame straight in a neutral bezel (#banner-device-screen) —
// a face-on screen, aligned for any model, with no per-model rect to tune.

window._setScreenOverlayFrame = function(src) {
    const screen = document.getElementById("banner-device-screen");
    if (!screen) return;
    if (src) {
        screen.style.backgroundImage = `url("${src}")`;
        screen.classList.add("has-frame");
    } else {
        screen.style.backgroundImage = "";
        screen.classList.remove("has-frame");
    }
};

// Empty-state hint below the screen. When a device IS active, its name is
// already shown (highlighted) in the chip directly below — repeating it here was
// redundant, so we only show this as the "nothing connected" placeholder.
window._updateDeviceLabel = function(name) {
    const label = document.getElementById("banner-device-label");
    if (!label) return;
    const n = (name || "").trim();
    if (!n || n === "None" || n === "No Connected Screen") {
        label.textContent = "No screen connected";
        label.hidden = false;
    } else {
        label.hidden = true;   // the active chip carries the name
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
        window._setScreenOverlayFrame(src);
    }
};

window.restoreDevicePreview = function(address, _fallbackSrc) {
    // R49: no product photo anymore — just show this device's last frame in the
    // flat screen (or the empty state when nothing has been pushed yet).
    window._setScreenOverlayFrame(window.DivoomState.devicePreviews[address] || null);
};

// ── R46 #2: per-device "last active element" preview ──────────────────────
// The device preview should show what each device is doing. Image content
// (live widgets, custom art, cover art) supplies a real frame; channels render
// on the device, so we draw a recognizable glyph for them.
// R50: render the SPECIFIC clock face the user picked (6 styles), not a generic
// clock glyph — mirrors the channel tiles (channels_grids.js CLOCK_FACES).
window._clockFaceSVG = function(style, color) {
    const c = color || "#ffffff";
    const t = (txt, fill, extra) =>
        `<text x="32" y="40" font-size="18" font-family="monospace" font-weight="bold"`
        + ` fill="${fill}" text-anchor="middle"${extra || ""}>${txt}</text>`;
    let inner, bg = "#0a0b10";
    switch (Number(style)) {
        case 1: // Rainbow — each glyph a different hue
            inner = ["#ff5a5a", "#ffc864", "#5ede91", "#5aabff", "#c89bff"]
                .map((h, i) => `<text x="${10 + i * 11}" y="40" font-size="16"`
                    + ` font-family="monospace" font-weight="bold" fill="${h}">${"12:00"[i]}</text>`)
                .join("");
            break;
        case 2: // With Box — time inside a rounded border
            inner = `<rect x="9" y="24" width="46" height="20" rx="3" fill="none"`
                  + ` stroke="${c}" stroke-width="2"/>` + t("12:00", c);
            break;
        case 3: // Analog Square
            inner = `<rect x="14" y="14" width="36" height="36" rx="4" fill="none" stroke="${c}" stroke-width="2.5"/>`
                  + `<line x1="32" y1="32" x2="32" y2="20" stroke="${c}" stroke-width="2.5" stroke-linecap="round"/>`
                  + `<line x1="32" y1="32" x2="42" y2="32" stroke="${c}" stroke-width="2" stroke-linecap="round"/>`;
            break;
        case 4: // Full Screen Neg — inverted: color fills the screen, dark digits
            bg = c; inner = t("12:00", "#1a2318");
            break;
        case 5: // Analog Round
            inner = `<circle cx="32" cy="32" r="19" fill="none" stroke="${c}" stroke-width="2.5"/>`
                  + `<line x1="32" y1="32" x2="32" y2="18" stroke="${c}" stroke-width="2.5" stroke-linecap="round"/>`
                  + `<line x1="32" y1="32" x2="42" y2="37" stroke="${c}" stroke-width="2" stroke-linecap="round"/>`;
            break;
        default: // 0 Full Screen digital
            inner = t("12:00", c);
    }
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">`
              + `<rect width="64" height="64" fill="${bg}"/>${inner}</svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
};

window._channelPreviewSVG = function(kind, opts) {
    opts = opts || {};
    const a = opts.color || "#00ffcc";
    const k = (kind || "").toLowerCase();
    let inner;
    if (k === "clock") {
        // R50: reflect the selected face + color (falls back to current state).
        const style = (opts.style != null) ? opts.style
                    : (window.DivoomState.selectedClockStyle ?? 0);
        const color = opts.color
                    || document.getElementById("clock-color-input")?.value || "#ffffff";
        return window._clockFaceSVG(style, color);
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
    // R46 #3: push the CHANNEL kind to the daemon so the menubar can show a
    // per-device tile. Live-widget image content is skipped here — the daemon
    // already sets that kind itself (sysmon/stocks/weather/music) on
    // live_job_start, so we'd only clobber it with "image".
    if (kind !== "image" && window.pywebview?.api?.set_device_activity) {
        const dev = (window.DivoomState.discoveredDevices || []).find(d => d.address === mac);
        const name = (dev && dev.name) || (mac === window._activeDeviceMac()
            ? (document.getElementById("banner-device-name")?.textContent || "").trim() : "");
        try { window.pywebview.api.set_device_activity(mac, kind, name || ""); } catch (e) {}
    }
};

window._activeDeviceMac = function() {
    return (document.getElementById("banner-device-mac")?.textContent || "").trim();
};

// R46 #2: mirror the active widget's pushed frame to its device's last-active
// preview (used by the sysmon/music/stocks pollers).
window.markActiveDeviceFrame = function(src) {
    const mac = window._activeDeviceMac();
    if (mac && mac !== "None" && src && window.setDeviceActivity)
        window.setDeviceActivity(mac, "image", { src: src });
};

// R47: device-dots / selector logic (mergeDiscoveredDevices, refreshOwnedDevices,
// renderDeviceDots, setScanning) lives in device_selector.js to keep this file
// under the 500-LOC cap.

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
        `#device-dots [data-value="${(window.CSS && CSS.escape) ? CSS.escape(address) : address}"]`);
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
                window._updateDeviceLabel(name);
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
                window._updateDeviceLabel(null);
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
    // R47: keep daemon-owned devices in the selector even when this GUI didn't
    // start them (a widget persisted from a prior session, or another client).
    window.refreshOwnedDevices();
    window._ownedHeartbeat = setInterval(window.refreshOwnedDevices, 4000);
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
