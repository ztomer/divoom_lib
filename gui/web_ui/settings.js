/* settings.js — Bluetooth scanning, Wi-Fi screen lists, theme modes, and cloud credentials */

document.addEventListener("DOMContentLoaded", () => {
    // ── 1. MAIN TAB SWITCH NAVIGATION ──
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            navButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(t => t.classList.remove("active"));
            
            btn.classList.add("active");
            const targetTab = btn.getAttribute("data-tab");
            const el = document.getElementById(targetTab);
            if (el) el.classList.add("active");

            // Dispatch custom event to notify other scripts (e.g. widgets or gallery)
            window.dispatchEvent(new CustomEvent("tab-changed", { detail: { tab: targetTab } }));
        });
    });

    // Sub-settings tabs navigation click handler
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

    // ── 2. THEME SELECTOR WIRING ──
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

    // ── 3. BLUETOOTH SCREEN SCANNER UI ──
    const scanBtn = document.getElementById("scan-btn");
    const scanSpinner = document.getElementById("scan-spinner");
    const deviceListUl = document.getElementById("device-list");

    // Persist scan timeout / limit values on change
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

    window.runBleScan = function() {
        const timeout = parseInt(document.getElementById("scan-timeout")?.value) || 15;
        const limit = parseInt(document.getElementById("scan-limit")?.value) || 0;

        if (scanSpinner) scanSpinner.style.display = "inline-block";
        if (scanBtn) scanBtn.disabled = true;
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.scan_devices(timeout, limit)
                .then(devicesJson => {
                    if (scanSpinner) scanSpinner.style.display = "none";
                    if (scanBtn) scanBtn.disabled = false;
                    
                    const devices = JSON.parse(devicesJson);
                    window.DivoomState.discoveredDevices = devices;
                    populateDeviceSelectors(devices);
                    window.showToast(`Discovered ${devices.length} screens!`, "success");
                    window.renderArrangerCanvas(); 
                });
        } else {
            if (scanSpinner) scanSpinner.style.display = "none";
            if (scanBtn) scanBtn.disabled = false;
            window.showToast("Web interface API unavailable.", "error");
        }
    }

    if (scanBtn) {
        scanBtn.addEventListener("click", window.runBleScan);
    }

    function populateDeviceSelectors(devices) {
        if (deviceListUl) {
            deviceListUl.innerHTML = "";
            if (devices.length === 0) {
                deviceListUl.innerHTML = `<tr><td colspan="4" class="empty-list">No BLE screens found.</td></tr>`;
            } else {
                devices.forEach(d => {
                    const tr = document.createElement("tr");
                    tr.style.cursor = "pointer";
                    const color = window.deviceColor(d.address);
                    const dims = window.getDeviceDimensions ? window.getDeviceDimensions(d.name) : { size: 16 };
                    const isSpk = /timoo|ditoo/i.test(d.name || "");
                    tr.innerHTML = `
                        <td>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span class="device-accent-dot" style="background:${color}; box-shadow:0 0 6px ${color}; width:8px; height:8px; border-radius:50%; display:inline-block;"></span>
                                <span>${d.name}</span>
                            </div>
                        </td>
                        <td><span class="device-mac">${d.address}</span></td>
                        <td>${dims.size}x${dims.size}</td>
                        <td>${isSpk ? "Yes" : "No"}</td>
                    `;
                    tr.addEventListener("click", () => {
                        window.connectDevice(d.name, d.address);
                    });
                    deviceListUl.appendChild(tr);
                });
            }
        }
        window.updateDeviceSelectorDropdown();
    }

    // ── 4. Wi-Fi (LAN) DEVICES MANAGER ──
    window.loadLanDevices = function() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_lan_devices()
                .then(json => {
                    try {
                        window.DivoomState.registeredLanDevices = JSON.parse(json);
                        renderLanDevicesList();
                        window.updateDeviceSelectorDropdown();
                    } catch(e) {
                        window.DivoomState.registeredLanDevices = [];
                    }
                });
        }
    }

    function renderLanDevicesList() {
        const tbody = document.getElementById("lan-device-list");
        if (!tbody) return;
        tbody.innerHTML = "";
        if (window.DivoomState.registeredLanDevices.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-list">No Wi-Fi screens registered.</td></tr>';
            return;
        }
        window.DivoomState.registeredLanDevices.forEach(d => {
            const tr = document.createElement("tr");
            const dims = window.getDeviceDimensions ? window.getDeviceDimensions(`Wi-Fi Screen: ${d.ip}`) : { size: 16 };
            tr.innerHTML = `
                <td style="font-weight:600; cursor:pointer;" class="lan-connect-cell">🟢 ${d.ip}</td>
                <td>${d.token || 0}</td>
                <td>${dims.size}x${dims.size}</td>
                <td>—</td>
                <td>
                    <button class="glow-btn compact delete-lan-btn" style="margin:0; background:rgba(255, 68, 68, 0.15); border-color:#ef4444; color:#ef4444; padding: 4px 8px; font-size: 11px;" data-ip="${d.ip}">Delete</button>
                </td>
            `;
            tr.querySelector(".lan-connect-cell").addEventListener("click", () => {
                window.connectDevice(`Local Network: ${d.ip}`, `LAN:${d.ip}`);
            });
            tr.querySelector(".delete-lan-btn").addEventListener("click", (e) => {
                e.stopPropagation();
                const ip = e.target.getAttribute("data-ip");
                if (window.pywebview && window.pywebview.api) {
                    window.pywebview.api.delete_lan_device(ip)
                        .then(ok => {
                            if (ok) {
                                window.showToast("Deleted Wi-Fi device", "success");
                                window.loadLanDevices();
                            }
                        });
                }
            });
            tbody.appendChild(tr);
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
            if (!ip) { window.showToast("Enter an IP Address", "error"); return; }
            
            if (probeResult) { probeResult.textContent = "Connecting..."; probeResult.className = "lan-probe-result"; }
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.add_lan_device(ip, token)
                    .then(ok => {
                        if (ok) {
                            window.showToast(`Added Wi-Fi device: ${ip}`, "success");
                            if (probeResult) { probeResult.textContent = "Device registered successfully."; probeResult.className = "lan-probe-result success"; }
                            if (ipInput) ipInput.value = "";
                            if (tokenInput) tokenInput.value = "0";
                            window.loadLanDevices();
                        } else {
                            window.showToast("Failed to add Wi-Fi device", "error");
                            if (probeResult) { probeResult.textContent = "Could not register device."; probeResult.className = "lan-probe-result error"; }
                        }
                    });
            }
        });
    }

    // ── 5. TRANSPORT POLLING STATUS PANEL ──
    function updateTransportPanel(status) {
        const transports = [
            { name: 'Bluetooth (BLE)', key: 'ble',      dotId: 'tr-ble-dot',   detailId: 'tr-ble-detail' },
            { name: 'Local Network (LAN)', key: 'lan',      dotId: 'tr-lan-dot',   detailId: 'tr-lan-detail' },
            { name: 'Divoom Cloud', key: 'cloud',    dotId: 'tr-cloud-dot', detailId: 'tr-cloud-detail' },
            { name: 'Public Cloud', key: 'external', dotId: 'tr-ext-dot',   detailId: 'tr-ext-detail' },
        ];
        transports.forEach(({ name, key, dotId, detailId }) => {
            const t = status[key];
            if (!t) return;
            const dot    = document.getElementById(dotId);
            const detail = document.getElementById(detailId);
            if (dot) {
                dot.className = `transport-dot ${t.available ? 'active' : 'inactive'}`;
                if (t.detail) {
                    dot.setAttribute("title", `${name}: ${t.detail}`);
                }
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

    // ── 6. CLOUD CREDENTIALS ──
    const saveCredsBtn = document.getElementById("save-creds-btn");
    if (saveCredsBtn) {
        saveCredsBtn.addEventListener("click", () => {
            const email = document.getElementById("settings-email").value.trim();
            const pwd = document.getElementById("settings-password").value.trim();

            if (!email || !pwd) {
                window.showToast("Email and Password are required!", "error");
                return;
            }

            window.showToast("Saving cloud credentials...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_credentials(email, pwd)
                    .then(res => {
                        if (res) {
                            window.showToast("Credentials configured & login cache generated!", "success");
                            const statusBox = document.getElementById("divoom-cloud-status-box");
                            if (statusBox) {
                                statusBox.style.display = "flex";
                                statusBox.style.background = "rgba(34, 197, 94, 0.15)";
                                statusBox.style.border = "1px solid rgba(34, 197, 94, 0.3)";
                                statusBox.style.color = "#22c55e";
                                statusBox.innerHTML = `<span>🟢 Connected as <b>${email}</b></span>`;
                            }
                        } else {
                            window.showToast("Authentication failed. Please verify credentials.", "error");
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

    // Poll every 5 seconds
    setInterval(refreshTransportStatus, 5000);

    // Initializers on mount after small delays
    setTimeout(refreshTransportStatus, 1500);
    setTimeout(window.loadLanDevices, 1200);

    // ── 4. ROUTINES (Round 6 — moved from Monthly Best) ──
    // Auto-sync gallery schedule. The underlying API methods
    // (get_hot_channel_config / save_hot_channel_config) are unchanged
    // — the config key in `hotchannel_config.json` is also unchanged
    // for backward compat with running daemons.
    window.loadRoutinesAutoSync = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_hot_channel_config) {
            window.pywebview.api.get_hot_channel_config().then(json => {
                try {
                    const cfg = JSON.parse(json);
                    const en = document.getElementById("routines-auto-sync-enabled");
                    const iv = document.getElementById("routines-auto-sync-interval");
                    if (en) en.checked = !!cfg.enabled;
                    if (iv) iv.value = String(cfg.interval);
                } catch (e) { /* ignore */ }
            });
        }
    }

    const routinesSaveBtn = document.getElementById("routines-auto-sync-save");
    if (routinesSaveBtn) {
        routinesSaveBtn.addEventListener("click", () => {
            const enabled = document.getElementById("routines-auto-sync-enabled")?.checked || false;
            const interval = parseInt(document.getElementById("routines-auto-sync-interval")?.value) || 3600;
            window.pywebview.api.save_hot_channel_config(JSON.stringify({ enabled, interval })).then(ok => {
                const st = document.getElementById("routines-auto-sync-status");
                if (st) st.textContent = ok ? (enabled ? "Saved — auto-sync on" : "Saved — auto-sync off") : "Failed to save";
                window.showToast(ok ? "Schedule saved" : "Failed to save schedule", ok ? "success" : "error");
            });
        });
    }

    // Load the routines form when the Settings tab is opened OR when
    // the Routines sub-tab is selected.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail && e.detail.tab === "settings") {
            setTimeout(window.loadRoutinesAutoSync, 0);
        }
    });
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".settings-tab-btn");
        if (btn && btn.getAttribute("data-settings-tab") === "settings-routines") {
            setTimeout(window.loadRoutinesAutoSync, 0);
        }
    });

    // ── Round 7: Alarms editor (10 slots) ──────────────────────────────
    const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
    let alarmsRendered = false;
    function renderAlarmRows(alarms) {
        const list = document.getElementById("alarms-list");
        if (!list) return;
        list.innerHTML = "";
        for (let i = 0; i < 10; i++) {
            const a = (alarms && alarms[i]) || {};
            const week = a.week || 0;
            const days = WEEKDAYS.map((d, b) =>
                `<label class="alarm-day"><input type="checkbox" data-bit="${b}" ${week & (1 << b) ? "checked" : ""}>${d}</label>`).join("");
            const row = document.createElement("div");
            row.className = "alarm-row";
            row.dataset.index = i;
            row.style.cssText = "display:flex; flex-wrap:wrap; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.06);";
            row.innerHTML =
                `<input type="checkbox" class="alarm-enabled" ${a.status ? "checked" : ""} title="Enable">` +
                `<input type="number" class="alarm-hour text-input" min="0" max="23" value="${a.hour ?? 7}" style="width:54px; text-align:center;">` +
                `<span>:</span>` +
                `<input type="number" class="alarm-min text-input" min="0" max="59" value="${String(a.minute ?? 0).padStart(2,'0')}" style="width:54px; text-align:center;">` +
                `<span class="alarm-days" style="display:flex; gap:4px; font-size:10px; flex-wrap:wrap;">${days}</span>` +
                `<button class="glow-btn compact alarm-save" style="margin-left:auto;">Save</button>`;
            list.appendChild(row);
        }
        alarmsRendered = true;
    }
    function ensureAlarms() { if (!alarmsRendered) renderAlarmRows([]); }

    document.addEventListener("click", (e) => {
        const tab = e.target.closest(".settings-tab-btn");
        if (tab && tab.getAttribute("data-settings-tab") === "settings-divoom") {
            setTimeout(ensureAlarms, 0);
        }
        const saveBtn = e.target.closest(".alarm-save");
        if (saveBtn) {
            if (window.requireDevice && !window.requireDevice()) return;
            const row = saveBtn.closest(".alarm-row");
            const idx = parseInt(row.dataset.index);
            const enabled = row.querySelector(".alarm-enabled").checked;
            const hour = parseInt(row.querySelector(".alarm-hour").value) || 0;
            const minute = parseInt(row.querySelector(".alarm-min").value) || 0;
            let week = 0;
            row.querySelectorAll(".alarm-days input:checked").forEach(cb => { week |= (1 << parseInt(cb.dataset.bit)); });
            window.pywebview?.api?.set_alarm?.(idx, enabled, hour, minute, week).then(res =>
                window.showToast(res ? `Alarm ${idx + 1} saved` : "Failed to save alarm", res ? "success" : "error", "🔵 BLE"));
        }
    });
    const alarmsRefreshBtn = document.getElementById("alarms-refresh-btn");
    if (alarmsRefreshBtn) {
        alarmsRefreshBtn.addEventListener("click", () => {
            window.pywebview?.api?.get_alarms?.().then(json => {
                try { renderAlarmRows(JSON.parse(json)); } catch (e) { renderAlarmRows([]); }
            });
        });
    }

    // ── Round 7: Sleep Aid ─────────────────────────────────────────────
    const sleepVol = document.getElementById("sleep-volume");
    const sleepVolVal = document.getElementById("sleep-vol-val");
    if (sleepVol && sleepVolVal) sleepVol.addEventListener("input", () => { sleepVolVal.textContent = sleepVol.value; });
    document.addEventListener("click", (e) => {
        if (e.target.closest("#sleep-start-btn")) {
            if (window.requireDevice && !window.requireDevice()) return;
            const m = parseInt(document.getElementById("sleep-minutes")?.value) || 30;
            const c = document.getElementById("sleep-color")?.value || "#2040ff";
            const v = parseInt(document.getElementById("sleep-volume")?.value) || 10;
            window.pywebview?.api?.start_sleep?.(m, c, v).then(r =>
                window.showToast(r ? "Sleep started" : "Failed to start sleep", r ? "success" : "error", "🔵 BLE"));
        } else if (e.target.closest("#sleep-stop-btn")) {
            window.pywebview?.api?.stop_sleep?.().then(r =>
                window.showToast(r ? "Sleep stopped" : "Failed", r ? "success" : "error", "🔵 BLE"));
        }
    });

    // ── Round 7: Tools (timer / countdown / noise) ─────────────────────
    document.addEventListener("click", (e) => {
        const timerBtn = e.target.closest(".tool-timer-btn");
        if (timerBtn) {
            if (window.requireDevice && !window.requireDevice()) return;
            window.pywebview?.api?.set_timer?.(timerBtn.dataset.action).then(r =>
                window.showToast(r ? `Stopwatch ${timerBtn.dataset.action}` : "Failed", r ? "success" : "error", "🔵 BLE"));
            return;
        }
        if (e.target.closest("#countdown-start-btn") || e.target.closest("#countdown-stop-btn")) {
            if (window.requireDevice && !window.requireDevice()) return;
            const action = e.target.closest("#countdown-stop-btn") ? "stop" : "start";
            const mm = parseInt(document.getElementById("countdown-min")?.value) || 0;
            const ss = parseInt(document.getElementById("countdown-sec")?.value) || 0;
            window.pywebview?.api?.set_countdown?.(action, mm, ss).then(r =>
                window.showToast(r ? `Countdown ${action}` : "Failed", r ? "success" : "error", "🔵 BLE"));
            return;
        }
        if (e.target.closest("#noise-start-btn") || e.target.closest("#noise-stop-btn")) {
            if (window.requireDevice && !window.requireDevice()) return;
            const action = e.target.closest("#noise-stop-btn") ? "stop" : "start";
            window.pywebview?.api?.set_noise?.(action).then(r =>
                window.showToast(r ? `Noise meter ${action}` : "Failed", r ? "success" : "error", "🔵 BLE"));
        }
    });
});
