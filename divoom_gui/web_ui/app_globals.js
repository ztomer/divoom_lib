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
    devicePreviews: {}
};

// R32 §C2: persist last-pushed previews across restarts via localStorage.
try {
    window.DivoomState.devicePreviews = JSON.parse(localStorage.getItem("divoomDevicePreviews") || "{}");
} catch (e) { window.DivoomState.devicePreviews = {}; }

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

// ── R32 §C2: last-pushed device preview ───────────────────────────────
// The device can't report its framebuffer, so we mirror the last image
// this app pushed. setDevicePreview() is called from the image-push sites
// (gallery, custom art); restoreDevicePreview() runs on connect / switch.
window.setDevicePreview = function(address, src) {
    if (!address || !src) return;
    window.DivoomState.devicePreviews[address] = src;
    try {
        localStorage.setItem("divoomDevicePreviews", JSON.stringify(window.DivoomState.devicePreviews));
    } catch (e) { /* quota — non-fatal */ }
    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    if (activeMac === address) {
        const img = document.getElementById("banner-device-image");
        if (img) img.src = src;
    }
};

window.restoreDevicePreview = function(address, fallbackSrc) {
    const img = document.getElementById("banner-device-image");
    if (!img) return;
    const stored = window.DivoomState.devicePreviews[address];
    img.src = stored || fallbackSrc || "assets/pixoo.png";
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
        entries.push({ value: "MatrixWall", name: "Matrix Wall Grid" });
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
    // R34 §2: pulse the sidebar device dot being connected (same amber
    // dot-pulse the appbar dot uses). Cleared by re-render on success or
    // explicitly on failure.
    const deviceDot = document.querySelector(
        `#device-dots .transport-dot[data-value="${(window.CSS && CSS.escape) ? CSS.escape(address) : address}"]`);
    if (deviceDot) { deviceDot.classList.add("connecting"); deviceDot.removeAttribute("style"); }

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
                // R32 §C3: refresh the switch dots so the active one highlights.
                if (window.renderDeviceDots) window.renderDeviceDots();
                // banner-device-res and banner-device-speaker moved to Settings → Devices.
                // Their textContent assignments are intentionally skipped here.
                const isSpk = name.toLowerCase().includes("timoo") || name.toLowerCase().includes("ditoo");
                window.updateSidebarSpeakerIcon(isSpk);
                const sidebarSelect = document.getElementById("sidebar-device-select");
                if (sidebarSelect) sidebarSelect.value = address;
                if (window.updateSyncTargetList) window.updateSyncTargetList();
                if (window.updateChannelButtonsVisibility) window.updateChannelButtonsVisibility(name);
            } else {
                window.DivoomState.appConnected = false;
                window.showToast(`Failed to connect to ${name}`, "error");
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
    if (Object.keys(window.DivoomState.assignedSlots || {}).length > 0) addOpt("MatrixWall", " Matrix Wall Grid");
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
