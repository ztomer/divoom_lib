/* channels.js — Control Center channels layout and swatch elements */

document.addEventListener("DOMContentLoaded", () => {
    // ── 1. AMBIENT LIGHT SWATCHES ──
    const colorSwatches = document.querySelectorAll(".color-swatch");
    const customColorInput = document.getElementById("custom-color-input");
    
    colorSwatches.forEach(swatch => {
        swatch.addEventListener("click", () => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            swatch.classList.add("active");
            window.DivoomState.selectedColor = swatch.getAttribute("data-color");
        });
    });
    
    if (customColorInput) {
        customColorInput.addEventListener("input", (e) => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            window.DivoomState.selectedColor = e.target.value.replace("#", "");
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
    
    // ── 2. CHANNEL CARDS NAVIGATION ──
    const channelCards = document.querySelectorAll(".channel-card");
    const channelPanels = document.querySelectorAll(".channel-panel");

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
        if (channel === "design") {
            loadCustomArtCacheGrid();
        }
    }

    channelCards.forEach(card => {
        card.addEventListener("click", () => {
            channelCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            window.DivoomState.activeChannel = card.getAttribute("data-channel");
            showChannelPanel(window.DivoomState.activeChannel);
            // Ambient is a light mode applied via its own button, not a device
            // channel switch, so don't fire switch_channel for it.
            if (window.DivoomState.activeChannel === "ambient") return;
            if (!window.requireDevice()) return;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.switch_channel) {
                window.pywebview.api.switch_channel(window.DivoomState.activeChannel).then(res => {
                    if (res) window.showToast("Switched channel", "success", "🔵 BLE");
                    else window.showToast("Failed to switch channel", "error");
                });
            }
        });
    });

    // Selector-grid builder helper
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

    // ── 3. CLOCK FACES GRID ──
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
        if (!window.requireDevice()) return;
        const color = document.getElementById("clock-color-input")?.value || "#ffffff";
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_clock(style, color).then(res => {
                window.showToast(res ? "Clock style applied" : "Failed to apply clock", res ? "success" : "🔵 BLE");
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

    // ── 4. VJ EFFECTS GRID ──
    const VJ_EFFECTS = ["Sparkles", "Lava", "Vertical Rainbow", "Drops", "Rainbow Swirl",
        "CMY Fade", "Rainbow Lava", "Pastel Patterns", "CMY Wave", "Fire", "Countdown",
        "Pink/Blue Fade", "Rainbow Polygons", "Pink/Blue Wave", "Rainbow Cross", "Rainbow Shapes"]
        .map((name, i) => ({ value: i, name }));
        
    const VJ_PREVIEWS = {};
    for (let i = 0; i < 16; i++) {
        const vjIndex = i + 2; // maps python 0-15 to VJ assets index 2-17
        const assetNum = vjIndex > 16 ? 16 : vjIndex;
        VJ_PREVIEWS[i] = `<div class="apk-preview-container">
            <img class="apk-preview-img inactive-img" src="assets/icon_vj_${assetNum}_n3x.webp" alt="VJ ${i}">
            <img class="apk-preview-img active-img" src="assets/icon_vj_${assetNum}_y3x.webp" alt="VJ ${i} Active">
        </div>`;
    }

    buildSelectorGrid("vj-effects-grid", VJ_EFFECTS, (v) => {
        if (!window.requireDevice()) return;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_vj_effect) {
            window.pywebview.api.set_vj_effect(v).then(res => {
                window.showToast(res ? "VJ effect applied" : "Failed to apply VJ effect", res ? "success" : "🔵 BLE");
            });
        }
    }, -1, VJ_PREVIEWS);

    // ── 5. MUSIC EQ GRID ──
    const EQ_MAPPING = [1, 6, 3, 5, 10, 13, 4, 14, 9, 2, 11, 12];
    const EQ_PATTERNS = EQ_MAPPING.map((eqId, idx) => ({ value: idx, name: `EQ ${String(idx + 1).padStart(2, "0")}` }));
    const EQ_PREVIEWS = {};
    for (let i = 0; i < EQ_MAPPING.length; i++) {
        const eqIndex = EQ_MAPPING[i];
        let inactiveSrc, activeSrc;
        
        if ([1, 2, 3, 4, 5, 6, 9, 10].includes(eqIndex)) {
            inactiveSrc = `assets/icon_eq_${eqIndex}_n3x.webp`;
            activeSrc = `assets/icon_eq_${eqIndex}_y3x.webp`;
        } else if ([11, 12, 13, 14].includes(eqIndex)) {
            inactiveSrc = `assets/icon_eq_${eqIndex}_n.webp`;
            activeSrc = `assets/icon_eq_${eqIndex}_y.webp`;
        } else {
            inactiveSrc = `assets/icon_eq_unkonow_n.webp`;
            activeSrc = `assets/icon_eq_unkonow_y.webp`;
        }
        
        EQ_PREVIEWS[i] = `<div class="apk-preview-container">
            <img class="apk-preview-img inactive-img" src="${inactiveSrc}" alt="EQ ${eqIndex}">
            <img class="apk-preview-img active-img" src="${activeSrc}" alt="EQ ${eqIndex} Active">
        </div>`;
    }

    buildSelectorGrid("eq-visualizer-grid", EQ_PATTERNS, (v) => {
        if (!window.requireDevice()) return;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_visualization) {
            window.pywebview.api.set_visualization(v).then(res => {
                window.showToast(res ? "EQ pattern applied" : "Failed to apply EQ", res ? "success" : "🔵 BLE");
            });
        }
    }, -1, EQ_PREVIEWS);

    // ── 6. AMBIENT COLOR TRIGGERS ──
    const applyAmbientBtn = document.getElementById("apply-ambient-btn");
    const ambientColorInput = document.getElementById("ambient-color-input");
    
    window.applyAmbientColor = function(color) {
        if (!window.requireDevice()) return;
        const brightness = parseInt(document.getElementById("global-brightness-slider")?.value) || 80;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_solid_light) {
            window.pywebview.api.set_solid_light(color, brightness).then(res => {
                window.showToast(res ? "Ambient color applied" : "Failed to apply ambient", res ? "success" : "🔵 BLE");
            });
        }
    }

    if (applyAmbientBtn) {
        applyAmbientBtn.addEventListener("click", () => {
            const color = ambientColorInput?.value || "#00ffcc";
            window.applyAmbientColor(color);
        });
    }
    
    document.querySelectorAll(".ambient-swatch").forEach(swatch => {
        swatch.addEventListener("click", () => {
            const color = swatch.getAttribute("data-color");
            if (ambientColorInput) ambientColorInput.value = color;
            window.applyAmbientColor(color);
        });
    });

    // ── 7. DYNAMIC VJ EFFECTS TOGGLE & GALLERY CACHE SELECTOR ──
    window.updateChannelButtonsVisibility = function(name) {
        const vjCard = document.querySelector('.channel-card[data-channel="vj"]');
        if (!vjCard) return;
        
        const n = (name || "").toLowerCase();
        // Timebox Evo supports VJ effects
        const supportsVJ = n.includes("timebox") || n.includes("evo");
        if (supportsVJ) {
            vjCard.style.display = "";
        } else {
            vjCard.style.display = "none";
            // Auto-switch to clock mode if active channel was VJ
            if (window.DivoomState.activeChannel === "vj") {
                const clockCard = document.querySelector('.channel-card[data-channel="clock"]');
                if (clockCard) clockCard.click();
            }
        }
    };
    
    // Hide VJ by default
    window.updateChannelButtonsVisibility("");

    function loadCustomArtCacheGrid() {
        const grid = document.getElementById("custom-art-cache-grid");
        if (!grid) return;
        grid.innerHTML = '<div class="empty-list" style="grid-column: 1/-1;">Loading offline cache...</div>';
        
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_cached_gallery_files) {
            window.pywebview.api.get_cached_gallery_files().then(json => {
                const files = JSON.parse(json);
                grid.innerHTML = "";
                if (!files || files.length === 0) {
                    grid.innerHTML = '<div class="empty-list" style="grid-column: 1/-1;">No cached gallery files. Download them in Monthly Best first!</div>';
                    return;
                }
                files.forEach(f => {
                    const item = document.createElement("button");
                    item.className = "cache-thumb-item";
                    item.style.background = "rgba(0,0,0,0.3)";
                    item.style.border = "1px solid rgba(255,255,255,0.1)";
                    item.style.borderRadius = "4px";
                    item.style.padding = "4px";
                    item.style.cursor = "pointer";
                    item.style.display = "flex";
                    item.style.alignItems = "center";
                    item.style.justifyContent = "center";
                    item.style.aspectRatio = "1/1";
                    item.title = f.name;
                    
                    item.innerHTML = `<img src="${f.preview_url}" style="width:100%; height:100%; object-fit:contain; image-rendering:pixelated; border-radius:2px;">`;
                    item.addEventListener("click", () => {
                        grid.querySelectorAll(".cache-thumb-item").forEach(c => c.style.borderColor = "rgba(255,255,255,0.1)");
                        item.style.borderColor = "var(--primary)";
                        
                        const pathInput = document.getElementById("custom-art-path-input");
                        const previewImg = document.getElementById("custom-art-preview-img");
                        const previewCont = document.getElementById("custom-art-preview-container");
                        
                        if (pathInput) pathInput.value = f.path;
                        if (previewImg) previewImg.src = f.preview_url;
                        if (previewCont) previewCont.style.display = "flex";
                    });
                    grid.appendChild(item);
                });
            });
        }
    }
});
