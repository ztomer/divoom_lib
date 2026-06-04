/* widgets.js — Frameless window controls, live music synchronizer, stocks ticker, and system monitor */

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

    // ── 2. LIVE MUSIC SYNCHRONIZER ──
    const musicSyncToggle = document.getElementById("music-sync-toggle");
    if (musicSyncToggle) {
        musicSyncToggle.addEventListener("change", (e) => {
            const enable = e.target.checked;
            const trackerStatus = document.getElementById("music-track-status");
            if (enable) {
                trackerStatus.classList.add("active");
                window.showToast("Enabled macOS Music track listener thread", "success");
            } else {
                trackerStatus.classList.remove("active");
                document.getElementById("music-track-name").textContent = "No Music Playing";
                document.getElementById("music-artist-name").textContent = "Spotify / Apple Music";
                window.showToast("Music synchronization stopped", "success");
            }

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.toggle_music_sync(enable);
            }
        });
    }

    // Poll live track info from backend every 3 seconds
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
                window.pywebview.api.apply_stock_ticker(symbol)
                    .then(resJson => {
                        if (resJson) {
                            const res = JSON.parse(resJson);
                            if (res.success) {
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
                            } else {
                                window.showToast(res.error || `Failed to display ${symbol}`, "error");
                                showTickerDevicePreview(res.preview);
                            }
                        } else {
                            window.showToast("API return error", "error");
                        }
                    });
            }
        });
    }

    function showTickerDevicePreview(dataUrl) {
        const img = document.getElementById("ticker-device-preview");
        if (img && dataUrl) {
            img.src = dataUrl;
            img.style.display = "inline-block";
        }
    }

    // Saved stock tickers persistence
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

    // Startup Delay Inits
    setTimeout(loadTickers, 1500);
    setTimeout(refreshSysmonPreview, 1800);
});
