// Divoom Wall Dashboard Javascript Core Logic
// Hooks UI events directly to pywebview Python API bridge.

document.addEventListener("DOMContentLoaded", () => {
    
    // ── 1. FRAMELESS WINDOW TITLEBAR BUTTON BINDINGS ──
    const winMin = document.getElementById("win-min");
    const winMax = document.getElementById("win-max");
    const winClose = document.getElementById("win-close");

    if (winMin) {
        winMin.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.minimize_window();
            }
        });
    }
    if (winMax) {
        winMax.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.maximize_window();
            }
        });
    }
    if (winClose) {
        winClose.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.close_window();
            }
        });
    }

    // Frameless window dragging relative movement via python API
    let isDragging = false;
    let lastScreenX = 0;
    let lastScreenY = 0;
    const appbar = document.querySelector(".integrated-appbar");
    if (appbar) {
        appbar.addEventListener("mousedown", (e) => {
            if (e.button !== 0 || e.target.closest("button") || e.target.closest("select") || e.target.closest("input")) return;
            isDragging = true;
            lastScreenX = e.screenX;
            lastScreenY = e.screenY;
        });

        window.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const deltaX = e.screenX - lastScreenX;
            const deltaY = e.screenY - lastScreenY;
            lastScreenX = e.screenX;
            lastScreenY = e.screenY;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.drag_window) {
                if (deltaX !== 0 || deltaY !== 0) {
                    window.pywebview.api.drag_window(deltaX, deltaY);
                }
            }
        });

        window.addEventListener("mouseup", () => {
            isDragging = false;
        });
    }

    // ── 2. TAB NAVIGATION ──
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            navButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(t => t.classList.remove("active"));
            
            btn.classList.add("active");
            const targetTab = btn.getAttribute("data-tab");
            document.getElementById(targetTab).classList.add("active");
        });
    });
    
    // ── 2B. THEME SELECTOR WIRING ──
    const themeButtons = document.querySelectorAll(".theme-mode-btn");
    
    function applyTheme(theme) {
        document.body.classList.remove("theme-dark", "theme-light", "theme-system");
        document.body.classList.add(`theme-${theme}`);
        
        themeButtons.forEach(btn => {
            if (btn.getAttribute("data-theme") === theme) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
        
        localStorage.setItem("aesthetic-theme", theme);
    }
    
    themeButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const selectedTheme = btn.getAttribute("data-theme");
            applyTheme(selectedTheme);
        });
    });
    
    const savedTheme = localStorage.getItem("aesthetic-theme") || "dark";
    applyTheme(savedTheme);
    
    // ── 3. AMBIENT LIGHT SWATCHES ──
    const colorSwatches = document.querySelectorAll(".color-swatch");
    const customColorInput = document.getElementById("custom-color-input");
    let selectedColor = "00FFCC"; // Default
    
    colorSwatches.forEach(swatch => {
        swatch.addEventListener("click", () => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            swatch.classList.add("active");
            selectedColor = swatch.getAttribute("data-color");
        });
    });
    
    if (customColorInput) {
        customColorInput.addEventListener("input", (e) => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            selectedColor = e.target.value.replace("#", "");
        });
    }
    
    // Brightness Slider
    const brightnessSlider = document.getElementById("brightness-slider");
    const brightnessVal = document.getElementById("brightness-val");
    if (brightnessSlider) {
        brightnessSlider.addEventListener("input", (e) => {
            brightnessVal.textContent = e.target.value;
        });
    }
    
    // ── 3. CONTROL CENTER: channels + APK/protocol-sourced sub-selectors ──
    const channelCards = document.querySelectorAll(".channel-card");
    const channelPanels = document.querySelectorAll(".channel-panel");
    let activeChannel = "clock";

    // Track active connection so Control Center actions can explain *why* nothing
    // happens (the bridge returns false when no device is connected — the real
    // cause behind "switching channels doesn't work").
    let appConnected = false;
    function requireDevice() {
        if (!appConnected) {
            showToast("Connect a device first — scan and connect under Settings.", "error");
            return false;
        }
        return true;
    }

    function showChannelPanel(channel) {
        channelPanels.forEach(p => p.classList.toggle("active", p.id === `panel-${channel}`));
        const titleEl = document.getElementById("channel-options-title");
        if (titleEl) {
            const channelNames = {
                "clock": "Clock Mode Options",
                "visualizer": "Music EQ Options",
                "vj": "VJ Effects Options",
                "design": "Custom Art Options",
                "ambient": "Ambient Color Options"
            };
            titleEl.textContent = channelNames[channel] || "Channel Options";
        }
    }

    channelCards.forEach(card => {
        card.addEventListener("click", () => {
            channelCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            activeChannel = card.getAttribute("data-channel");
            showChannelPanel(activeChannel);
            // Ambient is a light mode applied via its own button, not a device
            // channel switch, so don't fire switch_channel for it.
            if (activeChannel === "ambient") return;
            if (!requireDevice()) return;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.switch_channel) {
                window.pywebview.api.switch_channel(activeChannel).then(res => {
                    if (res) showToast("Switched channel", "success", "🔵 Bluetooth");
                    else showToast("Failed to switch channel", "error");
                });
            }
        });
    });

    // Generic selector-grid builder. `activeIndex < 0` => no pre-selection.
    function buildSelectorGrid(containerId, items, onSelect, activeIndex = 0, previewMap = null) {
        const grid = document.getElementById(containerId);
        if (!grid) return;
        grid.innerHTML = "";
        items.forEach((it, i) => {
            const cell = document.createElement("button");
            cell.className = "selector-cell" + (i === activeIndex ? " active" : "");
            cell.setAttribute("data-value", it.value);
            
            if (previewMap && previewMap[it.value] !== undefined) {
                const previewWrapper = document.createElement("div");
                previewWrapper.innerHTML = previewMap[it.value];
                cell.appendChild(previewWrapper.firstChild);
            }
            
            const label = document.createElement("div");
            label.className = "cell-label";
            label.textContent = it.name;
            cell.appendChild(label);
            
            cell.addEventListener("click", () => {
                grid.querySelectorAll(".selector-cell").forEach(c => c.classList.remove("active"));
                cell.classList.add("active");
                onSelect(it.value, it.name);
            });
            grid.appendChild(cell);
        });
    }

    // 2.f — REAL built-in Timebox Evo clock dial types (from node-divoom
    // PROTOCOL.md Time channel `TT`), replacing the previously hallucinated set.
    const CLOCK_FACES = [
        { value: 0, name: "Full Screen" }, { value: 1, name: "Rainbow" },
        { value: 2, name: "With Box" }, { value: 3, name: "Analog Square" },
        { value: 4, name: "Full Screen Neg" }, { value: 5, name: "Analog Round" },
    ];
    const CLOCK_PREVIEWS = {
        0: `<div class="clock-preview-box digital-full">12:00</div>`,
        1: `<div class="clock-preview-box digital-rainbow">12:00</div>`,
        2: `<div class="clock-preview-box digital-box"><span>12:00</span></div>`,
        3: `<div class="clock-preview-box analog-square">
                <svg class="mini-clock-svg" viewBox="0 0 40 40">
                    <rect x="2" y="2" width="36" height="36" rx="4" fill="none" stroke="currentColor" stroke-width="2"/>
                    <line x1="20" y1="20" x2="20" y2="10" stroke="currentColor" stroke-width="2"/>
                    <line x1="20" y1="20" x2="30" y2="20" stroke="currentColor" stroke-width="1.5"/>
                </svg>
            </div>`,
        4: `<div class="clock-preview-box digital-neg">12:00</div>`,
        5: `<div class="clock-preview-box analog-round">
                <svg class="mini-clock-svg" viewBox="0 0 40 40">
                    <circle cx="20" cy="20" r="17" fill="none" stroke="currentColor" stroke-width="2"/>
                    <line x1="20" y1="20" x2="20" y2="10" stroke="currentColor" stroke-width="2"/>
                    <line x1="20" y1="20" x2="28" y2="25" stroke="currentColor" stroke-width="1.5"/>
                </svg>
            </div>`
    };
    function applyClockStyle(style) {
        if (!requireDevice()) return;
        const color = document.getElementById("clock-color-input")?.value || "#ffffff";
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_clock(style, color).then(res => {
                showToast(res ? "Clock style applied" : "Failed to apply clock", res ? "success" : "error", "🔵 Bluetooth");
            });
        }
    }

    let selectedClockStyle = 0;
    buildSelectorGrid("clock-faces-grid", CLOCK_FACES, (v) => {
        selectedClockStyle = v;
        applyClockStyle(v);
    }, 0, CLOCK_PREVIEWS);

    const clockColorInput = document.getElementById("clock-color-input");
    if (clockColorInput) {
        clockColorInput.addEventListener("input", () => {
            applyClockStyle(selectedClockStyle);
        });
    }

    // 2.d — 16 named VJ effects (divoom_lib VJEffectType).
    const VJ_EFFECTS = ["Sparkles", "Lava", "Vertical Rainbow", "Drops", "Rainbow Swirl",
        "CMY Fade", "Rainbow Lava", "Pastel Patterns", "CMY Wave", "Fire", "Countdown",
        "Pink/Blue Fade", "Rainbow Polygons", "Pink/Blue Wave", "Rainbow Cross", "Rainbow Shapes"]
        .map((name, i) => ({ value: i, name }));
    const VJ_PREVIEWS = {
        0: `<div class="vj-preview-box sparkles"></div>`,
        1: `<div class="vj-preview-box lava"></div>`,
        2: `<div class="vj-preview-box rainbow-vert"></div>`,
        3: `<div class="vj-preview-box drops"></div>`,
        4: `<div class="vj-preview-box swirl"></div>`,
        5: `<div class="vj-preview-box cmy-fade"></div>`,
        6: `<div class="vj-preview-box rainbow-lava"></div>`,
        7: `<div class="vj-preview-box pastel"></div>`,
        8: `<div class="vj-preview-box cmy-wave"></div>`,
        9: `<div class="vj-preview-box fire"></div>`,
        10: `<div class="vj-preview-box countdown"></div>`,
        11: `<div class="vj-preview-box pink-blue-fade"></div>`,
        12: `<div class="vj-preview-box rainbow-poly"></div>`,
        13: `<div class="vj-preview-box pink-blue-wave"></div>`,
        14: `<div class="vj-preview-box rainbow-cross"></div>`,
        15: `<div class="vj-preview-box rainbow-shapes"></div>`
    };
    buildSelectorGrid("vj-effects-grid", VJ_EFFECTS, (v) => {
        if (!requireDevice()) return;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_vj_effect) {
            window.pywebview.api.set_vj_effect(v).then(res => {
                showToast(res ? "VJ effect applied" : "Failed to apply VJ effect", res ? "success" : "error", "🔵 Bluetooth");
            });
        }
    }, -1, VJ_PREVIEWS);

    // 2.c — Music EQ / visualizer patterns. Count verified against all four
    // physical devices (they accept indices 0–15 cleanly).
    const EQ_PATTERNS = Array.from({ length: 16 }, (_, i) => ({ value: i, name: `EQ ${String(i + 1).padStart(2, "0")}` }));
    const EQ_PREVIEWS = {};
    for (let i = 0; i < 16; i++) {
        const styleNum = (i % 5) + 1;
        const delay1 = (0.1 + (i * 0.13) % 0.5).toFixed(2);
        const delay2 = (0.2 + (i * 0.17) % 0.5).toFixed(2);
        const delay3 = (0.3 + (i * 0.23) % 0.5).toFixed(2);
        const delay4 = (0.4 + (i * 0.29) % 0.5).toFixed(2);
        const dur1 = (0.5 + (i * 0.07) % 0.4).toFixed(2);
        const dur2 = (0.5 + (i * 0.11) % 0.4).toFixed(2);
        const dur3 = (0.5 + (i * 0.13) % 0.4).toFixed(2);
        const dur4 = (0.5 + (i * 0.17) % 0.4).toFixed(2);
        EQ_PREVIEWS[i] = `<div class="eq-preview-box style${styleNum}">
            <div class="eq-preview-bar" style="animation-delay: -${delay1}s; animation-duration: ${dur1}s;"></div>
            <div class="eq-preview-bar" style="animation-delay: -${delay2}s; animation-duration: ${dur2}s;"></div>
            <div class="eq-preview-bar" style="animation-delay: -${delay3}s; animation-duration: ${dur3}s;"></div>
            <div class="eq-preview-bar" style="animation-delay: -${delay4}s; animation-duration: ${dur4}s;"></div>
        </div>`;
    }
    buildSelectorGrid("eq-visualizer-grid", EQ_PATTERNS, (v) => {
        if (!requireDevice()) return;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_visualization) {
            window.pywebview.api.set_visualization(v).then(res => {
                showToast(res ? "EQ pattern applied" : "Failed to apply EQ", res ? "success" : "error", "🔵 Bluetooth");
            });
        }
    }, -1, EQ_PREVIEWS);

    // 2.b — Ambient color, now a channel selection.
    const applyAmbientBtn = document.getElementById("apply-ambient-btn");
    if (applyAmbientBtn) {
        applyAmbientBtn.addEventListener("click", () => {
            if (!requireDevice()) return;
            const color = document.getElementById("ambient-color-input")?.value || "#00ffcc";
            const brightness = parseInt(document.getElementById("ambient-brightness")?.value) || 80;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.set_solid_light) {
                window.pywebview.api.set_solid_light(color, brightness).then(res => {
                    showToast(res ? "Ambient color applied" : "Failed to apply ambient", res ? "success" : "error", "🔵 Bluetooth");
                });
            }
        });
    }
    
    // Toast notifications
    function showToast(message, type = "success", transport = null) {
        const toast = document.getElementById("toast");
        toast.className = `toast ${type} show`;
        const transportSuffix = transport
            ? `<span class="toast-transport">${transport}</span>`
            : '';
        toast.innerHTML = message + transportSuffix;
        
        setTimeout(() => {
            toast.classList.remove("show");
        }, 3000);
    }
    
    // ── 4. FREE-FORM DRAG AND DROP CANVAS COORDINATOR ──
    let discoveredDevices = [];
    let assignedSlots = {}; // mac -> { x, y, width, height, size, name }
    
    const arrangerCanvas = document.getElementById("arranger-canvas");

    // Physical sizes specifications mapped to CSS dimensions (pixels)
    function getDeviceDimensions(name) {
        const lowerName = (name || "").toLowerCase();
        if (lowerName.includes("tivoo-max") || lowerName.includes("tivoo max")) {
            return { width: 160, height: 140, size: 16, image: "assets/tivoo_max.png" };
        }
        if (lowerName.includes("timoo")) {
            return { width: 80, height: 80, size: 16, image: "assets/timoo.png" };
        }
        if (lowerName.includes("ditoo")) {
            return { width: 90, height: 90, size: 16, image: "assets/ditoo.png" };
        }
        if (lowerName.includes("timebox") || lowerName.includes("evo")) {
            return { width: 100, height: 100, size: 16, image: "assets/timebox.png" };
        }
        if (lowerName.includes("pixoo") && lowerName.includes("64")) {
            return { width: 260, height: 260, size: 64, image: "assets/pixoo.png" };
        }
        if (lowerName.includes("pixoo")) {
            return { width: 200, height: 200, size: 16, image: "assets/pixoo.png" };
        }
        return { width: 100, height: 100, size: 16, image: "assets/pixoo.png" }; // default fallback
    }

    function syncArrangerToPython() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.update_wall_slots(JSON.stringify(assignedSlots));
        }
        updateSyncTargetList();
    }

    // Deterministic accent color per device, so devices are distinguished by
    // color (Kare: meaningful color-coding) instead of verbose text labels.
    function deviceColor(key) {
        let h = 0;
        const s = String(key || "");
        for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
        return `hsl(${h % 360}, 70%, 55%)`;
    }

    function renderArrangerCanvas() {
        // Clear workspace
        arrangerCanvas.innerHTML = "";

        Object.keys(assignedSlots).forEach(mac => {
            const slot = assignedSlots[mac];
            // Drop stale/placeholder slots (e.g. "AA:BB:CC:DD:EE:FF" -> null)
            // that otherwise render as an "undefined" device on an empty canvas.
            if (!slot || !slot.name || !mac || mac === "undefined") {
                delete assignedSlots[mac];
                return;
            }
            const node = document.createElement("div");
            node.className = "arranger-node";
            node.style.left = `${slot.x}px`;
            node.style.top = `${slot.y}px`;
            node.style.width = `${slot.width}px`;
            node.style.height = `${slot.height}px`;
            
            // Declutter (3.b): show the device mockup (with its preview in the
            // screen region when available) and identify it by an accent color
            // rather than on-canvas name/MAC text. Full name lives in the tooltip.
            const accent = deviceColor(mac);
            node.style.borderColor = accent;
            node.style.setProperty("--node-accent", accent);
            node.title = `${slot.name} — ${mac}`;
            // 3.c: render a uniform FRONT-FACING schematic screen (the body is
            // the node itself, accent-tinted) so the preview always aligns —
            // the product photos are inconsistently angled (ditoo/timoo/timebox)
            // which broke the in-screen preview.
            const previewInner = slot.preview
                ? `<img src="${slot.preview}" class="arranger-node-preview" alt="">`
                : "";
            node.innerHTML = `
                <span class="arranger-node-chip" style="background:${accent}"></span>
                <div class="arranger-node-screen">${previewInner}</div>
                <div class="arranger-node-remove" data-mac="${mac}">×</div>
            `;
            
            // Absolute positioning dragging math handlers
            let isDragging = false;
            let startX, startY;
            let startLeft, startTop;
            
            node.addEventListener("mousedown", (e) => {
                if (e.target.classList.contains("arranger-node-remove")) {
                    const macToRemove = e.target.getAttribute("data-mac");
                    delete assignedSlots[macToRemove];
                    renderArrangerCanvas();
                    syncArrangerToPython();
                    e.stopPropagation();
                    return;
                }
                
                isDragging = true;
                node.classList.add("dragging");
                
                startX = e.clientX;
                startY = e.clientY;
                startLeft = parseInt(node.style.left) || 0;
                startTop = parseInt(node.style.top) || 0;
                
                e.preventDefault();
            });
            
            document.addEventListener("mousemove", (e) => {
                if (!isDragging) return;
                
                const deltaX = e.clientX - startX;
                const deltaY = e.clientY - startY;
                
                let newLeft = startLeft + deltaX;
                let newTop = startTop + deltaY;
                
                // Keep inside arranger boundary limits
                const maxLeft = arrangerCanvas.clientWidth - node.clientWidth;
                const maxTop = arrangerCanvas.clientHeight - node.clientHeight;
                
                newLeft = Math.max(0, Math.min(newLeft, maxLeft));
                newTop = Math.max(0, Math.min(newTop, maxTop));
                
                node.style.left = `${newLeft}px`;
                node.style.top = `${newTop}px`;
                
                // Update slots position cache
                assignedSlots[mac].x = newLeft;
                assignedSlots[mac].y = newTop;
            });
            
            document.addEventListener("mouseup", () => {
                if (isDragging) {
                    isDragging = false;
                    node.classList.remove("dragging");
                    syncArrangerToPython();
                }
            });
            
            arrangerCanvas.appendChild(node);
        });
    }

    // Add arranged Screen button click
    const addArrangerBtn = document.getElementById("add-arranger-screen-btn");
    if (addArrangerBtn) {
        addArrangerBtn.addEventListener("click", () => {
            if (discoveredDevices.length === 0) {
                showToast("Please scan Bluetooth devices first under Settings tab!", "error");
                return;
            }
            
            // Show assignments dropdown options prompt
            const options = discoveredDevices.map(d => `<option value="${d.address}">${d.name} (${d.address})</option>`).join("");
            
            const popup = document.createElement("div");
            popup.style.position = "fixed";
            popup.style.top = "50%";
            popup.style.left = "50%";
            popup.style.transform = "translate(-50%, -50%)";
            popup.style.background = "var(--card-bg)";
            popup.style.border = "1px solid var(--border-color)";
            popup.style.borderRadius = "16px";
            popup.style.padding = "25px";
            popup.style.boxShadow = "0 10px 40px rgba(0,0,0,0.25)";
            popup.style.zIndex = "2000";
            popup.style.minWidth = "320px";
            popup.style.backdropFilter = "blur(15px)";
            
            popup.innerHTML = `
                <h3 style="font-family: var(--font-display); font-size:16px; margin-bottom:15px; color: var(--text-main);">Add Screen to Arranger</h3>
                <select id="canvas-add-select" class="custom-select" style="width:100%; margin-bottom:15px;">
                    ${options}
                </select>
                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button id="canvas-add-cancel" class="glow-btn compact" style="background:rgba(130,131,138,0.1); border: 1px solid var(--border-color); color: var(--text-main); box-shadow:none;">Cancel</button>
                    <button id="canvas-add-confirm" class="glow-btn compact" style="background: var(--primary); border: 1px solid var(--primary); color:#fff; box-shadow:none;">Add Node</button>
                </div>
            `;
            
            document.body.appendChild(popup);
            
            document.getElementById("canvas-add-cancel").addEventListener("click", () => {
                popup.remove();
            });
            
            document.getElementById("canvas-add-confirm").addEventListener("click", () => {
                const selectEl = document.getElementById("canvas-add-select");
                const addr = selectEl ? selectEl.value : "";
                popup.remove();
                
                if (!addr) {
                    showToast("No valid device selected!", "error");
                    return;
                }
                
                if (assignedSlots[addr]) {
                    showToast("Device already placed on canvas!", "error");
                    return;
                }
                
                const dev = discoveredDevices.find(d => d.address === addr);
                const devName = dev ? dev.name : "Divoom Screen";
                const dims = getDeviceDimensions(devName);
                
                // Center node on placement
                const placementX = Math.round((arrangerCanvas.clientWidth - dims.width) / 2);
                const placementY = Math.round((arrangerCanvas.clientHeight - dims.height) / 2);
                
                assignedSlots[addr] = {
                    x: placementX,
                    y: placementY,
                    width: dims.width,
                    height: dims.height,
                    size: dims.size,
                    name: devName,
                    image: dims.image
                };
                
                renderArrangerCanvas();
                syncArrangerToPython();
                showToast("Device node added to arranger", "success");
            });
        });
    }

    // Clear Canvas
    const clearArrangerBtn = document.getElementById("clear-arranger-btn");
    if (clearArrangerBtn) {
        clearArrangerBtn.addEventListener("click", () => {
            assignedSlots = {};
            renderArrangerCanvas();
            syncArrangerToPython();
            showToast("Arranger canvas cleared", "success");
        });
    }
    
    // ── 5. BLE CONNECTION HELPER & SELECTOR POPULATION ──
    function connectDevice(name, address) {
        showToast(`Connecting to ${name}...`, "success");
        const statusDot = document.getElementById("global-status-dot");
        const statusText = document.getElementById("global-status-text");
        
        if (statusDot) {
            statusDot.className = "transport-dot connecting";
            statusDot.removeAttribute("style");
        }
        if (statusText) statusText.textContent = "Connecting…";
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.connect_single_device(address)
                .then(res => {
                    if (res) {
                        appConnected = true;
                        let typeClass = "ble";
                        let transportLabel = "🔵 Bluetooth";
                        if (address === "MatrixWall") {
                            typeClass = "wall";
                            transportLabel = "🧱 Matrix Wall";
                        } else if (address.startsWith("LAN:")) {
                            typeClass = "lan";
                            transportLabel = "🟢 Local Network";
                        }
                        showToast(`Successfully connected to ${name}!`, "success", transportLabel);
                        if (statusDot) {
                            statusDot.className = `transport-dot active ${typeClass}`;
                            statusDot.removeAttribute("style");
                        }
                        if (statusText) statusText.textContent = "Connected";
                        
                        document.getElementById("banner-device-name").textContent = name;
                        document.getElementById("banner-device-mac").textContent = address;
                        
                        const dims = getDeviceDimensions(name);
                        document.getElementById("banner-device-image").src = dims.image;
                        document.getElementById("banner-device-res").textContent = `${dims.size}x${dims.size}`;
                        
                        const isSpeaker = name.toLowerCase().includes("timoo") || name.toLowerCase().includes("ditoo");
                        document.getElementById("banner-device-speaker").textContent = isSpeaker ? "Yes (Built-in)" : "No";
                        
                        const sidebarSelect = document.getElementById("sidebar-device-select");
                        if (sidebarSelect) sidebarSelect.value = address;
                        
                        updateSyncTargetList();
                    } else {
                        appConnected = false;
                        showToast(`Failed to connect to ${name}`, "error");
                        if (statusDot) {
                            statusDot.className = "transport-dot inactive";
                            statusDot.removeAttribute("style");
                        }
                        if (statusText) statusText.textContent = "Disconnected";
                        document.getElementById("banner-device-name").textContent = "None";
                        document.getElementById("banner-device-mac").textContent = "None";
                        updateSyncTargetList();
                    }
                });
        }
    }

    let registeredLanDevices = [];

    function populateDeviceSelectors(devices) {
        const deviceListUl = document.getElementById("device-list");
        if (deviceListUl) {
            deviceListUl.innerHTML = "";
            if (devices.length === 0) {
                deviceListUl.innerHTML = `<li class="empty-list">No BLE screens found.</li>`;
            } else {
                devices.forEach(d => {
                    const li = document.createElement("li");
                    const color = deviceColor(d.address);
                    li.innerHTML = `
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span class="device-accent-dot" style="background:${color}; box-shadow:0 0 6px ${color};"></span>
                            <span>${d.name}</span>
                        </div>
                        <span class="device-mac">${d.address}</span>
                    `;
                    li.addEventListener("click", () => {
                        connectDevice(d.name, d.address);
                    });
                    deviceListUl.appendChild(li);
                });
            }
        }
        updateDeviceSelectorDropdown();
    }

    function updateDeviceSelectorDropdown() {
        const sel = document.getElementById("sidebar-device-select");
        if (!sel) return;
        
        sel.innerHTML = '<option value="">Select Screen...</option>';
        
        const currentMac = document.getElementById("banner-device-mac")?.textContent || "";
        
        // Populate BLE devices
        discoveredDevices.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.address;
            opt.textContent = `🔵 Bluetooth: ${d.name} (${d.address})`;
            if (currentMac === d.address) opt.selected = true;
            sel.appendChild(opt);
        });
        
        // Populate Wi-Fi devices
        registeredLanDevices.forEach(d => {
            const opt = document.createElement("option");
            opt.value = `LAN:${d.ip}`;
            opt.textContent = `🟢 Local Network: ${d.ip}`;
            if (currentMac === `LAN:${d.ip}`) opt.selected = true;
            sel.appendChild(opt);
        });
        
        // Append Matrix Wall Grid if slots exist
        if (Object.keys(assignedSlots || {}).length > 0) {
            const opt = document.createElement("option");
            opt.value = "MatrixWall";
            opt.textContent = "🧱 Matrix Wall Grid";
            if (currentMac === "MatrixWall") opt.selected = true;
            sel.appendChild(opt);
        }
    }

    const sidebarSelect = document.getElementById("sidebar-device-select");
    if (sidebarSelect) {
        sidebarSelect.addEventListener("change", (e) => {
            const addr = e.target.value;
            if (!addr) return;
            
            if (addr === "MatrixWall") {
                connectDevice("Matrix Wall Grid", "MatrixWall");
            } else if (addr.startsWith("LAN:")) {
                const ip = addr.split("LAN:")[1];
                connectDevice(`Local Network: ${ip}`, addr);
            } else {
                const dev = discoveredDevices.find(d => d.address === addr);
                const name = dev ? dev.name : "Bluetooth Device";
                connectDevice(name, addr);
            }
        });
    }

    const scanBtn = document.getElementById("scan-btn");
    const scanSpinner = document.getElementById("scan-spinner");
    const deviceListUl = document.getElementById("device-list");

    // Persist scan timeout / device limit on change so they survive across
    // sessions even when the user adjusts them without running a scan.
    ["scan-timeout", "scan-limit"].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("change", () => {
                const t = parseInt(document.getElementById("scan-timeout")?.value) || 15;
                const l = parseInt(document.getElementById("scan-limit")?.value);
                if (window.pywebview && window.pywebview.api && window.pywebview.api.save_scan_settings) {
                    window.pywebview.api.save_scan_settings(t, isNaN(l) ? 0 : l);
                }
            });
        }
    });

    function runBleScan() {
        const timeout = parseInt(document.getElementById("scan-timeout")?.value) || 15;
        const limit = parseInt(document.getElementById("scan-limit")?.value) || 0;

        if (scanSpinner) scanSpinner.style.display = "inline-block";
        if (scanBtn) scanBtn.disabled = true;
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.scan_devices_with_config(timeout, limit)
                .then(devicesJson => {
                    if (scanSpinner) scanSpinner.style.display = "none";
                    if (scanBtn) scanBtn.disabled = false;
                    
                    const devices = JSON.parse(devicesJson);
                    discoveredDevices = devices;
                    populateDeviceSelectors(devices);
                    showToast(`Discovered ${devices.length} screens!`, "success");
                    renderArrangerCanvas(); 
                });
        } else {
            if (scanSpinner) scanSpinner.style.display = "none";
            if (scanBtn) scanBtn.disabled = false;
            showToast("Web interface API unavailable.", "error");
        }
    }

    if (scanBtn) {
        scanBtn.addEventListener("click", runBleScan);
    }
    
    // Light Controls Apply
    const applyLightBtn = document.getElementById("apply-light-btn");
    if (applyLightBtn) {
        applyLightBtn.addEventListener("click", () => {
            const brightness = brightnessSlider ? parseInt(brightnessSlider.value) : 100;
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_solid_light(selectedColor, brightness)
                    .then(res => {
                        if (res) showToast("Ambient light applied", "success", "🔵 Bluetooth");
                        else showToast("Failed to apply ambient light", "error");
                    });
            }
        });
    }
    
    // Split and Push to Wall
    const applyWallArtBtn = document.getElementById("apply-wall-art");
    if (applyWallArtBtn) {
        applyWallArtBtn.addEventListener("click", () => {
            const path = document.getElementById("file-path-input").value.trim();
            const cellSize = 16; // default size
            
            if (!path) {
                showToast("Please provide a local file path!", "error");
                return;
            }
            
            if (Object.keys(assignedSlots).length === 0) {
                showToast("Please arrange at least one device on the canvas first!", "error");
                return;
            }
            
            showToast("Splitting image and syncing wall...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.apply_wall_image(path, cellSize)
                    .then(res => {
                        if (res) showToast("Synchronized display wall", "success", "🔵 Bluetooth");
                        else showToast("Failed to split and push wall image", "error");
                    });
            }
        });
    }

    // Dynamic Live Preview for Split & Sync local GIF/PNG path input
    const filePathInput = document.getElementById("file-path-input");
    const filePreviewContainer = document.getElementById("file-preview-container");
    const filePreviewImg = document.getElementById("file-preview-img");

    if (filePathInput && filePreviewContainer && filePreviewImg) {
        const updatePreview = () => {
            const val = filePathInput.value.trim();
            if (val) {
                let src = val;
                if (!val.startsWith("http://") && !val.startsWith("https://") && !val.startsWith("file://") && !val.startsWith("data:")) {
                    if (val.startsWith("/")) {
                        src = "file://" + val;
                    } else {
                        src = "file:///" + val.replace(/\\/g, "/");
                    }
                }
                filePreviewImg.src = src;
                filePreviewContainer.style.display = "flex";
            } else {
                filePreviewImg.src = "";
                filePreviewContainer.style.display = "none";
            }
        };

        filePathInput.addEventListener("input", updatePreview);
        filePathInput.addEventListener("change", updatePreview);
    }
    
    // ── 6. CLOUD GALLERY WITH ANIMATED COVER PREVIEWS ──
    const galleryContainer = document.getElementById("gallery-container");
    let loadedArtworks = [];
    let selectedArtworkIndex = null;
    
    const loadGalleryBtn = document.getElementById("load-gallery-btn");
    if (loadGalleryBtn) {
        loadGalleryBtn.addEventListener("click", () => {
            const classify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">Fetching public community gallery...</div>`;
            
            let targetSize = 16;
            const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
            if (bannerResText.includes("64")) {
                targetSize = 64;
            } else if (bannerResText.includes("32")) {
                targetSize = 32;
            }
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.fetch_gallery(classify, targetSize)
                    .then(artworksJson => {
                        const artworks = JSON.parse(artworksJson);
                        if (artworks.error) {
                            showToast(artworks.error, "error");
                            if (galleryContainer) {
                                galleryContainer.innerHTML = `<div class="empty-list" style="color:#ef4444; padding:20px; font-weight:600; text-align:center;">⚠️ ${artworks.error}</div>`;
                            }
                            return;
                        }
                        
                        loadedArtworks = artworks;
                        selectedArtworkIndex = null;
                        renderGallery(artworks);
                        showToast("Gallery loaded from cache", "success", "🟡 Divoom Cloud");
                    });
            }
        });
    }
    
    // Batch Sync Monthly Best to Grid Wall
    const batchSyncBtn = document.getElementById("batch-sync-btn");
    if (batchSyncBtn) {
        batchSyncBtn.addEventListener("click", () => {
            if (selectedArtworkIndex === null) {
                showToast("Please select an artwork from the gallery list first!", "error");
                return;
            }
            
            const artwork = loadedArtworks[selectedArtworkIndex];
            showToast(`Downloading and syncing '${artwork.name}'...`, "success");
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.batch_sync_artwork(JSON.stringify(artwork))
                    .then(res => {
                        if (res) showToast(`'${artwork.name}' synced`, "success", "🔵 Bluetooth");
                        else showToast("Failed to batch sync artwork", "error");
                    });
            }
        });
    }

    // Live Widgets (macOS Music & Stocks Ticker)
    const musicSyncToggle = document.getElementById("music-sync-toggle");
    if (musicSyncToggle) {
        musicSyncToggle.addEventListener("change", (e) => {
            const enable = e.target.checked;
            const trackerStatus = document.getElementById("music-track-status");
            if (enable) {
                trackerStatus.classList.add("active");
                showToast("Enabled macOS Music track listener thread", "success");
            } else {
                trackerStatus.classList.remove("active");
                document.getElementById("music-track-name").textContent = "No Music Playing";
                document.getElementById("music-artist-name").textContent = "Spotify / Apple Music";
                showToast("Music synchronization stopped", "success");
            }

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.toggle_music_sync(enable);
            }
        });
    }

    // Poll live track info from backend every 3 seconds to update the UI
    setInterval(() => {
        if (musicSyncToggle && musicSyncToggle.checked && window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_current_track_info()
                .then(infoJson => {
                    if (infoJson) {
                        const info = JSON.parse(infoJson);
                        if (info && info.track) {
                            document.getElementById("music-track-name").textContent = info.track;
                            document.getElementById("music-artist-name").textContent = `${info.artist} (${info.source})`;
                            if (info.artwork_url) {
                                document.getElementById("music-cover-img").src = info.artwork_url;
                            }
                            // On-device preview: the exact downsampled frame (5.d).
                            const devPrev = document.getElementById("music-device-preview");
                            if (devPrev && info.preview) {
                                devPrev.src = info.preview;
                                devPrev.style.display = "inline-block";
                            }
                        }
                    }
                });
        }
    }, 3000);

    // Stock price submit
    const applyStockBtn = document.getElementById("apply-stock-btn");
    if (applyStockBtn) {
        applyStockBtn.addEventListener("click", () => {
            const symbol = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
            if (!symbol) {
                showToast("Please enter a ticker symbol!", "error");
                return;
            }

            showToast(`Fetching Yahoo price data for ${symbol}...`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.apply_stock_ticker(symbol)
                    .then(resJson => {
                        if (resJson) {
                            const res = JSON.parse(resJson);
                            if (res.success) {
                                showToast(`Displaying ${symbol} price frame!`, "success", "🔴 Public Cloud");
                                const priceMock = document.querySelector(".ticker-price-mock");
                                const arrowMock = document.querySelector(".ticker-arrow-mock");
                                const nameMock = document.querySelector(".ticker-name-mock");

                                if (nameMock) nameMock.textContent = symbol;
                                if (priceMock) priceMock.textContent = `$${res.price}`;
                                if (arrowMock) {
                                    arrowMock.textContent = res.change >= 0 ? "▲" : "▼";
                                    arrowMock.style.color = res.change >= 0 ? "var(--secondary)" : "red";
                                }
                                showTickerDevicePreview(res.preview);
                            } else {
                                // 5.a: surface the real reason (e.g. "No device connected").
                                showToast(res.error || `Failed to display ${symbol}`, "error");
                                showTickerDevicePreview(res.preview);
                            }
                        } else {
                            showToast("API return error", "error");
                        }
                    });
            }
        });
    }

    // Area 7 — System Monitor widget (CPU/RAM/battery → device).
    function refreshSysmonPreview() {
        if (!(window.pywebview && window.pywebview.api && window.pywebview.api.get_system_stats_preview)) return;
        window.pywebview.api.get_system_stats_preview(0).then(json => {
            try {
                const r = JSON.parse(json);
                if (!r.ok) return;
                const s = r.stats || {};
                const cpu = document.getElementById("sysmon-cpu");
                const mem = document.getElementById("sysmon-mem");
                const bat = document.getElementById("sysmon-bat");
                if (cpu) cpu.textContent = `${s.cpu}%`;
                if (mem) mem.textContent = `${s.mem}%`;
                if (bat) bat.textContent = s.battery != null ? `${s.battery}%` : "n/a";
                const img = document.getElementById("sysmon-device-preview");
                if (img && r.preview) { img.src = r.preview; img.style.display = "inline-block"; }
            } catch (e) { /* ignore */ }
        });
    }
    const sysmonDisplayBtn = document.getElementById("sysmon-display-btn");
    if (sysmonDisplayBtn) {
        sysmonDisplayBtn.addEventListener("click", () => {
            if (!(window.pywebview && window.pywebview.api && window.pywebview.api.apply_system_stats)) return;
            window.pywebview.api.apply_system_stats().then(json => {
                try {
                    const r = JSON.parse(json);
                    const img = document.getElementById("sysmon-device-preview");
                    if (img && r.preview) { img.src = r.preview; img.style.display = "inline-block"; }
                    showToast(r.success ? "System monitor on device" : (r.error || "Failed"), r.success ? "success" : "error", "🔵 Bluetooth");
                } catch (e) { showToast("Failed", "error"); }
            });
        });
    }
    let sysmonTimer = null;
    const sysmonLive = document.getElementById("sysmon-live");
    if (sysmonLive) {
        sysmonLive.addEventListener("change", (e) => {
            if (e.target.checked) {
                refreshSysmonPreview();
                sysmonTimer = setInterval(() => {
                    refreshSysmonPreview();
                    if (window.pywebview && window.pywebview.api && window.pywebview.api.apply_system_stats) {
                        window.pywebview.api.apply_system_stats();
                    }
                }, 5000);
            } else if (sysmonTimer) {
                clearInterval(sysmonTimer);
                sysmonTimer = null;
            }
        });
    }
    setTimeout(refreshSysmonPreview, 1800);

    function showTickerDevicePreview(dataUrl) {
        const img = document.getElementById("ticker-device-preview");
        if (img && dataUrl) {
            img.src = dataUrl;
            img.style.display = "inline-block";
        }
    }

    // 5.e — multiple saved tickers (persisted, seeded from macOS Stocks).
    function renderTickers(symbols) {
        const el = document.getElementById("tickers-list");
        if (!el) return;
        el.innerHTML = "";
        (symbols || []).forEach(sym => {
            const chip = document.createElement("span");
            chip.className = "ticker-chip";
            const label = document.createElement("button");
            label.className = "ticker-chip-label";
            label.textContent = sym;
            label.title = `Display ${sym}`;
            label.addEventListener("click", () => {
                const input = document.getElementById("stock-symbol-input");
                if (input) input.value = sym;
                document.getElementById("apply-stock-btn")?.click();
            });
            const rm = document.createElement("button");
            rm.className = "ticker-chip-remove";
            rm.textContent = "×";
            rm.title = `Remove ${sym}`;
            rm.addEventListener("click", () => removeTicker(sym));
            chip.append(label, rm);
            el.appendChild(chip);
        });
    }

    let savedTickers = [];
    function loadTickers() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_tickers) {
            window.pywebview.api.get_tickers().then(json => {
                try { savedTickers = JSON.parse(json) || []; renderTickers(savedTickers); } catch (e) {}
            });
        }
    }
    function persistTickers() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_tickers) {
            window.pywebview.api.set_tickers(JSON.stringify(savedTickers));
        }
        renderTickers(savedTickers);
    }
    function removeTicker(sym) {
        savedTickers = savedTickers.filter(s => s !== sym);
        persistTickers();
    }
    const addTickerBtn = document.getElementById("add-ticker-btn");
    if (addTickerBtn) {
        addTickerBtn.addEventListener("click", () => {
            const sym = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
            if (!sym) { showToast("Enter a ticker symbol first.", "error"); return; }
            if (!savedTickers.includes(sym)) {
                savedTickers.push(sym);
                persistTickers();
                showToast(`Saved ${sym}`, "success");
            }
        });
    }
    setTimeout(loadTickers, 1500);

    // Tab 5: Credentials Settings tab
    const saveCredsBtn = document.getElementById("save-creds-btn");
    if (saveCredsBtn) {
        saveCredsBtn.addEventListener("click", () => {
            const email = document.getElementById("settings-email").value.trim();
            const pwd = document.getElementById("settings-password").value.trim();

            if (!email || !pwd) {
                showToast("Email and Password are required!", "error");
                return;
            }

            showToast("Saving cloud credentials...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_credentials(email, pwd)
                    .then(res => {
                        if (res) {
                            showToast("Credentials configured & login cache generated!", "success");
                            const statusBox = document.getElementById("divoom-cloud-status-box");
                            if (statusBox) {
                                statusBox.style.display = "flex";
                                statusBox.style.background = "rgba(34, 197, 94, 0.15)";
                                statusBox.style.border = "1px solid rgba(34, 197, 94, 0.3)";
                                statusBox.style.color = "#22c55e";
                                statusBox.innerHTML = `<span>🟢 Connected as <b>${email}</b></span>`;
                            }
                        } else {
                            showToast("Authentication failed. Please verify credentials.", "error");
                            const statusBox = document.getElementById("divoom-cloud-status-box");
                            if (statusBox) {
                                statusBox.style.display = "flex";
                                statusBox.style.background = "rgba(239, 68, 68, 0.15)";
                                statusBox.style.border = "1px solid rgba(239, 68, 68, 0.3)";
                                statusBox.style.color = "#ef4444";
                                statusBox.innerHTML = `<span>🔴 Not connected. Save your credentials to log in.</span>`;
                            }
                        }
                    });
            }
        });
    }

    // Load initial credentials & configurations from python backend on mount
    setTimeout(() => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_config()
                .then(configJson => {
                    if (configJson) {
                        const conf = JSON.parse(configJson);
                        if (conf.email && document.getElementById("settings-email")) {
                            document.getElementById("settings-email").value = conf.email;
                        }
                        if (conf.timeout != null && document.getElementById("scan-timeout")) {
                            document.getElementById("scan-timeout").value = conf.timeout;
                        }
                        // Use an explicit null check so a saved limit of 0
                        // ("unlimited") is restored instead of being dropped as falsy.
                        if (conf.limit != null && document.getElementById("scan-limit")) {
                            document.getElementById("scan-limit").value = conf.limit;
                        }
                        if (conf.slots) {
                            assignedSlots = conf.slots;
                            renderArrangerCanvas();
                        }
                        if (conf.devices && conf.devices.length > 0) {
                            discoveredDevices = conf.devices;
                            populateDeviceSelectors(discoveredDevices);
                            renderArrangerCanvas();
                        }
                        
                        if (conf.last_connected_device) {
                            const addr = conf.last_connected_device;
                            let name = "Divoom Screen";
                            if (addr === "MatrixWall") {
                                name = "Matrix Wall Grid";
                            } else if (addr.startsWith("LAN:")) {
                                const ip = addr.split("LAN:")[1];
                                name = `Wi-Fi: ${ip}`;
                            } else {
                                const dev = discoveredDevices.find(d => d.address === addr);
                                if (dev) name = dev.name;
                            }
                            setTimeout(() => {
                                connectDevice(name, addr);
                            }, 500);
                        }

                        if (conf.last_detected_count && conf.last_detected_count > 0) {
                            setTimeout(() => {
                                showToast("Resuming session: Auto-scanning screens...", "success");
                                runBleScan();
                            }, 1000);
                        }
                        
                        // Cloud Connection Status Indicator Card
                        const statusBox = document.getElementById("divoom-cloud-status-box");
                        if (statusBox) {
                            if (conf.cloud_connected) {
                                statusBox.style.display = "flex";
                                statusBox.style.background = "rgba(34, 197, 94, 0.15)";
                                statusBox.style.border = "1px solid rgba(34, 197, 94, 0.3)";
                                statusBox.style.color = "#22c55e";
                                statusBox.innerHTML = `<span>🟢 Connected as <b>${conf.cloud_email || conf.email}</b></span>`;
                            } else {
                                statusBox.style.display = "flex";
                                statusBox.style.background = "rgba(239, 68, 68, 0.15)";
                                statusBox.style.border = "1px solid rgba(239, 68, 68, 0.3)";
                                statusBox.style.color = "#ef4444";
                                statusBox.innerHTML = `<span>🔴 Not connected. Save your credentials to log in.</span>`;
                            }
                        }
                    }
                });
            
            // Load preset listings
            window.pywebview.api.load_preset_names()
                .then(namesJson => {
                    if (namesJson) {
                        const names = JSON.parse(namesJson);
                        const select = document.getElementById("presets-select");
                        if (select) {
                            select.innerHTML = '<option value="">Load Preset...</option>';
                            names.forEach(name => {
                                const opt = document.createElement("option");
                                opt.value = name;
                                opt.textContent = name;
                                select.appendChild(opt);
                            });
                        }
                    }
                });
        }
    }, 1000);

    // Preset dropdown select event
    const presetsSelect = document.getElementById("presets-select");
    if (presetsSelect) {
        presetsSelect.addEventListener("change", (e) => {
            const name = e.target.value;
            if (!name) return;

            showToast(`Loading layout preset '${name}'...`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.load_preset_by_name(name)
                    .then(slotsJson => {
                        if (slotsJson) {
                            assignedSlots = JSON.parse(slotsJson);
                            renderArrangerCanvas();
                            showToast(`Layout preset '${name}' applied!`, "success");
                        } else {
                            showToast("Failed to load layout slots from file", "error");
                        }
                    });
            }
        });
    }

    // Save Preset button click
    const savePresetBtn = document.getElementById("save-preset-btn");
    if (savePresetBtn) {
        savePresetBtn.addEventListener("click", () => {
            if (Object.keys(assignedSlots).length === 0) {
                showToast("No arranged screens to save!", "error");
                return;
            }

            const name = prompt("Enter a unique name for this screen wall layout preset:", "My Custom Wall");
            if (!name) return;

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_preset(name, JSON.stringify(assignedSlots))
                    .then(res => {
                        if (res) {
                            showToast(`Saved wall layout preset '${name}'`, "success");
                            // Refresh selector options
                            window.pywebview.api.load_preset_names()
                                .then(namesJson => {
                                    if (namesJson) {
                                        const names = JSON.parse(namesJson);
                                        const select = document.getElementById("presets-select");
                                        if (select) {
                                            select.innerHTML = '<option value="">Load Preset...</option>';
                                            names.forEach(n => {
                                                const opt = document.createElement("option");
                                                opt.value = n;
                                                opt.textContent = n;
                                                select.appendChild(opt);
                                            });
                                        }
                                    }
                                });
                        } else {
                            showToast("Failed to save layout preset", "error");
                        }
                    });
            }
        });
    }

    // ── TRANSPORT STATUS POLLING (4-badge sidebar panel) ──────────────────
    function updateTransportPanel(status) {
        const transports = [
            { key: 'ble',      dotId: 'tr-ble-dot',   detailId: 'tr-ble-detail' },
            { key: 'lan',      dotId: 'tr-lan-dot',   detailId: 'tr-lan-detail' },
            { key: 'cloud',    dotId: 'tr-cloud-dot', detailId: 'tr-cloud-detail' },
            { key: 'external', dotId: 'tr-ext-dot',   detailId: 'tr-ext-detail' },
        ];
        transports.forEach(({ key, dotId, detailId }) => {
            const t = status[key];
            if (!t) return;
            const dot    = document.getElementById(dotId);
            const detail = document.getElementById(detailId);
            if (dot) {
                dot.className = `transport-dot ${t.available ? 'active' : 'inactive'}`;
            }
            if (detail && t.detail) {
                detail.textContent = t.detail;
            }
        });
    }

    function refreshTransportStatus() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_transport_status()
                .then(json => {
                    try { updateTransportPanel(JSON.parse(json)); } catch(e) {}
                })
                .catch(() => {});
        }
    }
    // Poll every 5 seconds
    setInterval(refreshTransportStatus, 5000);
    // Also fire once at startup after a short delay
    setTimeout(refreshTransportStatus, 1500);

    // ── Wi-Fi DEVICES MANAGER WIRING ──────────────────────────────────────
    function loadLanDevices() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_lan_devices()
                .then(json => {
                    try {
                        registeredLanDevices = JSON.parse(json);
                        renderLanDevicesList();
                        updateDeviceSelectorDropdown();
                    } catch(e) {
                        registeredLanDevices = [];
                    }
                });
        }
    }

    function renderLanDevicesList() {
        const ul = document.getElementById("lan-device-list");
        if (!ul) return;
        ul.innerHTML = "";
        if (registeredLanDevices.length === 0) {
            ul.innerHTML = '<li class="empty-list">No Wi-Fi screens registered.</li>';
            return;
        }
        registeredLanDevices.forEach(d => {
            const li = document.createElement("li");
            li.style.display = "flex";
            li.style.justifyContent = "space-between";
            li.style.alignItems = "center";
            li.innerHTML = `
                <span style="font-weight:600; cursor:pointer;">🟢 Local Network Device (${d.ip})</span>
                <button class="glow-btn compact" style="margin:0; background:rgba(255, 68, 68, 0.15); border-color:#ef4444; color:#ef4444;" data-ip="${d.ip}">Delete</button>
            `;
            li.querySelector("span").addEventListener("click", () => {
                connectDevice(`Local Network: ${d.ip}`, `LAN:${d.ip}`);
            });
            li.querySelector("button").addEventListener("click", (e) => {
                e.stopPropagation();
                const ip = e.target.getAttribute("data-ip");
                if (window.pywebview && window.pywebview.api) {
                    window.pywebview.api.delete_lan_device(ip)
                        .then(ok => {
                            if (ok) {
                                showToast("Deleted Wi-Fi device", "success");
                                loadLanDevices();
                            }
                        });
                }
            });
            ul.appendChild(li);
        });
    }

    const addLanBtn = document.getElementById("add-lan-btn");
    if (addLanBtn) {
        addLanBtn.addEventListener("click", () => {
            const ipInput = document.getElementById("lan-ip-input");
            const tokenInput = document.getElementById("lan-token-input");
            const probeResult = document.getElementById("lan-probe-result");
            
            const ip = (ipInput?.value || "").trim();
            const token = parseInt(tokenInput?.value || "0");
            if (!ip) { showToast("Enter an IP Address", "error"); return; }
            
            if (probeResult) { probeResult.textContent = "Connecting..."; probeResult.className = "lan-probe-result"; }
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.add_lan_device(ip, token)
                    .then(ok => {
                        if (ok) {
                            showToast(`Added Wi-Fi device: ${ip}`, "success");
                            if (probeResult) { probeResult.textContent = "Device registered successfully."; probeResult.className = "lan-probe-result success"; }
                            if (ipInput) ipInput.value = "";
                            if (tokenInput) tokenInput.value = "0";
                            loadLanDevices();
                        } else {
                            showToast("Failed to add Wi-Fi device", "error");
                            if (probeResult) { probeResult.textContent = "Could not register device."; probeResult.className = "lan-probe-result error"; }
                        }
                    });
            }
        });
    }

    // Load LAN config and devices on startup
    setTimeout(() => {
        loadLanDevices();
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_config()
                .then(() => {});
        }
    }, 1200);

    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".settings-tab-btn");
        if (btn) {
            const settingsTabButtons = document.querySelectorAll(".settings-tab-btn");
            const settingsTabContents = document.querySelectorAll(".settings-tab-content");
            
            settingsTabButtons.forEach(b => b.classList.remove("active"));
            settingsTabContents.forEach(t => t.classList.remove("active"));

            btn.classList.add("active");
            const targetSubTab = btn.getAttribute("data-settings-tab");
            const targetEl = document.getElementById(targetSubTab);
            if (targetEl) {
                targetEl.classList.add("active");
            }
        }
    });

    // ── 2D. DYNAMIC TARGET SCREENS LIST FOR MONTHLY BEST ──
    // 4.c — render the sync-target multi-select from backend candidates.
    function renderSyncTargets(candidates) {
        const el = document.getElementById("sync-targets-list");
        if (!el) return;
        if (!candidates || candidates.length === 0) {
            el.innerHTML = `<span class="empty-list">No devices — scan under Settings, or add a Wi-Fi screen.</span>`;
            return;
        }
        el.innerHTML = "";
        candidates.forEach(c => {
            const row = document.createElement("label");
            row.className = "target-row";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = c.address;
            cb.checked = !!c.selected;
            cb.addEventListener("change", persistSyncTargets);
            
            const color = deviceColor(c.address);
            const accent = document.createElement("span");
            accent.className = "device-accent-dot";
            accent.style.background = color;
            accent.style.boxShadow = `0 0 6px ${color}`;
            accent.style.marginRight = "6px";
            
            const name = document.createElement("span");
            name.className = "target-name";
            name.textContent = c.name;
            const addr = document.createElement("span");
            addr.className = "target-addr";
            addr.textContent = c.address;
            row.append(cb, accent, name, addr);
            el.appendChild(row);
        });
    }

    function persistSyncTargets() {
        const checked = Array.from(document.querySelectorAll("#sync-targets-list input:checked")).map(i => i.value);
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_sync_targets) {
            window.pywebview.api.set_sync_targets(JSON.stringify(checked));
        }
    }

    function updateSyncTargetList() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_sync_candidates) {
            window.pywebview.api.get_sync_candidates().then(json => {
                try { renderSyncTargets(JSON.parse(json)); } catch (e) { /* ignore */ }
            });
        }
    }

    const refreshTargetsBtn = document.getElementById("refresh-targets-btn");
    if (refreshTargetsBtn) refreshTargetsBtn.addEventListener("click", updateSyncTargetList);

    // 4.b — sync ALL loaded gallery items to every selected target at once.
    const syncAllBtn = document.getElementById("sync-all-btn");
    if (syncAllBtn) {
        syncAllBtn.addEventListener("click", () => {
            if (!loadedArtworks || loadedArtworks.length === 0) {
                showToast("Fetch the gallery first.", "error");
                return;
            }
            const fileIds = loadedArtworks.map(a => a.file_id).filter(Boolean);
            showToast(`Syncing ${fileIds.length} artworks to targets…`, "success");
            window.pywebview.api.sync_hot_channel(JSON.stringify(fileIds)).then(json => {
                try {
                    const r = JSON.parse(json);
                    if (r.ok) showToast(`Synced ${r.synced.length} artworks`, "success", "🔵 BLE");
                    else showToast(`Synced ${r.synced.length}, ${r.failed.length} failed`, "error");
                } catch (e) { showToast("Sync failed", "error"); }
            });
        });
    }

    // 4.d — load + save the automatic hot-channel schedule.
    function loadHotChannelSchedule() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_hot_channel_config) {
            window.pywebview.api.get_hot_channel_config().then(json => {
                try {
                    const cfg = JSON.parse(json);
                    const en = document.getElementById("hc-enabled");
                    const iv = document.getElementById("hc-interval");
                    const cl = document.getElementById("gallery-classify");
                    if (en) en.checked = !!cfg.enabled;
                    if (iv) iv.value = String(cfg.interval);
                    if (cl && cfg.classify != null) cl.value = String(cfg.classify);
                } catch (e) { /* ignore */ }
            });
        }
    }

    const hcSaveBtn = document.getElementById("hc-save-schedule-btn");
    if (hcSaveBtn) {
        hcSaveBtn.addEventListener("click", () => {
            const enabled = document.getElementById("hc-enabled")?.checked || false;
            const interval = parseInt(document.getElementById("hc-interval")?.value) || 3600;
            const classify = parseInt(document.getElementById("gallery-classify")?.value) || 18;
            window.pywebview.api.save_hot_channel_config(JSON.stringify({ enabled, interval, classify })).then(ok => {
                const st = document.getElementById("hc-schedule-status");
                if (st) st.textContent = ok ? (enabled ? "Saved — scheduled" : "Saved — disabled") : "Failed to save";
                showToast(ok ? "Schedule saved" : "Failed to save schedule", ok ? "success" : "error");
            });
        });
    }

    // Initial load of targets + schedule.
    setTimeout(() => {
        updateSyncTargetList();
        loadHotChannelSchedule();
    }, 1500);

    function renderGallery(artworks) {
        if (galleryContainer) galleryContainer.innerHTML = "";
        
        if (!artworks || artworks.length === 0) {
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">No gallery items found for classification.</div>`;
            return;
        }
        
        artworks.forEach((art, idx) => {
            const item = document.createElement("div");
            item.className = "gallery-item";
            
            const previewSrc = art.preview_url ? art.preview_url : "assets/pixoo.png";
            
            item.innerHTML = `
                <div class="gallery-item-preview-box">
                    <img src="${previewSrc}" class="gallery-item-preview" alt="${art.name}">
                </div>
                <div class="gallery-item-info">
                    <h5>${art.name}</h5>
                    <span>❤️ ${art.likes}</span>
                </div>
            `;
            
            item.addEventListener("click", () => {
                const items = galleryContainer.querySelectorAll(".gallery-item");
                items.forEach(it => it.classList.remove("active"));
                item.classList.add("active");
                selectedArtworkIndex = idx;
            });
            
            if (galleryContainer) galleryContainer.appendChild(item);
        });
    }

    window.onGalleryBackgroundFetched = function(classify, targetSize, b64Data) {
        try {
            const rawJson = atob(b64Data);
            const artworks = JSON.parse(rawJson);
            
            const currentClassify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            let currentTargetSize = 16;
            const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
            if (bannerResText.includes("64")) {
                currentTargetSize = 64;
            } else if (bannerResText.includes("32")) {
                currentTargetSize = 32;
            }
            
            if (currentClassify === classify && currentTargetSize === targetSize) {
                loadedArtworks = artworks;
                selectedArtworkIndex = null;
                renderGallery(artworks);
                showToast("Gallery updated with latest monthly best! 🟡", "success");
            }
        } catch (e) {
            console.error("Failed to process background gallery fetch:", e);
        }
    };

});

