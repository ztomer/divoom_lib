/* settings_features.js — Routines, alarms, sleep, tools, device settings, macOS, MCP */
document.addEventListener("DOMContentLoaded", () => {
    // ── 4. ROUTINES (Round 6 — moved from Monthly Best) ──
    // Auto-sync gallery schedule. The underlying API methods
    // (get_hot_channel_config / save_hot_channel_config) are unchanged
    // — the config key in `hotchannel_config.json` is also unchanged
    // for backward compat with running daemons.
    function saveSchedule() {
        const enabled = document.getElementById("routines-auto-sync-enabled")?.checked || false;
        const interval = parseInt(document.querySelector("#routines-interval-tabs .tab-btn.active")?.getAttribute("data-interval")) || 3600;
        if (window.pywebview?.api?.save_hot_channel_config) {
            window.pywebview.api.save_hot_channel_config(JSON.stringify({ enabled, interval })).then(ok => {
                const st = document.getElementById("routines-auto-sync-status");
                if (st) st.textContent = ok ? (enabled ? "Auto-sync on" : "Auto-sync off") : "Failed to save";
            });
        }
    }

    window.loadRoutinesAutoSync = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_hot_channel_config) {
            window.pywebview.api.get_hot_channel_config().then(json => {
                try {
                    const cfg = JSON.parse(json);
                    const en = document.getElementById("routines-auto-sync-enabled");
                    if (en) en.checked = !!cfg.enabled;
                    const iv = String(cfg.interval || 3600);
                    document.querySelectorAll("#routines-interval-tabs .tab-btn").forEach(b => {
                        b.classList.toggle("active", b.getAttribute("data-interval") === iv);
                    });
                } catch (e) { /* ignore */ }
            });
        }
        if (window.updateSyncTargetList) window.updateSyncTargetList();
    }

    // Auto-save on any change.
    document.getElementById("routines-auto-sync-enabled")?.addEventListener("change", saveSchedule);
    document.addEventListener("click", (e) => {
        const intervalBtn = e.target.closest("#routines-interval-tabs .tab-btn");
        if (intervalBtn) {
            document.querySelectorAll("#routines-interval-tabs .tab-btn").forEach(b => b.classList.remove("active"));
            intervalBtn.classList.add("active");
            saveSchedule();
        }
    });

    // Load the routines form when the Routines tab is opened.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail && e.detail.tab === "routines") {
            setTimeout(window.loadRoutinesAutoSync, 0);
        }
    });


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

    // ── R33: Routines sub-tab nav ──
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".tab-btn[data-routines-tab]");
        if (!btn) return;
        document.querySelectorAll(".tab-btn[data-routines-tab]").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".routines-subtab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        const target = document.getElementById(btn.getAttribute("data-routines-tab"));
        if (target) target.classList.add("active");
    });

    // ── Pixel Art sub-tab nav ──
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".tab-btn[data-pixel-tab]");
        if (!btn) return;
        document.querySelectorAll(".tab-btn[data-pixel-tab]").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".pixel-subtab-content").forEach(c => c.classList.remove("active"));
        btn.classList.add("active");
        const target = document.getElementById(btn.getAttribute("data-pixel-tab"));
        if (target) target.classList.add("active");
        // Refresh gallery/hot preview when switching to those sub-tabs
        if (btn.getAttribute("data-pixel-tab") === "pixel-gallery" && window.loadGallery) {
            setTimeout(window.loadGallery, 50);
        } else if (btn.getAttribute("data-pixel-tab") === "pixel-hot-channel" && window.loadHotPreview) {
            setTimeout(window.loadHotPreview, 50);
        } else if (btn.getAttribute("data-pixel-tab") === "pixel-custom-art") {
            // Re-init custom art if needed (library may have been refreshed)
            if (window.customArtSyncLibrary) setTimeout(window.customArtSyncLibrary, 50);
            if (window.loadCachedGallery) setTimeout(window.loadCachedGallery, 50);
        }
    });

    // ── Round 8: Device settings / weather / memorial / FM ─────────────
    function api() { return window.pywebview && window.pywebview.api; }
    function dev() { return !window.requireDevice || window.requireDevice(); }
    function toast(r, ok, fail) { window.showToast(r ? ok : (fail || "Failed"), r ? "success" : "error", " BLE"); }

    const wireToggle = (id, fn) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener("change", () => { if (dev()) api()?.[fn]?.(el.checked).then(r => toast(r, "Saved")); });
    };
    wireToggle("screen-mirror-toggle", "set_screen_mirror");

    // R40 §8: clock/temp/power are now segmented pills (.tabs-row with
    // data-api on the container + data-val 0/1 on the buttons). Each maps to
    // the same boolean API the old toggles called.
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("#hour24-seg .tab-btn, #tempf-seg .tab-btn, #lowpower-seg .tab-btn");
        if (!btn) return;
        const seg = btn.parentElement;
        seg.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const fn = seg.getAttribute("data-api");
        const on = btn.getAttribute("data-val") === "1";
        if (fn && dev()) api()?.[fn]?.(on).then(r => toast(r, "Saved"));
    });

    // Display orientation (0-3 = 0/90/180/270°) via tab selector.
    document.addEventListener("click", (e) => {
        const dirBtn = e.target.closest("#screen-dir-tabs .tab-btn");
        if (!dirBtn) return;
        document.querySelectorAll("#screen-dir-tabs .tab-btn").forEach(b => b.classList.remove("active"));
        dirBtn.classList.add("active");
        if (dev()) api()?.set_screen_dir?.(parseInt(dirBtn.getAttribute("data-dir")) || 0)
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
    // R40 §9: keep-daemon-alive toggle (Connectivity → Background agent).
    const keepDaemonToggle = document.getElementById("keep-daemon-toggle");
    if (keepDaemonToggle) {
        api()?.get_keep_daemon_alive?.().then(v => { keepDaemonToggle.checked = !!v; });
        keepDaemonToggle.addEventListener("change", () => {
            api()?.set_keep_daemon_alive?.(keepDaemonToggle.checked).then(ok => {
                window.showToast(ok ? (keepDaemonToggle.checked
                    ? "Menu bar will stay running after quit"
                    : "Menu bar will close with the dashboard") : "Failed to save",
                    ok ? "success" : "error");
            });
        });
    }

    const mcpToggle = document.getElementById("mcp-toggle");
    const mcpStatusDetail = document.getElementById("mcp-status-detail");
    const mcpLog = document.getElementById("mcp-log");

    function renderMcpStatus(s) {
        if (!s) return;
        const running = !!s.running;
        if (mcpToggle) mcpToggle.checked = running;
        if (mcpStatusDetail) {
            mcpStatusDetail.textContent = running
                ? (s.pid ? `PID: ${s.pid}  mac: ${s.mac || "--"}` : "running")
                : "stopped";
        }
        if (mcpLog) {
            const lines = Array.isArray(s.last_log_lines) ? s.last_log_lines : [];
            mcpLog.textContent = lines.length ? lines.join("\n") : "No log entries yet.";
        }
    }

    function refreshMcpStatus() {
        if (!api()?.mcp_server_status) return;
        Promise.resolve(api().mcp_server_status()).then(s => renderMcpStatus(s));
    }

    if (mcpToggle) {
        mcpToggle.addEventListener("change", () => {
            if (mcpToggle.checked) {
                if (!api()?.start_mcp_server) return;
                mcpToggle.disabled = true;
                Promise.resolve(api().start_mcp_server("")).then(s => {
                    mcpToggle.disabled = false;
                    renderMcpStatus(s);
                });
            } else {
                if (!api()?.stop_mcp_server) return;
                mcpToggle.disabled = true;
                Promise.resolve(api().stop_mcp_server()).then(s => {
                    mcpToggle.disabled = false;
                    renderMcpStatus(s);
                });
            }
        });
    }
    // Refresh status on tab activation.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail && e.detail.tab === "settings") {
            setTimeout(refreshMcpStatus, 0);
        }
    });
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
