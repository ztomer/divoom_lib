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

    // ── 2. LIVE MUSIC SYNCHRONIZER & REAL WEB AUDIO VISUALIZER ──
    let audioCtx = null;
    let analyser = null;
    let audioStream = null;
    let dataArray = null;
    let animationFrameId = null;

    function startRealVisualizer() {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => {
                    audioStream = stream;
                    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    analyser = audioCtx.createAnalyser();
                    analyser.fftSize = 64; // Small FFT size for 10 bars
                    const source = audioCtx.createMediaStreamSource(audioStream);
                    source.connect(analyser);
                    
                    const bufferLength = analyser.frequencyBinCount;
                    dataArray = new Uint8Array(bufferLength);
                    
                    animateRealVisualizer();
                    console.log("Real Web Audio visualizer started successfully!");
                })
                .catch(err => {
                    console.warn("Could not start real Web Audio visualizer (falling back to realistic simulation):", err);
                    animateSimulatedVisualizer();
                });
        } else {
            console.warn("navigator.mediaDevices.getUserMedia is not supported, using simulated visualizer.");
            animateSimulatedVisualizer();
        }
    }

    function stopRealVisualizer() {
        if (animationFrameId) {
            cancelAnimationFrame(animationFrameId);
            animationFrameId = null;
        }
        if (audioStream) {
            audioStream.getTracks().forEach(track => track.stop());
            audioStream = null;
        }
        if (audioCtx) {
            audioCtx.close();
            audioCtx = null;
        }
        analyser = null;
        
        // Reset heights to 0%
        document.querySelectorAll(".winamp-fill").forEach(fill => {
            fill.style.height = "0%";
        });
    }

    function animateRealVisualizer() {
        if (!analyser) return;
        animationFrameId = requestAnimationFrame(animateRealVisualizer);
        
        analyser.getByteFrequencyData(dataArray);
        const fills = document.querySelectorAll(".winamp-fill");
        const numBars = fills.length;
        const binsPerBar = Math.floor(dataArray.length / numBars) || 1;
        
        for (let i = 0; i < numBars; i++) {
            let sum = 0;
            for (let j = 0; j < binsPerBar; j++) {
                sum += dataArray[i * binsPerBar + j];
            }
            const val = sum / binsPerBar;
            const percent = Math.min(100, Math.max(0, (val / 255) * 100));
            if (fills[i]) {
                fills[i].style.height = `${percent}%`;
            }
        }
    }

    function animateSimulatedVisualizer() {
        if (audioCtx) return; // Real is running
        animationFrameId = requestAnimationFrame(animateSimulatedVisualizer);
        const fills = document.querySelectorAll(".winamp-fill");
        fills.forEach((fill, i) => {
            const time = Date.now() * 0.003;
            const base = Math.sin(time + i * 0.8) * 40 + 50;
            const noise = Math.sin(time * 2.3 - i * 1.5) * 20;
            const val = Math.min(100, Math.max(0, base + noise));
            fill.style.height = `${val}%`;
        });
    }

    const musicSyncToggle = document.getElementById("music-sync-toggle");
    if (musicSyncToggle) {
        musicSyncToggle.addEventListener("change", (e) => {
            const enable = e.target.checked;
            const trackerStatus = document.getElementById("music-track-status");
            const musicCard = document.getElementById("widget-card-music");
            if (enable) {
                trackerStatus.classList.add("active");
                if (musicCard) musicCard.classList.add("widget-active");
                window.showToast("Enabled macOS Music track listener thread", "success");
                startRealVisualizer();
            } else {
                trackerStatus.classList.remove("active");
                if (musicCard) musicCard.classList.remove("widget-active");
                document.getElementById("music-track-name").textContent = "No Music Playing";
                document.getElementById("music-artist-name").textContent = "Spotify / Apple Music";
                window.showToast("Music synchronization stopped", "success");
                stopRealVisualizer();
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
                            } else {
                                const stockCard = document.getElementById("widget-card-stock");
                                if (stockCard) stockCard.classList.remove("widget-active");
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
            const sysmonCard = document.getElementById("widget-card-sysmon");
            if (e.target.checked) {
                if (sysmonCard) sysmonCard.classList.add("widget-active");
                refreshSysmonPreview();
                sysmonTimer = setInterval(() => {
                    refreshSysmonPreview();
                    if (window.pywebview && window.pywebview.api && window.pywebview.api.apply_system_stats) {
                        window.pywebview.api.apply_system_stats();
                    }
                }, 5000);
            } else {
                if (sysmonCard) sysmonCard.classList.remove("widget-active");
                if (sysmonTimer) {
                    clearInterval(sysmonTimer);
                    sysmonTimer = null;
                }
            }
        });
    }

    // Delegated listener for simulated Notification triggers
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".notif-trigger-btn");
        if (btn) {
            const app = btn.getAttribute("data-app");
            const notifCard = document.getElementById("widget-card-notif");
            if (notifCard) notifCard.classList.add("widget-active");
            
            window.showToast(`Sending ${app} alert...`, "success");
            if (window.pywebview && window.pywebview.api && window.pywebview.api.trigger_notification) {
                window.pywebview.api.trigger_notification(app).then(resJson => {
                    if (resJson) {
                        const res = JSON.parse(resJson);
                        if (res.success) {
                            window.showToast(`${app} alert displayed!`, "success", "🔵 BLE");
                        } else {
                            window.showToast(res.error || "Failed to trigger alert", "error");
                        }
                        const prev = document.getElementById("notif-device-preview");
                        if (prev && res.preview) {
                            prev.src = res.preview;
                            prev.style.display = "inline-block";
                        }
                    }
                    setTimeout(() => {
                        if (notifCard) notifCard.classList.remove("widget-active");
                    }, 3000);
                });
            }
        }
    });

    // Startup Delay Inits
    setTimeout(loadTickers, 1500);
    setTimeout(refreshSysmonPreview, 1800);
});
