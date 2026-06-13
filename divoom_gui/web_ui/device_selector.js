// Device selector: the per-device switch dots below the sidebar preview, plus
// the logic that keeps daemon-owned (connected, non-advertising) screens in the
// list so they stay selectable. Split out of app_globals.js to stay under the
// 500-LOC file cap.

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

// R47: a device the daemon OWNS (active link or a background live-widget job)
// is connected, so it doesn't advertise and a BLE scan never sees it. Without
// this it shows as "connected" in the appbar but has no selector dot — you
// can't switch to it or stop its widget. Pull the daemon's activity registry
// and union those macs into the selector so an owned device is ALWAYS
// selectable, tagged with what it's streaming.
window.refreshOwnedDevices = function() {
    const api = window.pywebview && window.pywebview.api;
    if (!api || !api.get_device_activity) return;
    api.get_device_activity().then(raw => {
        let act;
        try { act = JSON.parse(raw) || {}; } catch (e) { return; }
        let changed = false;
        Object.keys(act).forEach(mac => {
            if (mac === "MatrixWall") return;   // the wall has its own dot
            const info = act[mac] || {};
            const kind = info.kind || "";
            const state = info.state || "";   // G5: daemon-owned device health
            const streaming = kind && kind !== "idle";
            const known = (window.DivoomState.discoveredDevices || [])
                .find(d => d.address === mac);
            if (!known) {
                window.DivoomState.discoveredDevices.push({
                    address: mac, name: info.name || "Screen",
                    daemonOwned: true, activityKind: kind, activityState: state,
                });
                changed = true;
            } else {
                if (info.name && known.name !== info.name) {
                    known.name = info.name; changed = true;
                }
                if (known.activityKind !== kind) {
                    known.activityKind = kind; changed = true;
                }
                if (known.activityState !== state) {
                    known.activityState = state; changed = true;
                }
                if (streaming && !known.daemonOwned) {
                    known.daemonOwned = true; changed = true;
                }
            }
        });
        if (changed && window.renderDeviceDots) window.renderDeviceDots();
    }).catch(() => {});
};

// ── R32 §C3: per-device switch dots overlaid on the preview ───────────
window.renderDeviceDots = function() {
    const host = document.getElementById("device-dots");
    if (!host) return;
    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    const entries = [];
    (window.DivoomState.discoveredDevices || []).forEach(d => {
        if (d.address) entries.push({
            value: d.address, name: d.name || "Bluetooth Screen",
            streaming: !!(d.daemonOwned && d.activityKind && d.activityKind !== "idle"),
            kind: d.activityKind || "",
            // G5: an owned device whose link degraded/dropped (self-healing).
            degraded: d.activityState === "degraded" || d.activityState === "disconnected",
        });
    });
    (window.DivoomState.registeredLanDevices || []).forEach(d => {
        if (d.ip) entries.push({ value: `LAN:${d.ip}`, name: `Wi-Fi: ${d.ip}` });
    });
    // The Virtual Wall is NOT a device — it's a composite of screens. It used to
    // sit here as an identical dot, which read as "just another screen". It now
    // has its own distinct button in a row below (renderWallButton).
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
        // R47: a daemon-owned (streaming) device gets a ring so it reads as
        // "busy but selectable" — click it to take it over / stop its widget.
        if (e.streaming && !isActive) dot.classList.add("streaming");
        if (e.degraded) dot.classList.add("degraded");
        dot.title = e.degraded ? `${e.name} — ${e.kind} (reconnecting)`
                  : e.streaming ? `${e.name} — ${e.kind}` : e.name;
        dot.setAttribute("role", "tab");
        dot.setAttribute("aria-selected", isActive ? "true" : "false");
        dot.addEventListener("click", () => window.connectDevice(e.name, e.value));
        host.appendChild(dot);
    });
    if (window.renderWallButton) window.renderWallButton();
};

// The Virtual Wall gets a distinct affordance, not a device dot: it drives many
// screens as one, so it reads as a labeled button with a 2x2 grid glyph, in its
// own row below the dots. Shown only when a wall is configured (Rams: as little
// as possible — no empty control).
window.renderWallButton = function() {
    const host = document.getElementById("wall-button");
    if (!host) return;
    const slots = window.DivoomState.assignedSlots || {};
    const n = Object.keys(slots).length;
    host.innerHTML = "";
    host.hidden = n === 0;
    if (n === 0) return;
    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
    const isActive = activeMac === "MatrixWall";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "wall-button" + (isActive ? " active" : "");
    btn.dataset.value = "MatrixWall";
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    btn.title = `Virtual Wall — drive ${n} screen${n === 1 ? "" : "s"} as one display`;
    btn.innerHTML =
        '<svg class="wall-button-glyph" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">' +
        '<rect x="1" y="1" width="6" height="6" rx="1"/><rect x="9" y="1" width="6" height="6" rx="1"/>' +
        '<rect x="1" y="9" width="6" height="6" rx="1"/><rect x="9" y="9" width="6" height="6" rx="1"/></svg>' +
        '<span class="wall-button-label">Virtual Wall</span>' +
        `<span class="wall-button-count">${n}</span>`;
    btn.addEventListener("click", () => window.connectDevice("Virtual Wall", "MatrixWall"));
    host.appendChild(btn);
};

// R47: surface a scan in progress in the main UI (the Scan button is buried in
// Settings, so a scan used to give no feedback in the sidebar where the device
// dots live).
window.setScanning = function(on) {
    const el = document.getElementById("scan-indicator");
    if (el) el.hidden = !on;
};
