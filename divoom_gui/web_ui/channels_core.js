/* channels_core.js — Navigation, swatches, buildSelectorGrid helper */
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
    
    // ── 2. CHANNEL CARDS NAVIGATION (R15 §1+§7: `.channel-card` → `.tab-btn`) ──
    const channelCards = document.querySelectorAll(".tab-btn[data-channel]");
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
                    if (res) window.showToast("Switched channel", "success", " BLE");
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
                    window.showToast(res ? "Text pushed to device" : "Failed to push text", res ? "success" : "error", " BLE");
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
                window.showToast(res ? `Score: ${red}–${blue}` : "Failed to set scoreboard", res ? "success" : " BLE");
            });
        }
    }
    if (scoreboardRedInput) scoreboardRedInput.addEventListener("change", pushScoreboard);
    if (scoreboardBlueInput) scoreboardBlueInput.addEventListener("change", pushScoreboard);

    // R11 item 5a: Reset both scores to 0 and push.
    const scoreboardResetBtn = document.getElementById("scoreboard-reset-btn");
    if (scoreboardResetBtn) scoreboardResetBtn.addEventListener("click", () => {
        if (scoreboardRedInput) scoreboardRedInput.value = 0;
        if (scoreboardBlueInput) scoreboardBlueInput.value = 0;
        pushScoreboard();
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

    window.buildSelectorGrid = buildSelectorGrid;
});
