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
    savedTickers: []
};

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
    
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.connect_single_device(address).then(res => {
            if (res) {
                window.DivoomState.appConnected = true;
                const type = address === "MatrixWall" ? "wall" : (address.startsWith("LAN:") ? "lan" : "ble");
                const label = type === "wall" ? "🧱 Wall" : (type === "lan" ? "🟢 LAN" : "🔵 BLE");
                window.showToast(`Connected to ${name}!`, "success", label);
                if (statusDot) { statusDot.className = `transport-dot active ${type}`; statusDot.removeAttribute("style"); }
                
                document.getElementById("banner-device-name").textContent = name;
                document.getElementById("banner-device-mac").textContent = address;
                const dims = window.getDeviceDimensions(name);
                document.getElementById("banner-device-image").src = dims.image;
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
    
    window.DivoomState.discoveredDevices.forEach(d => addOpt(d.address, `🔵 BLE: ${d.name}`));
    window.DivoomState.registeredLanDevices.forEach(d => addOpt(`LAN:${d.ip}`, `🟢 LAN: ${d.ip}`));
    if (Object.keys(window.DivoomState.assignedSlots || {}).length > 0) addOpt("MatrixWall", "🧱 Matrix Wall Grid");
};

// ── 4. FREE-FORM DISPLAY WALL ARRANGER CANVAS ──
const arrangerCanvas = document.getElementById("arranger-canvas");

window.syncArrangerToPython = function() {
    if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.update_wall_slots(JSON.stringify(window.DivoomState.assignedSlots));
    }
    if (window.updateSyncTargetList) window.updateSyncTargetList();
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

document.addEventListener("DOMContentLoaded", () => {

    // ── 0. FRAMELESS WINDOW DRAG (appbar) ──
    // The window drag is handled by pywebview's built-in drag-region
    // mechanism: <header class="integrated-appbar pywebview-drag-region">
    // matches the DRAG_REGION_SELECTOR, and customize.js
    // (webview/js/customize.js:69-89) walks the DOM looking for that
    // selector and dispatches `pywebviewMoveWindow` to the cocoa
    // backend (BrowserView.move).
    //
    // macOS multi-monitor coordinate double-count: the bundled
    // BrowserView.move adds `self.screen.origin.x` to the X coord
    // the JS sends, which jumps the window off-screen when the
    // window is on a secondary monitor with non-zero origin
    // (upstream issue #1820, May 2026). We apply the
    // upstream-recommended monkey-patch in gui_main.py before
    // `webview.create_window` that drops the `self.screen.origin.x`
    // term from BrowserView.move. The patch is a no-op on
    // single-monitor setups.

    // Inject HTML Templates
    if (document.getElementById('monthly-best') && window.DivoomTemplates?.monthlyBest) {
        document.getElementById('monthly-best').innerHTML = window.DivoomTemplates.monthlyBest;
    }
    if (document.getElementById('data-sources') && window.DivoomTemplates?.widgets) {
        document.getElementById('data-sources').innerHTML = window.DivoomTemplates.widgets;
    }
    if (document.getElementById('settings') && window.DivoomTemplates?.settings) {
        document.getElementById('settings').innerHTML = window.DivoomTemplates.settings;
    }

    // ── 5. CANVAS ARRANGER AND PRESETS BINDINGS ──
    const addArrangerBtn = document.getElementById("add-arranger-screen-btn");
    if (addArrangerBtn) {
        addArrangerBtn.addEventListener("click", () => {
            document.querySelectorAll(".arranger-popup").forEach(p => p.remove());
            
            const bleOptions = (window.DivoomState.discoveredDevices || []).map(d => `<option value="${d.address}">🔵 BLE: ${d.name}</option>`);
            const lanOptions = (window.DivoomState.registeredLanDevices || []).map(d => `<option value="LAN:${d.ip}">🟢 LAN: ${d.ip}</option>`);
            const combinedOptions = bleOptions.concat(lanOptions).join("");

            if (!combinedOptions) {
                window.showToast("No devices found. Scan BLE screens or configure a LAN screen first!", "error");
                return;
            }
            
            const popup = document.createElement("div");
            popup.className = "arranger-popup";
            popup.innerHTML = `
                <h3 style="font-family: var(--font-display); font-size:16px; margin-bottom:15px; color: var(--text-main);">Add Screen to Arranger</h3>
                <select id="canvas-add-select" class="custom-select" style="width:100%; margin-bottom:15px;">${combinedOptions}</select>
                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button id="canvas-add-cancel" class="glow-btn compact" style="background:rgba(130,131,138,0.1); border: 1px solid var(--border-color); color: var(--text-main); box-shadow:none;">Cancel</button>
                    <button id="canvas-add-confirm" class="glow-btn compact" style="background: var(--primary); border: 1px solid var(--primary); color:#fff; box-shadow:none;">Add Node</button>
                </div>
            `;
            
            document.body.appendChild(popup);
            document.getElementById("canvas-add-cancel").addEventListener("click", () => popup.remove());
            document.getElementById("canvas-add-confirm").addEventListener("click", () => {
                const selectEl = document.getElementById("canvas-add-select");
                const addr = selectEl ? selectEl.value : "";
                popup.remove();
                if (!addr) return;
                if (window.DivoomState.assignedSlots[addr]) {
                    window.showToast("Device already placed on canvas!", "error");
                    return;
                }
                const isLan = addr.startsWith("LAN:");
                let devName = "Divoom Screen";
                if (isLan) {
                    devName = `Wi-Fi Screen: ${addr.split("LAN:")[1]}`;
                } else {
                    const dev = window.DivoomState.discoveredDevices.find(d => d.address === addr);
                    devName = dev ? dev.name : "Divoom Screen";
                }
                const dims = window.getDeviceDimensions(devName);
                const placementX = Math.round((arrangerCanvas.clientWidth - dims.width) / 2);
                const placementY = Math.round((arrangerCanvas.clientHeight - dims.height) / 2);
                
                window.DivoomState.assignedSlots[addr] = {
                    x: placementX, y: placementY, width: dims.width, height: dims.height,
                    size: dims.size, name: devName, image: dims.image
                };
                window.renderArrangerCanvas();
                window.syncArrangerToPython();
            });
        });
    }

    const clearArrangerBtn = document.getElementById("clear-arranger-btn");
    if (clearArrangerBtn) {
        clearArrangerBtn.addEventListener("click", () => {
            window.DivoomState.assignedSlots = {};
            window.renderArrangerCanvas();
            window.syncArrangerToPython();
        });
    }

    const presetsSelect = document.getElementById("presets-select");
    if (presetsSelect) {
        presetsSelect.addEventListener("change", (e) => {
            const name = e.target.value;
            if (!name) return;
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.load_preset_by_name(name).then(slotsJson => {
                    if (slotsJson) {
                        window.DivoomState.assignedSlots = JSON.parse(slotsJson);
                        window.renderArrangerCanvas();
                        window.showToast(`Layout preset '${name}' applied!`, "success");
                    }
                });
            }
        });
    }

    const savePresetBtn = document.getElementById("save-preset-btn");
    if (savePresetBtn) {
        savePresetBtn.addEventListener("click", () => {
            if (Object.keys(window.DivoomState.assignedSlots).length === 0) return;
            const name = prompt("Enter a unique preset name:", "My Layout Preset");
            if (!name) return;
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_preset(name, JSON.stringify(window.DivoomState.assignedSlots)).then(res => {
                    if (res) {
                        window.showToast(`Saved layout '${name}'`, "success");
                        window.pywebview.api.load_preset_names().then(namesJson => {
                            if (namesJson && presetsSelect) {
                                const names = JSON.parse(namesJson);
                                presetsSelect.innerHTML = '<option value="">Load Preset...</option>';
                                names.forEach(n => {
                                    const opt = document.createElement("option");
                                    opt.value = n; opt.textContent = n;
                                    presetsSelect.appendChild(opt);
                                });
                            }
                        });
                    }
                });
            }
        });
    }

    // ── 6. NATIVE FILE BROWSERS ──
    const browseCustomArtBtn = document.getElementById("browse-custom-art-btn");
    const customArtPathInput = document.getElementById("custom-art-path-input");
    const customArtPreviewContainer = document.getElementById("custom-art-preview-container");
    const customArtPreviewImg = document.getElementById("custom-art-preview-img");
    const applyCustomArtBtn = document.getElementById("apply-custom-art-btn");

    if (browseCustomArtBtn) {
        browseCustomArtBtn.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.open_file_dialog) {
                window.pywebview.api.open_file_dialog().then(path => {
                    if (path) {
                        if (customArtPathInput) customArtPathInput.value = path;
                        if (window.showCustomArtPreview) window.showCustomArtPreview(path);
                    }
                });
            }
        });
    }

    if (applyCustomArtBtn) {
        applyCustomArtBtn.addEventListener("click", () => {
            if (!window.requireDevice()) return;
            const path = customArtPathInput?.value;
            if (!path) return;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.display_custom_art) {
                window.pywebview.api.display_custom_art(path).then(res => {
                    if (res) {
                        window.showToast("Custom artwork displayed!", "success", "🔵 BLE");
                        const filename = path.split("/").pop();
                        if (window.addCustomArtToHistory) {
                            window.addCustomArtToHistory(filename, path, "file://" + path);
                        }
                    } else {
                        window.showToast("Failed to display", "error");
                    }
                });
            }
        });
    }

    const browseWallArtBtn = document.getElementById("browse-wall-art-btn");
    const filePathInput = document.getElementById("file-path-input");
    const filePreviewContainer = document.getElementById("file-preview-container");
    const filePreviewImg = document.getElementById("file-preview-img");

    if (browseWallArtBtn) {
        browseWallArtBtn.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api && window.pywebview.api.open_file_dialog) {
                window.pywebview.api.open_file_dialog().then(path => {
                    if (path) {
                        if (filePathInput) filePathInput.value = path;
                        if (filePreviewImg) filePreviewImg.src = "file://" + path;
                        if (filePreviewContainer) filePreviewContainer.style.display = "flex";
                    }
                });
            }
        });
    }

    const applyWallArtBtn = document.getElementById("apply-wall-art");
    if (applyWallArtBtn) {
        applyWallArtBtn.addEventListener("click", () => {
            const path = filePathInput?.value.trim();
            if (!path) return;
            if (Object.keys(window.DivoomState.assignedSlots).length === 0) return;
            window.showToast("Splitting image and syncing wall...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.display_wall_image(path, 16).then(res => {
                    if (res) window.showToast("Synchronized display wall", "success", "🔵 BLE");
                });
            }
        });
    }

    // ── 7. BRIGHTNESS SLIDERS AND TARGET CHANGE HANDLERS ──
    const globalBrightnessSlider = document.getElementById("global-brightness-slider");
    const globalBrightnessValue = document.getElementById("global-brightness-value");
    
    if (globalBrightnessSlider) {
        globalBrightnessSlider.addEventListener("input", (e) => {
            const val = e.target.value;
            if (globalBrightnessValue) globalBrightnessValue.textContent = val + "%";
        });
        globalBrightnessSlider.addEventListener("change", (e) => {
            const val = parseInt(e.target.value);
            if (!window.DivoomState.appConnected) return;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.set_brightness) {
                window.pywebview.api.set_brightness(val).then(res => {
                    if (res) window.showToast(`Brightness set to ${val}%`, "success", "🔵 BLE");
                });
            }
        });
    }

    const sidebarDeviceSelect = document.getElementById("sidebar-device-select");
    if (sidebarDeviceSelect) {
        sidebarDeviceSelect.addEventListener("change", (e) => {
            const addr = e.target.value;
            if (!addr) return;
            if (addr === "MatrixWall") {
                window.connectDevice("Matrix Wall Grid", "MatrixWall");
            } else if (addr.startsWith("LAN:")) {
                const ip = addr.split("LAN:")[1];
                window.connectDevice(`Wi-Fi Screen: ${ip}`, addr);
            } else {
                const dev = window.DivoomState.discoveredDevices.find(d => d.address === addr);
                const name = dev ? dev.name : "Bluetooth Device";
                window.connectDevice(name, addr);
            }
        });
    }

    // ── 8. INITIAL SESSION RESTORE ON MOUNT ──
    setTimeout(() => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_config().then(configJson => {
                if (configJson) {
                    const conf = JSON.parse(configJson);
                    const getEl = id => document.getElementById(id);
                    if (conf.email && getEl("settings-email")) getEl("settings-email").value = conf.email;
                    if (conf.timeout != null && getEl("scan-timeout")) getEl("scan-timeout").value = conf.timeout;
                    if (conf.limit != null && getEl("scan-limit")) getEl("scan-limit").value = conf.limit;
                    
                    if (conf.slots) { window.DivoomState.assignedSlots = conf.slots; window.renderArrangerCanvas(); }
                    if (conf.devices && conf.devices.length > 0) { window.DivoomState.discoveredDevices = conf.devices; window.renderArrangerCanvas(); }
                    
                    if (conf.last_connected_device) {
                        const addr = conf.last_connected_device;
                        let name = "Divoom Screen";
                        if (addr === "MatrixWall") name = "Matrix Wall Grid";
                        else if (addr.startsWith("LAN:")) name = `Wi-Fi: ${addr.split("LAN:")[1]}`;
                        else {
                            const dev = window.DivoomState.discoveredDevices.find(d => d.address === addr);
                            if (dev) name = dev.name;
                        }
                        setTimeout(() => window.connectDevice(name, addr), 500);
                    }

                    if (conf.last_detected_count && conf.last_detected_count > 0 && window.runBleScan) {
                        setTimeout(() => { window.showToast("Resuming session: Auto-scanning screens...", "success"); window.runBleScan(); }, 1000);
                    }
                    
                    const statusBox = getEl("divoom-cloud-status-box");
                    if (statusBox) {
                        const isConn = !!conf.cloud_connected;
                        statusBox.style.display = "flex";
                        statusBox.style.background = isConn ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)";
                        statusBox.style.border = isConn ? "1px solid rgba(34, 197, 94, 0.3)" : "1px solid rgba(239, 68, 68, 0.3)";
                        statusBox.style.color = isConn ? "#22c55e" : "#ef4444";
                        statusBox.innerHTML = `<span>${isConn ? '🟢 Connected as <b>' + (conf.cloud_email || conf.email) + '</b>' : '🔴 Not connected. Save credentials to log in.'}</span>`;
                    }
                }
            });
            
            window.pywebview.api.load_preset_names().then(namesJson => {
                if (namesJson && presetsSelect) {
                    const names = JSON.parse(namesJson);
                    presetsSelect.innerHTML = '<option value="">Load Preset...</option>';
                    names.forEach(n => {
                        const opt = document.createElement("option");
                        opt.value = n; opt.textContent = n;
                        presetsSelect.appendChild(opt);
                    });
                }
            });
        }
        
        // Realtime Custom Art Preview Helper
        window.showCustomArtPreview = function(path) {
            if (!path) {
                if (customArtPreviewContainer) customArtPreviewContainer.style.display = "none";
                return;
            }
            if (customArtPreviewImg) {
                const src = (path.startsWith("data:") || path.startsWith("file://") || path.startsWith("http"))
                    ? path
                    : "file://" + path;
                customArtPreviewImg.src = src;
            }
            if (customArtPreviewContainer) {
                customArtPreviewContainer.style.display = "flex";
            }
        };
        
        // Close modals on tab change
        window.addEventListener("tab-changed", () => {
            document.querySelectorAll(".arranger-popup").forEach(p => p.remove());
        });
    }, 1000);
});
