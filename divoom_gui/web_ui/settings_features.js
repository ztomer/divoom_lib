/* settings_features.js — Routines, alarms, sleep, tools, device settings, macOS, MCP */
document.addEventListener("DOMContentLoaded", () => {
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
        // R15 §1+§7: `.settings-tab-btn` → `.tab-btn[data-settings-tab]`
        const btn = e.target.closest(".tab-btn[data-settings-tab]");
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

    // Alarms/Sleep/Tools now live in the Tools sidebar tab — render the alarm
    // rows when that tab is opened.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail && e.detail.tab === "tools") setTimeout(ensureAlarms, 0);
    });
    document.addEventListener("click", (e) => {
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
                window.showToast(res ? `Alarm ${idx + 1} saved` : "Failed to save alarm", res ? "success" : "error", " BLE"));
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
                window.showToast(r ? "Sleep started" : "Failed to start sleep", r ? "success" : "error", " BLE"));
        } else if (e.target.closest("#sleep-stop-btn")) {
            window.pywebview?.api?.stop_sleep?.().then(r =>
                window.showToast(r ? "Sleep stopped" : "Failed", r ? "success" : "error", " BLE"));
        }
    });

    // ── Round 7: Tools (timer / countdown / noise) ─────────────────────
    document.addEventListener("click", (e) => {
        const timerBtn = e.target.closest(".tool-timer-btn");
        if (timerBtn) {
            if (window.requireDevice && !window.requireDevice()) return;
            window.pywebview?.api?.set_timer?.(timerBtn.dataset.action).then(r =>
                window.showToast(r ? `Stopwatch ${timerBtn.dataset.action}` : "Failed", r ? "success" : "error", " BLE"));
            return;
        }
        if (e.target.closest("#countdown-start-btn") || e.target.closest("#countdown-stop-btn")) {
            if (window.requireDevice && !window.requireDevice()) return;
            const action = e.target.closest("#countdown-stop-btn") ? "stop" : "start";
            const mm = parseInt(document.getElementById("countdown-min")?.value) || 0;
            const ss = parseInt(document.getElementById("countdown-sec")?.value) || 0;
            window.pywebview?.api?.set_countdown?.(action, mm, ss).then(r =>
                window.showToast(r ? `Countdown ${action}` : "Failed", r ? "success" : "error", " BLE"));
            return;
        }
        if (e.target.closest("#noise-start-btn") || e.target.closest("#noise-stop-btn")) {
            if (window.requireDevice && !window.requireDevice()) return;
            const action = e.target.closest("#noise-stop-btn") ? "stop" : "start";
            window.pywebview?.api?.set_noise?.(action).then(r =>
                window.showToast(r ? `Noise meter ${action}` : "Failed", r ? "success" : "error", " BLE"));
        }
    });

    // ── Round 8: Tools sub-tab nav (R15 §1+§7: `.tools-subtab-btn` → `.tab-btn[data-tools-tab]`) ──
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".tab-btn[data-tools-tab]");
        if (!btn) return;
        document.querySelectorAll(".tab-btn[data-tools-tab]").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".tools-subtab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        const target = document.getElementById(btn.getAttribute("data-tools-tab"));
        if (target) target.classList.add("active");
    });

    // ── Round 8: Device settings / weather / memorial / FM ─────────────
    function api() { return window.pywebview && window.pywebview.api; }
    function dev() { return !window.requireDevice || window.requireDevice(); }
    function toast(r, ok, fail) { window.showToast(r ? ok : (fail || "Failed"), r ? "success" : "error", " BLE"); }

    const wireToggle = (id, fn) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("change", () => { if (dev()) api()?.[fn]?.(el.checked).then(r => toast(r, "Saved")); });
    };
    wireToggle("hour24-toggle", "set_hour_type");
    wireToggle("tempf-toggle", "set_temp_unit");
    wireToggle("lowpower-toggle", "set_low_power");
    wireToggle("screen-mirror-toggle", "set_screen_mirror");

    // Display orientation (0-3 = 0/90/180/270°).
    const dirSel = document.getElementById("screen-dir-select");
    if (dirSel) dirSel.addEventListener("change", () => {
        if (dev()) api()?.set_screen_dir?.(parseInt(dirSel.value) || 0)
            .then(r => toast(r, "Orientation set"));
    });

    document.addEventListener("click", (e) => {
        if (e.target.closest("#sync-time-btn")) {
            if (dev()) api()?.sync_time?.().then(r => toast(r, "Time synced"));
        } else if (e.target.closest("#device-name-save")) {
            const name = document.getElementById("device-name-input")?.value.trim();
            if (!name) { window.showToast("Enter a name", "error"); return; }
            if (dev()) api()?.set_device_name?.(name).then(r => toast(r, "Name saved"));
        } else if (e.target.closest("#auto-off-save")) {
            const m = parseInt(document.getElementById("auto-off-min")?.value) || 0;
            if (dev()) api()?.set_auto_power_off?.(m).then(r => toast(r, m ? `Auto-off ${m}min` : "Auto-off disabled"));
        } else if (e.target.closest("#memorial-save")) {
            if (!dev()) return;
            const enabled = document.getElementById("memorial-enabled")?.checked;
            const title = document.getElementById("memorial-title")?.value.trim() || "";
            const mo = parseInt(document.getElementById("memorial-month")?.value) || 1;
            const da = parseInt(document.getElementById("memorial-day")?.value) || 1;
            const hh = parseInt(document.getElementById("memorial-hour")?.value) || 0;
            const mi = parseInt(document.getElementById("memorial-min")?.value) || 0;
            api()?.set_memorial?.(0, enabled, mo, da, hh, mi, title).then(r => toast(r, "Anniversary saved"));
        } else if (e.target.closest("#factory-reset-btn")) {
            if (!dev()) return;
            // Double-confirm: a dialog, then a typed token, then the bridge also
            // requires the literal "RESET" string before it sends anything.
            if (!window.confirm("Factory-reset this device? This wipes its stored config and cannot be undone.")) return;
            const token = window.prompt('This is irreversible. Type RESET (all caps) to confirm:');
            if (token !== "RESET") { window.showToast("Factory reset cancelled", "error"); return; }
            api()?.factory_reset?.("RESET").then(r => toast(r, "Device factory-reset"));
        } else if (e.target.closest("#notif-send")) {
            if (!dev()) return;
            const t = parseInt(document.getElementById("notif-app-select")?.value) || 7;
            const txt = document.getElementById("notif-text")?.value.trim() || "";
            api()?.send_notification?.(t, txt).then(r => toast(r, "Notification sent"));
        }
    });

    // FM radio — frequency (MHz → MHz×10) + presets.
    function tuneFM(mhz) {
        const x10 = Math.round(parseFloat(mhz) * 10);
        if (dev()) api()?.set_fm_frequency?.(x10).then(r => toast(r, `Tuned ${mhz} MHz`));
    }
    document.addEventListener("click", (e) => {
        if (e.target.closest("#fm-tune-btn")) {
            tuneFM(document.getElementById("fm-freq")?.value || "101.5");
        } else {
            const preset = e.target.closest(".fm-preset");
            if (preset) {
                const f = preset.getAttribute("data-freq");
                const inp = document.getElementById("fm-freq"); if (inp) inp.value = f;
                tuneFM(f);
            }
        }
    });

    // ── R14 §3 — macOS notification mirroring (Settings → Devices card) ──
    const macToggle    = document.getElementById("macnotif-toggle");
    const macDetail    = document.getElementById("macnotif-detail");
    const macPill      = document.getElementById("macnotif-status-pill");
    const macRulesJson = document.getElementById("macnotif-rules-json");
    const macRulesSave = document.getElementById("macnotif-rules-save");
    const macRulesReset = document.getElementById("macnotif-rules-reset");
    const macRulesMsg  = document.getElementById("macnotif-rules-msg");
    const macRoutingPathEl = document.getElementById("macnotif-routing-path");

    function setMacPill(state) {
        if (!macPill) return;
        macPill.textContent = state;
        macPill.dataset.state = state.toLowerCase();
    }

    function renderMacNotifStatus(s) {
        if (!s) return;
        if (macRoutingPathEl && s.routing_path) macRoutingPathEl.textContent = s.routing_path;
        if (!s.platform_supported) {
            if (macToggle) { macToggle.disabled = true; macToggle.checked = false; }
            setMacPill("unsupported");
            if (macDetail) macDetail.textContent = "macOS notifications are only available on macOS.";
            return;
        }
        if (macToggle) macToggle.disabled = false;
        if (s.running) {
            setMacPill("running");
            if (macToggle) macToggle.checked = true;
        } else {
            setMacPill(s.error ? "error" : "stopped");
            if (macToggle) macToggle.checked = false;
        }
        const c = s.counters || { seen: 0, routed: 0, dropped: 0 };
        if (macDetail) {
            macDetail.textContent = [
                `status:    ${s.running ? "running" : (s.error || "stopped")}`,
                `db:        ${s.db_path || "(not found)"}`,
                `seen:      ${c.seen}`,
                `routed:    ${c.routed}`,
                `dropped:   ${c.dropped}`,
            ].join("\n");
        }
        if (macRulesJson && s.rules && !macRulesJson.dataset.dirty) {
            macRulesJson.value = JSON.stringify(s.rules, null, 2);
        }
    }

    function refreshMacNotifStatus() {
        const a = api();
        if (!a?.get_notification_listener_status) return;
        a.get_notification_listener_status().then(renderMacNotifStatus);
    }

    refreshMacNotifStatus();
    // Refresh counters every 5s while the user is on the Devices card.
    setInterval(refreshMacNotifStatus, 5000);

    if (macToggle) {
        macToggle.addEventListener("change", async () => {
            const a = api();
            if (!a) return;
            try {
                if (macToggle.checked) {
                    const r = await a.start_notification_listener();
                    if (r && r.error) { macToggle.checked = false; toast(r.error, "Mirror failed"); }
                } else {
                    await a.stop_notification_listener();
                }
            } finally {
                refreshMacNotifStatus();
            }
        });
    }

    if (macRulesJson) {
        macRulesJson.addEventListener("input", () => {
            macRulesJson.dataset.dirty = "1";
            if (macRulesMsg) { macRulesMsg.textContent = "unsaved changes"; macRulesMsg.dataset.state = "warn"; }
        });
    }

    if (macRulesSave) {
        macRulesSave.addEventListener("click", async () => {
            const a = api();
            if (!a?.save_notification_routing) return;
            const r = await a.save_notification_routing(macRulesJson.value || "[]");
            if (r.error) {
                if (macRulesMsg) { macRulesMsg.textContent = r.error; macRulesMsg.dataset.state = "error"; }
                return;
            }
            delete macRulesJson.dataset.dirty;
            macRulesJson.value = JSON.stringify(r.rules, null, 2);
            if (macRulesMsg) { macRulesMsg.textContent = "saved"; macRulesMsg.dataset.state = "ok"; }
        });
    }

    if (macRulesReset) {
        macRulesReset.addEventListener("click", async () => {
            const a = api();
            if (!a?.save_notification_routing) return;
            // Pass an empty list to revert to DEFAULT_ROUTING.
            const r = await a.save_notification_routing("[]");
            if (r.error) {
                if (macRulesMsg) { macRulesMsg.textContent = r.error; macRulesMsg.dataset.state = "error"; }
                return;
            }
            delete macRulesJson.dataset.dirty;
            macRulesJson.value = JSON.stringify(r.rules, null, 2);
            if (macRulesMsg) { macRulesMsg.textContent = "reset to defaults"; macRulesMsg.dataset.state = "ok"; }
        });
    }

    // ── R15 §5: MCP server toggle ────────────────────────────────
    const mcpStartBtn = document.getElementById("mcp-start-btn");
    const mcpStopBtn = document.getElementById("mcp-stop-btn");
    const mcpStatusPill = document.getElementById("mcp-status-pill");
    const mcpStatusDetail = document.getElementById("mcp-status-detail");
    const mcpLog = document.getElementById("mcp-log");

    function renderMcpStatus(s) {
        if (!s) return;
        const running = !!s.running;
        if (mcpStatusPill) {
            mcpStatusPill.textContent = running ? "running" : "stopped";
            mcpStatusPill.dataset.state = running ? "ok" : "idle";
        }
        if (mcpStatusDetail) {
            mcpStatusDetail.textContent = s.pid ? `PID: ${s.pid}  mac: ${s.mac || "--"}` : "PID: --";
        }
        if (mcpLog) {
            const lines = Array.isArray(s.last_log_lines) ? s.last_log_lines : [];
            mcpLog.textContent = lines.length ? lines.join("\n") : "No log entries yet.";
        }
        if (mcpStartBtn) mcpStartBtn.disabled = running;
        if (mcpStopBtn) mcpStopBtn.disabled = !running;
    }

    function refreshMcpStatus() {
        if (!api()?.mcp_server_status) return;
        Promise.resolve(api().mcp_server_status()).then(s => renderMcpStatus(s));
    }

    if (mcpStartBtn) {
        mcpStartBtn.addEventListener("click", () => {
            if (!api()?.start_mcp_server) return;
            mcpStartBtn.disabled = true;
            Promise.resolve(api().start_mcp_server("")).then(s => renderMcpStatus(s));
        });
    }
    if (mcpStopBtn) {
        mcpStopBtn.addEventListener("click", () => {
            if (!api()?.stop_mcp_server) return;
            mcpStopBtn.disabled = true;
            Promise.resolve(api().stop_mcp_server()).then(s => renderMcpStatus(s));
        });
    }
    // Refresh on tab activation only — no background polling. The
    // status card shows current state on entry; it updates after
    // Start/Stop click. If the subprocess dies between activations,
    // the next visit will show the new state.
    refreshMcpStatus();
    window.addEventListener("tab-changed", (e) => {
        if (e.detail && e.detail.tab === "settings") {
            refreshMcpStatus();
        }
    });
});
