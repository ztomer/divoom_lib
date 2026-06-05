/* widgets.js — Frameless window controls, live music synchronizer, stocks ticker, and system monitor */

document.addEventListener("DOMContentLoaded", () => {
    // ── 1. FRAMELESS WINDOW TITLEBAR BUTTON BINDINGS ──
    const winMin = document.getElementById("win-min");
    const winMax = document.getElementById("win-max");
    const winClose = document.getElementById("win-close");

    if (winMin) winMin.addEventListener("click", () => window.pywebview?.api?.minimize_window());
    if (winMax) winMax.addEventListener("click", () => window.pywebview?.api?.maximize_window());
    if (winClose) winClose.addEventListener("click", () => window.pywebview?.api?.close_window());

    // Frameless window dragging relative movement via python API
    let isDragging = false, lastScreenX = 0, lastScreenY = 0;
    const appbar = document.querySelector(".integrated-appbar");
    if (appbar) {
        appbar.addEventListener("mousedown", (e) => {
            if (e.button === 0 && !e.target.closest("button, select, input")) {
                isDragging = true; lastScreenX = e.screenX; lastScreenY = e.screenY;
            }
        });
        window.addEventListener("mousemove", (e) => {
            if (!isDragging) return;
            const dx = e.screenX - lastScreenX, dy = e.screenY - lastScreenY;
            lastScreenX = e.screenX; lastScreenY = e.screenY;
            if ((dx || dy) && window.pywebview?.api?.drag_window) window.pywebview.api.drag_window(dx, dy);
        });
        window.addEventListener("mouseup", () => isDragging = false);
    }

    // ── 2. LIVE MUSIC SYNCHRONIZER & AUDIO VISUALIZER POLLING ──
    let visualizerTimer = null;
    let simulatedVisualizerFrameId = null;
    let trackTimer = null;
    let sysmonTimer = null;
    let stockTimer = null;

    function pollVisualizerLevels() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_audio_levels) {
            window.pywebview.api.get_audio_levels().then(resJson => {
                try {
                    const res = JSON.parse(resJson);
                    if (res && res.levels) {
                        if (simulatedVisualizerFrameId) {
                            cancelAnimationFrame(simulatedVisualizerFrameId);
                            simulatedVisualizerFrameId = null;
                        }
                        
                        const fills = document.querySelectorAll(".winamp-fill");
                        fills.forEach((fill, i) => {
                            const val = res.levels[i] || 0;
                            fill.style.height = `${val}%`;
                        });
                        
                        const tip = document.getElementById("audio-loopback-tip");
                        if (tip) {
                            tip.style.display = res.loopback_active ? "none" : "block";
                        }
                    }
                } catch (e) {
                    startSimulatedVisualizer();
                }
            }).catch(() => {
                startSimulatedVisualizer();
            });
        } else {
            startSimulatedVisualizer();
        }
    }

    function startVisualizerPolling() {
        if (visualizerTimer) return;
        pollVisualizerLevels();
        visualizerTimer = setInterval(pollVisualizerLevels, 50); // 20 FPS
    }

    function stopVisualizerPolling() {
        if (visualizerTimer) {
            clearInterval(visualizerTimer);
            visualizerTimer = null;
        }
        if (simulatedVisualizerFrameId) {
            cancelAnimationFrame(simulatedVisualizerFrameId);
            simulatedVisualizerFrameId = null;
        }
        document.querySelectorAll(".winamp-fill").forEach(fill => {
            fill.style.height = "0%";
        });
    }

    function startSimulatedVisualizer() {
        if (simulatedVisualizerFrameId) return;
        function animate() {
            simulatedVisualizerFrameId = requestAnimationFrame(animate);
            const fills = document.querySelectorAll(".winamp-fill");
            fills.forEach((fill, i) => {
                const time = Date.now() * 0.003;
                const base = Math.sin(time + i * 0.8) * 40 + 50;
                const noise = Math.sin(time * 2.3 - i * 1.5) * 20;
                const val = Math.min(100, Math.max(0, base + noise));
                fill.style.height = `${val}%`;
            });
        }
        animate();
    }

    function pollTrackInfo() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_current_track_info) {
            window.pywebview.api.get_current_track_info().then(infoJson => {
                if (infoJson) {
                    const info = JSON.parse(infoJson);
                    if (info && info.track) {
                        document.getElementById("music-track-name").textContent = info.track;
                        document.getElementById("music-artist-name").textContent = `${info.artist} (${info.source})`;
                        if (info.artwork_url) {
                            document.getElementById("music-cover-img").src = info.artwork_url;
                        }
                        const devPrev = document.getElementById("music-device-preview");
                        if (devPrev && info.preview) {
                            devPrev.src = info.preview;
                            devPrev.style.display = "inline-block";
                        }
                    }
                }
            });
        }
    }

    function startTrackPolling() {
        if (trackTimer) return;
        pollTrackInfo();
        trackTimer = setInterval(pollTrackInfo, 3000);
    }

    function stopTrackPolling() {
        if (trackTimer) {
            clearInterval(trackTimer);
            trackTimer = null;
        }
    }

    // ── 3. YAHOO STOCKS TICKER WIDGET ──
    const applyStockBtn = document.getElementById("apply-stock-btn");
    if (applyStockBtn) {
        applyStockBtn.addEventListener("click", () => {
            const symbol = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
            if (!symbol) {
                window.showToast("Please enter a ticker symbol!", "error");
                return;
            }

            window.showToast(`Fetching Yahoo price data for ${symbol}...`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.apply_stock_ticker(symbol).then(resJson => {
                    if (resJson) {
                        const res = JSON.parse(resJson);
                        if (res.success) {
                            const stockCard = document.getElementById("widget-card-stock");
                            if (stockCard) stockCard.classList.add("widget-active");
                            window.showToast(`Displaying ${symbol} price frame!`, "success", "🔴 Ext");
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
                            
                            // Re-trigger/update active stocks background sync
                            if (window.pywebview.api.toggle_stocks_sync) {
                                window.pywebview.api.toggle_stocks_sync(true, symbol);
                            }
                        } else {
                            const stockCard = document.getElementById("widget-card-stock");
                            if (stockCard) stockCard.classList.remove("widget-active");
                            window.showToast(res.error || `Failed to display ${symbol}`, "error");
                            showTickerDevicePreview(res.preview);
                        }
                    }
                });
            }
        });
    }

    function refreshStockPreview() {
        const symbol = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
        if (!symbol || !(window.pywebview && window.pywebview.api && window.pywebview.api.get_ticker_preview)) return;
        window.pywebview.api.get_ticker_preview(symbol).then(resJson => {
            try {
                if (!resJson) return;
                const res = JSON.parse(resJson);
                if (res.ok) {
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
                }
            } catch (e) {}
        });
    }

    function showTickerDevicePreview(dataUrl) {
        const img = document.getElementById("ticker-device-preview");
        if (img && dataUrl) {
            img.src = dataUrl;
            img.style.display = "inline-block";
        }
    }

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

    function loadTickers() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_tickers) {
            window.pywebview.api.get_tickers().then(json => {
                try { window.DivoomState.savedTickers = JSON.parse(json) || []; renderTickers(window.DivoomState.savedTickers); } catch (e) {}
            });
        }
    }

    function persistTickers() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_tickers) {
            window.pywebview.api.set_tickers(JSON.stringify(window.DivoomState.savedTickers));
        }
        renderTickers(window.DivoomState.savedTickers);
    }

    function removeTicker(sym) {
        window.DivoomState.savedTickers = window.DivoomState.savedTickers.filter(s => s !== sym);
        persistTickers();
    }

    const addTickerBtn = document.getElementById("add-ticker-btn");
    if (addTickerBtn) {
        addTickerBtn.addEventListener("click", () => {
            const sym = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
            if (!sym) { window.showToast("Enter a ticker symbol first.", "error"); return; }
            if (!window.DivoomState.savedTickers.includes(sym)) {
                window.DivoomState.savedTickers.push(sym);
                persistTickers();
                window.showToast(`Saved ${sym}`, "success");
            }
        });
    }

    // ── 4. SYSTEM STATS MONITOR ──
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
                    window.showToast(r.success ? "System monitor on device" : (r.error || "Failed"), r.success ? "success" : "🔵 BLE");
                } catch (e) { window.showToast("Failed", "error"); }
            });
        });
    }

    let selectedWidget = "music"; // Default selected widget is cover art

    function selectWidget(widgetId) {
        selectedWidget = widgetId;
        
        // Update visual card states
        const cards = ["music", "stock", "sysmon"];
        cards.forEach(id => {
            const cardEl = document.getElementById(`widget-card-${id}`);
            if (cardEl) {
                cardEl.classList.toggle("widget-active", id === widgetId);
            }
        });
        
        // Trigger background sync toggles
        syncActiveWidget();
    }

    function syncActiveWidget() {
        if (!window.pywebview || !window.pywebview.api) return;
        const isTabActive = document.getElementById("data-sources")?.classList.contains("active");

        // 1. Music (Cover Art)
        const startMusic = isTabActive && (selectedWidget === "music");
        window.pywebview.api.toggle_music_sync(startMusic);
        if (window.pywebview.api.toggle_audio_visualizer) {
            window.pywebview.api.toggle_audio_visualizer(startMusic);
        }
        if (startMusic) {
            startTrackPolling();
            startVisualizerPolling();
        } else {
            stopTrackPolling();
            stopVisualizerPolling();
        }

        // 2. Stocks
        const symbol = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
        const startStocks = isTabActive && (selectedWidget === "stock") && !!symbol;
        if (window.pywebview.api.toggle_stocks_sync) {
            window.pywebview.api.toggle_stocks_sync(startStocks, symbol || "");
        }
        if (startStocks) {
            refreshStockPreview();
            if (!stockTimer) {
                stockTimer = setInterval(refreshStockPreview, 15000);
            }
        } else {
            if (stockTimer) {
                clearInterval(stockTimer);
                stockTimer = null;
            }
        }

        // 3. System Monitor
        const sysmonLiveChecked = sysmonLive ? sysmonLive.checked : true;
        const startSysmon = isTabActive && (selectedWidget === "sysmon") && sysmonLiveChecked;
        if (window.pywebview.api.toggle_sysmon_sync) {
            window.pywebview.api.toggle_sysmon_sync(startSysmon);
        }
        if (startSysmon) {
            refreshSysmonPreview();
            if (!sysmonTimer) {
                sysmonTimer = setInterval(refreshSysmonPreview, 5000);
            }
        } else {
            if (sysmonTimer) {
                clearInterval(sysmonTimer);
                sysmonTimer = null;
            }
        }
    }

    function bindCardSelection(cardId, widgetName) {
        const card = document.getElementById(cardId);
        if (card) {
            card.style.cursor = "pointer";
            card.addEventListener("click", (e) => {
                if (e.target.closest("input") || e.target.closest("button") || e.target.closest("select")) {
                    if (e.target.closest("#apply-stock-btn") || e.target.closest("#sysmon-display-btn") || e.target.closest("#sysmon-live")) {
                        selectWidget(widgetName);
                    }
                    return;
                }
                selectWidget(widgetName);
            });
        }
    }

    bindCardSelection("widget-card-music", "music");
    bindCardSelection("widget-card-stock", "stock");
    bindCardSelection("widget-card-sysmon", "sysmon");

    const sysmonLive = document.getElementById("sysmon-live");
    if (sysmonLive) {
        sysmonLive.addEventListener("change", () => {
            if (sysmonLive.checked) {
                selectWidget("sysmon");
            } else {
                syncActiveWidget();
            }
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
                    window.showToast(r.success ? "System monitor on device" : (r.error || "Failed"), r.success ? "success" : "🔵 BLE");
                } catch (e) { window.showToast("Failed", "error"); }
            });
        });
    }

    // ── 5. TAB-CHANGED AUTOMATIC WIDGET WORKER CONTROL ──
    window.addEventListener("tab-changed", (e) => {
        const tab = e.detail.tab;
        if (tab === "data-sources") {
            selectWidget(selectedWidget);
        } else {
            // Stop everything when leaving the tab
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.toggle_music_sync(false);
                if (window.pywebview.api.toggle_sysmon_sync) {
                    window.pywebview.api.toggle_sysmon_sync(false);
                }
                if (window.pywebview.api.toggle_stocks_sync) {
                    window.pywebview.api.toggle_stocks_sync(false);
                }
                if (window.pywebview.api.toggle_audio_visualizer) {
                    window.pywebview.api.toggle_audio_visualizer(false);
                }
            }
            stopTrackPolling();
            stopVisualizerPolling();
            if (sysmonTimer) {
                clearInterval(sysmonTimer);
                sysmonTimer = null;
            }
            if (stockTimer) {
                clearInterval(stockTimer);
                stockTimer = null;
            }
            ["music", "stock", "sysmon"].forEach(id => {
                const cardEl = document.getElementById(`widget-card-${id}`);
                if (cardEl) cardEl.classList.remove("widget-active");
            });
        }
    });

    // Startup Delay Inits
    setTimeout(loadTickers, 1500);
    setTimeout(() => {
        if (document.getElementById("data-sources")?.classList.contains("active")) {
            window.dispatchEvent(new CustomEvent("tab-changed", { detail: { tab: "data-sources" } }));
        } else {
            refreshSysmonPreview();
        }
    }, 1800);
});
