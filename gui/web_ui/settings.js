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
            window.pywebview.api.scan_devices_with_config(timeout, limit)
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
                deviceListUl.innerHTML = `<tr><td colspan="2" class="empty-list">No BLE screens found.</td></tr>`;
            } else {
                devices.forEach(d => {
                    const tr = document.createElement("tr");
                    tr.style.cursor = "pointer";
                    const color = window.deviceColor(d.address);
                    tr.innerHTML = `
                        <td>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span class="device-accent-dot" style="background:${color}; box-shadow:0 0 6px ${color}; width:8px; height:8px; border-radius:50%; display:inline-block;"></span>
                                <span>${d.name}</span>
                            </div>
                        </td>
                        <td><span class="device-mac">${d.address}</span></td>
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
            tbody.innerHTML = '<tr><td colspan="3" class="empty-list">No Wi-Fi screens registered.</td></tr>';
            return;
        }
        window.DivoomState.registeredLanDevices.forEach(d => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight:600; cursor:pointer;" class="lan-connect-cell">🟢 ${d.ip}</td>
                <td>${d.token || 0}</td>
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
});
