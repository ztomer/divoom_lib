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
        if (channel === "design") {
            loadCustomArtCacheGrid();
            renderCustomArtHistory();
        }
    }

    channelCards.forEach(card => {
        card.addEventListener("click", () => {
            channelCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            window.DivoomState.activeChannel = card.getAttribute("data-channel");
            showChannelPanel(window.DivoomState.activeChannel);
            // Ambient and Text are "non-channel" cards (each has its own
            // Apply/Push button). Every other card — Clock, VJ, EQ, Design,
            // Scoreboard — fires switch_channel.
            if (["ambient", "text"].includes(window.DivoomState.activeChannel)) return;
            if (!window.requireDevice()) return;
            if (window.pywebview && window.pywebview.api && window.pywebview.api.switch_channel) {
                window.pywebview.api.switch_channel(window.DivoomState.activeChannel).then(res => {
                    if (res) window.showToast("Switched channel", "success", "🔵 BLE");
                    else window.showToast("Failed to switch channel", "error");
                });
            }
        });
    });

    // Round 7 — Text channel wiring (type & push scrolling text).
    const textSpeedInput = document.getElementById("text-speed-input");
    const textSpeedVal = document.getElementById("text-speed-val");
    if (textSpeedInput && textSpeedVal) {
        textSpeedInput.addEventListener("input", () => { textSpeedVal.textContent = textSpeedInput.value; });
    }
    const pushTextBtn = document.getElementById("push-text-btn");
    if (pushTextBtn) {
        pushTextBtn.addEventListener("click", () => {
            const text = (document.getElementById("text-content-input")?.value || "").trim();
            if (!text) { window.showToast("Enter some text first", "error"); return; }
            if (!window.requireDevice()) return;
            const color = document.getElementById("text-color-input")?.value || "#00ffcc";
            const speed = parseInt(document.getElementById("text-speed-input")?.value) || 50;
            const effect = parseInt(document.getElementById("text-effect-select")?.value);
            if (window.pywebview?.api?.push_text) {
                window.pywebview.api.push_text(text, color, 1, speed, isNaN(effect) ? 1 : effect).then(res => {
                    window.showToast(res ? "Text pushed to device" : "Failed to push text", res ? "success" : "error", "🔵 BLE");
                });
            }
        });
    }

    // Round 6 — Scoreboard channel wiring. The scoreboard is a TOOL
    // (0x72 set tool, TOOL_TYPE_SCORE) on a channel (0x06). The channel
    // switch is handled above (the channel-card click fires
    // switch_channel("scoreboard")). The number inputs below auto-push
    // score updates on `change` — same pattern as the clock color input
    // and the ambient color input: no "Show" or "Hide" button. Kare:
    // matches the other channels' "edit-and-it-applies" pattern.
    const scoreboardRedInput = document.getElementById("scoreboard-red");
    const scoreboardBlueInput = document.getElementById("scoreboard-blue");
    function pushScoreboard() {
        if (!window.requireDevice()) return;
        const red = parseInt(scoreboardRedInput?.value) || 0;
        const blue = parseInt(scoreboardBlueInput?.value) || 0;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_scoreboard) {
            window.pywebview.api.set_scoreboard(1, red, blue).then(res => {
                window.showToast(res ? `Score: ${red}–${blue}` : "Failed to set scoreboard", res ? "success" : "🔵 BLE");
            });
        }
    }
    if (scoreboardRedInput) scoreboardRedInput.addEventListener("change", pushScoreboard);
    if (scoreboardBlueInput) scoreboardBlueInput.addEventListener("change", pushScoreboard);

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

    function updateClockPreviewsColor(color) {
        // Style 0 (Full Screen Digital) - update text color and text shadow
        const style0 = document.querySelector(".clock-preview-box.digital-full");
        if (style0) {
            style0.style.color = color;
            style0.style.textShadow = `0 0 6px ${color}`;
        }
        
        // Style 2 (With Box) - update box style: border color and time color
        const style2Span = document.querySelector(".clock-preview-box.digital-box span");
        if (style2Span) {
            style2Span.style.color = color;
            style2Span.style.borderColor = color;
            style2Span.style.textShadow = `0 0 4px ${color}`;
        }
        
        // Style 3 (Analog Square) - update SVG stroke colors
        const style3Svg = document.querySelector(".clock-preview-box.analog-square svg");
        if (style3Svg) {
            style3Svg.querySelectorAll("rect, line").forEach(el => {
                el.style.stroke = color;
            });
            style3Svg.style.color = color;
        }
        
        // Style 4 (Full Screen Neg) - inverted: background is color, text is dark
        const style4 = document.querySelector(".clock-preview-box.digital-neg");
        if (style4) {
            style4.style.backgroundColor = color;
            style4.style.color = "#1a2318";
            style4.style.textShadow = "none";
        }
        
        // Style 5 (Analog Round) - update SVG stroke colors
        const style5Svg = document.querySelector(".clock-preview-box.analog-round svg");
        if (style5Svg) {
            style5Svg.querySelectorAll("circle, line").forEach(el => {
                el.style.stroke = color;
            });
            style5Svg.style.color = color;
        }
    }

    const clockColorInput = document.getElementById("clock-color-input");
    if (clockColorInput) {
        clockColorInput.addEventListener("input", (e) => {
            const color = e.target.value;
            updateClockPreviewsColor(color);
            applyClockStyle(selectedClockStyle);
        });
        
        // Call it initially after a small timeout to let the grid render
        setTimeout(() => {
            updateClockPreviewsColor(clockColorInput.value || "#ffffff");
        }, 500);
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
    const ambientColorInput = document.getElementById("ambient-color-input");
    const ambientSwatches = document.querySelectorAll(".ambient-swatch");
    
    const AMBIENT_EFFECTS = [
        { value: 0, name: "Plain Color" },
        { value: 1, name: "Love (Pulse)" },
        { value: 2, name: "Plants (Breathe)" },
        { value: 3, name: "Sleeping (Fade)" },
        { value: 4, name: "No Mosquitto" }
    ];
    const AMBIENT_PREVIEWS = {
        0: `<div class="ambient-preview plain" style="background:#00ffcc; height:60px; border-radius:4px; box-shadow: 0 0 10px rgba(0,255,204,0.3);"></div>`,
        1: `<div class="ambient-preview love" style="height:60px; border-radius:4px; animation:love-color-cycle 12s linear infinite;"></div>`,
        2: `<svg class="ambient-preview plants" viewBox="0 0 16 16" preserveAspectRatio="none" style="height:60px; width:100%; border-radius:4px; image-rendering:pixelated; display:block;">
                <rect width="16" height="16" fill="#ff0000"/>
                <rect x="0" y="0" width="1" height="16" fill="#0000ff"/>
                <rect x="4" y="0" width="1" height="16" fill="#0000ff"/>
                <rect x="8" y="0" width="1" height="16" fill="#0000ff"/>
                <rect x="12" y="0" width="1" height="16" fill="#0000ff"/>
            </svg>`,
        3: `<div class="ambient-preview sleeping" style="background:#33cc33; height:60px; border-radius:4px;"></div>`,
        4: `<div class="ambient-preview mosquito" style="background:rgba(255, 165, 0, 0.4); height:60px; border-radius:4px;"></div>`
    };

    let selectedAmbientMode = 0;

    function updateAmbientPreviewsColor(color) {
        const plainPreviews = document.querySelectorAll(".ambient-preview.plain");
        plainPreviews.forEach(p => {
            p.style.backgroundColor = color;
            p.style.boxShadow = `0 0 10px ${color}4d`;
        });
    }

    window.applyAmbientColor = function(color) {
        if (!window.requireDevice()) return;
        const brightness = parseInt(document.getElementById("global-brightness-slider")?.value) || 80;
        const modeType = selectedAmbientMode;
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_solid_light) {
            window.pywebview.api.set_solid_light(color, brightness, modeType).then(res => {
                window.showToast(res ? "Ambient mode applied" : "Failed to apply ambient", res ? "success" : "🔵 BLE");
            });
        }
    }

    buildSelectorGrid("ambient-mode-grid", AMBIENT_EFFECTS, (v) => {
        selectedAmbientMode = parseInt(v);
        const color = ambientColorInput?.value || "#00ffcc";
        window.applyAmbientColor(color);
    }, 0, AMBIENT_PREVIEWS);

    // Call it initially after grid builds
    setTimeout(() => {
        const initialColor = ambientColorInput?.value || "#00ffcc";
        updateAmbientPreviewsColor(initialColor);
    }, 500);

    // ── 10-favorites (last-selected colors) — Kare-style bitmap clarity, Rams #10 overridden per user ──
    const FAVORITES_KEY = "divoom-ambient-favorites";
    const FAVORITES_MAX = 10;
    function loadFavorites() {
        try { return JSON.parse(localStorage.getItem(FAVORITES_KEY) || "[]"); }
        catch (e) { return []; }
    }
    function saveFavorites(favs) {
        localStorage.setItem(FAVORITES_KEY, JSON.stringify(favs));
    }
    function pushFavorite(color) {
        if (!color) return;
        const norm = color.toLowerCase();
        const favs = loadFavorites().filter(c => c.toLowerCase() !== norm);
        favs.unshift(norm);
        if (favs.length > FAVORITES_MAX) favs.length = FAVORITES_MAX;
        saveFavorites(favs);
        renderFavorites();
    }
    function renderFavorites() {
        const grid = document.getElementById("ambient-favorites-grid");
        if (!grid) return;
        const label = grid.querySelector("span");
        grid.innerHTML = "";
        if (label) grid.appendChild(label);
        const favs = loadFavorites();
        favs.forEach(color => {
            const btn = document.createElement("button");
            btn.className = "ambient-swatch ambient-favorite";
            btn.style.background = color;
            btn.setAttribute("data-color", color);
            btn.setAttribute("title", color);
            btn.addEventListener("click", () => {
                if (ambientColorInput) ambientColorInput.value = color;
                ambientSwatches.forEach(s => s.classList.remove("active"));
                updateAmbientPreviewsColor(color);
                window.applyAmbientColor(color);
            });
            grid.appendChild(btn);
        });
    }
    renderFavorites();

    ambientSwatches.forEach(swatch => {
        swatch.addEventListener("click", () => {
            ambientSwatches.forEach(s => s.classList.remove("active"));
            swatch.classList.add("active");
            const color = swatch.getAttribute("data-color");
            if (ambientColorInput) ambientColorInput.value = color;
            updateAmbientPreviewsColor(color);
            pushFavorite(color);
            window.applyAmbientColor(color);
        });
    });

    if (ambientColorInput) {
        ambientColorInput.addEventListener("input", (e) => {
            ambientSwatches.forEach(s => s.classList.remove("active"));
            const color = e.target.value.toLowerCase();
            ambientSwatches.forEach(s => {
                if (s.getAttribute("data-color").toLowerCase() === color) {
                    s.classList.add("active");
                }
            });
            updateAmbientPreviewsColor(color);
        });
        ambientColorInput.addEventListener("change", (e) => {
            const color = e.target.value;
            pushFavorite(color);
            window.applyAmbientColor(color);
        });
    }

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
                        if (pathInput) pathInput.value = f.path;
                        if (window.showCustomArtPreview) window.showCustomArtPreview(f.path);
                    });
                    grid.appendChild(item);
                });
            });
        }
    }

    function renderCustomArtHistory() {
        const filmstrip = document.getElementById("custom-art-history-filmstrip");
        if (!filmstrip) return;
        
        let history = [];
        try {
            history = JSON.parse(localStorage.getItem("divoom_custom_art_history") || "[]");
        } catch (e) {
            history = [];
        }
        
        if (history.length === 0) {
            filmstrip.innerHTML = '<div class="empty-list" style="font-size:11px;">No design pushed yet.</div>';
            return;
        }
        
        filmstrip.innerHTML = "";
        history.slice(0, 5).forEach(itemData => {
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
            item.style.width = "48px";
            item.style.height = "48px";
            item.style.flexShrink = "0";
            item.title = itemData.name || "History Item";
            
            const src = itemData.preview_url || "assets/pixoo.png";
            item.innerHTML = `<img src="${src}" style="width:100%; height:100%; object-fit:contain; image-rendering:pixelated; border-radius:2px;">`;
            
            item.addEventListener("click", () => {
                const pathInput = document.getElementById("custom-art-path-input");
                if (pathInput) pathInput.value = itemData.path;
                if (window.showCustomArtPreview) window.showCustomArtPreview(itemData.path);
            });
            
            filmstrip.appendChild(item);
        });
    }
    
    window.addCustomArtToHistory = function(name, path, preview_url) {
        let history = [];
        try {
            history = JSON.parse(localStorage.getItem("divoom_custom_art_history") || "[]");
        } catch (e) {
            history = [];
        }
        history = history.filter(h => h.path !== path);
        history.unshift({ name, path, preview_url });
        history = history.slice(0, 5);
        localStorage.setItem("divoom_custom_art_history", JSON.stringify(history));
        renderCustomArtHistory();
    };

    // Load initial history
    setTimeout(renderCustomArtHistory, 1500);
});
