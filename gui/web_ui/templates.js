/* templates.js — House large HTML views as template strings to keep index.html under 500 LOC */

window.DivoomTemplates = {
    tools: `
        <div class="header-section"><h1>Tools</h1></div>
        <!-- R15 §1+§7: tab chrome is now .tabs-row + .tab-btn
             (defined in tabs.css) — same active state as Channels and
             Settings. The legacy class names are aliased in settings.css
             for backward compat with the JS selectors. -->
        <div class="tabs-row" role="tablist" aria-label="Tools">
            <button class="tab-btn active" data-tools-tab="tools-time" data-tab="tools-time" role="tab" aria-selected="true">Time</button>
            <button class="tab-btn" data-tools-tab="tools-sessions" data-tab="tools-sessions" role="tab" aria-selected="false">Sessions</button>
        </div>
        <!-- R11 item 8: TIME sub-tab — alarms + anniversary. -->
        <div class="tools-subtab-content active" id="tools-time">
        <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 600px;">
                        <!-- Round 7: Alarms editor (10 slots) -->
                        <div class="card glass-card">
                            <div class="card-header flex-header">
                                <h3>Alarms</h3>
                                <button id="alarms-refresh-btn" class="glow-btn compact" style="background:transparent; border:1px solid var(--secondary); color:var(--text-main); box-shadow:none;">Read from device</button>
                            </div>
                            <div class="card-body">
                                <p class="panel-hint" style="margin-top:0;">Connect a device, set a time + weekdays, then Save each alarm.</p>
                                <div id="alarms-list" class="alarms-list" style="display:flex; flex-direction:column; gap:8px;"></div>
                            </div>
                        </div>
                        <!-- Anniversary / Memorial (moved into Time, R11 item 8a) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Anniversary / Memorial</h3></div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:12px;">
                                <label class="hc-toggle"><input type="checkbox" id="memorial-enabled" checked> Enabled</label>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <input type="text" id="memorial-title" class="text-input" maxlength="16" style="flex:1; min-width:120px;" placeholder="Title (e.g. Birthday)">
                                </div>
                                <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px;">Date</span>
                                    <input type="number" id="memorial-month" class="text-input" min="1" max="12" value="1" style="width:60px;" title="month">
                                    <span>/</span>
                                    <input type="number" id="memorial-day" class="text-input" min="1" max="31" value="1" style="width:60px;" title="day">
                                    <span class="form-label" style="font-size:12px; margin-left:8px;">at</span>
                                    <input type="number" id="memorial-hour" class="text-input" min="0" max="23" value="9" style="width:60px;" title="hour">
                                    <span>:</span>
                                    <input type="number" id="memorial-min" class="text-input" min="0" max="59" value="0" style="width:60px;" title="minute">
                                    <button id="memorial-save" class="glow-btn compact" style="margin-left:auto;">Save</button>
                                </div>
                            </div>
                        </div>
        </div>
        </div>

        <!-- R11 item 8: SESSIONS sub-tab — sleep aid, FM radio, timer/countdown/noise.
             "Sessions" is the device-manual term for the multi-timer/noise/sleep bundle. -->
        <div class="tools-subtab-content" id="tools-sessions">
        <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 600px;">
                        <!-- Round 7: Sleep Aid -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Sleep Aid</h3></div>
                            <div class="card-body" id="sleep-aid-body">
                                <p class="panel-hint" style="margin-top:0;">Fade the screen to a color over a sleep timer.</p>
                                <div style="display:flex; gap:16px; flex-wrap:wrap; align-items:flex-end;">
                                    <div class="form-group" style="margin:0;">
                                        <label class="form-label" style="font-size:11px; color:var(--text-muted); display:block; margin-bottom:4px;">Minutes</label>
                                        <input type="number" id="sleep-minutes" min="0" max="120" value="30" class="text-input" style="width:90px;">
                                    </div>
                                    <div class="form-group" style="margin:0;">
                                        <label class="form-label" style="font-size:11px; color:var(--text-muted); display:block; margin-bottom:4px;">Color</label>
                                        <input type="color" id="sleep-color" value="#2040ff" style="background:none; border:none; width:44px; height:28px; cursor:pointer; padding:0;">
                                    </div>
                                    <div class="form-group" style="margin:0; flex:1; min-width:120px;">
                                        <label class="form-label" style="font-size:11px; color:var(--text-muted); display:block; margin-bottom:4px;">Volume <span id="sleep-vol-val">10</span></label>
                                        <input type="range" id="sleep-volume" min="0" max="16" value="10" style="width:100%;">
                                    </div>
                                </div>
                                <div style="display:flex; gap:10px; margin-top:14px;">
                                    <button id="sleep-start-btn" class="glow-btn" style="flex:1;">Start Sleep</button>
                                    <button id="sleep-stop-btn" class="glow-btn secondary" style="flex:1;">Stop</button>
                                </div>
                            </div>
                        </div>
                        <!-- Round 7: Tools (timer / countdown / noise) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Tools</h3></div>
                            <div class="card-body" id="tools-body" style="display:flex; flex-direction:column; gap:14px;">
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; font-weight:600; min-width:80px;">Stopwatch</span>
                                    <button class="glow-btn compact tool-timer-btn" data-action="start">Start</button>
                                    <button class="glow-btn compact secondary tool-timer-btn" data-action="stop">Stop</button>
                                    <button class="glow-btn compact secondary tool-timer-btn" data-action="reset">Reset</button>
                                </div>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; font-weight:600; min-width:80px;">Countdown</span>
                                    <input type="number" id="countdown-min" min="0" max="99" value="5" class="text-input" style="width:60px;" title="minutes">
                                    <span>:</span>
                                    <input type="number" id="countdown-sec" min="0" max="59" value="0" class="text-input" style="width:60px;" title="seconds">
                                    <button id="countdown-start-btn" class="glow-btn compact">Start</button>
                                    <button id="countdown-stop-btn" class="glow-btn compact secondary">Stop</button>
                                </div>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; font-weight:600; min-width:80px;">Noise meter</span>
                                    <button id="noise-start-btn" class="glow-btn compact">Start</button>
                                    <button id="noise-stop-btn" class="glow-btn compact secondary">Stop</button>
                                </div>
                            </div>
                        </div>
                        <!-- FM Radio (moved into Tools, R11 item 8c) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>FM Radio</h3></div>
                <div class="card-body" style="display:flex; flex-direction:column; gap:14px;">
                    <p class="panel-hint" style="margin-top:0;">Tune the device's FM radio (FM-capable models only — Tivoo / Ditoo).</p>
                    <div style="display:flex; gap:10px; align-items:center;">
                        <input type="number" id="fm-freq" class="text-input" min="87.5" max="108.0" step="0.1" value="101.5" style="width:100px;">
                        <span style="font-size:12px; color:var(--text-muted);">MHz</span>
                        <button id="fm-tune-btn" class="glow-btn compact">Tune</button>
                    </div>
                    <div id="fm-presets" style="display:flex; gap:8px; flex-wrap:wrap;">
                        <button class="glow-btn compact secondary fm-preset" data-freq="88.1">88.1</button>
                        <button class="glow-btn compact secondary fm-preset" data-freq="95.5">95.5</button>
                        <button class="glow-btn compact secondary fm-preset" data-freq="101.5">101.5</button>
                        <button class="glow-btn compact secondary fm-preset" data-freq="104.3">104.3</button>
                    </div>
                </div>
            </div>
        </div>
        </div>
    `,
    monthlyBest: `
                <div class="monthly-best-layout">
                    <!-- Left: Gallery Card -->
                    <div class="card glass-card" style="display:flex; flex-direction:column; height: 100%;">
                        <div class="card-header flex-header">
                            <div style="display:flex; align-items:center; gap:8px;">
                                <h3>Gallery</h3>
                                <span class="transport-badge cloud" style="position:static; margin-left: 0;">
                                    <svg class="kare-icon" viewBox="0 0 16 16" style="margin-right: 4px;">
                                        <path d="M4,11 C2.5,11 1,9.5 1,8 C1,6.5 2.5,5 4,5 C4.5,3 6.5,2 9,2 C12,2 14.5,4.5 14.5,7.5 C14.5,9.5 13,11 11,11 Z" fill="none" stroke="currentColor" stroke-width="2"/>
                                    </svg>
                                    Divoom Cloud
                                </span>
                            </div>
                            <div class="header-actions">
                                <select id="gallery-classify" class="custom-select small">
                                    <option value="18">Recommend</option>
                                    <option value="3">Cartoon</option>
                                    <option value="9">Creative</option>
                                    <option value="6">Nature</option>
                                </select>
                                <!-- R15 §2: "Fetch Gallery" button removed. The gallery
                                     now auto-loads on tab activation and on classify
                                     change. The button id is kept (load-gallery-btn)
                                     as a ghost hidden element so the auto-fetch
                                     flow in gallery.js can simulate a click. -->
                                <button id="load-gallery-btn" class="glow-btn compact" hidden>Fetch Gallery</button>
                            </div>
                        </div>
                        <div class="card-body" style="flex:1; overflow:hidden; min-height:0; display:flex; flex-direction:column;">
                            <!-- Dynamic Grid with preview covers -->
                            <div class="gallery-grid" id="gallery-container" style="flex:1; overflow-y:auto; min-height:0; margin-bottom:12px;">
                                <div class="empty-list">Loading community gallery...</div>
                            </div>
                            <div class="gallery-actions" style="margin-top:auto; display:flex; gap:10px;">
                                <button id="batch-sync-btn" class="glow-btn" style="flex:1; margin:0;">Update Device</button>
                            </div>
                        </div>
                    </div>

                    <!-- Right: Devices Card (was 'Sync Targets & Schedule'; schedule
                         moved to Settings → Routines, see §3 of docs/PLANNING_ROUND5.md).
                         R15 §2: Refresh button removed (the same operation lives in
                         Settings → Devices as a manual scan, and the auto-refresh
                         is wired by updateSyncTargetList on a 30s timer). -->
                    <div class="card glass-card" style="display:flex; flex-direction:column;">
                        <div class="card-header flex-header">
                            <h3>Devices</h3>
                        </div>
                        <div class="card-body" style="overflow-y:auto;">
                            <div class="hot-channel" style="margin-top: 0; padding-top: 0; border-top: none;">
                                <div id="sync-targets-list" class="sync-targets-list" style="margin-bottom: 12px;">
                                    <span class="empty-list">No devices — scan under Settings, or add a Wi-Fi screen.</span>
                                </div>

                                <div class="hc-actions">
                                    <button id="sync-all-btn" class="glow-btn secondary" style="flex:1;">Update Devices</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
    `,
    widgets: `
                <div class="grid-layout three-cols">
                    <!-- macOS Music Tracker -->
                    <div class="card glass-card" id="widget-card-music">
                        <div class="card-header flex-header">
                            <h3>Live cover art</h3>
                            <span class="active-indicator"></span>
                        </div>
                        <div class="card-body">
                            <!-- Cover art + device preview side-by-side, larger than before (Rams #10: as little as possible — no visualizer) -->
                            <div class="music-previews-container" style="margin-bottom: 12px; gap:16px;">
                                <div class="music-cover-preview" style="width:144px; height:144px;">
                                    <div class="cover-vinyl"></div>
                                    <img id="music-cover-img" src="assets/pixoo.png" alt="Vinyl Cover">
                                </div>
                                <div class="music-device-preview-wrap" style="flex:1; min-width:0; display:flex; align-items:center; justify-content:center;">
                                    <img id="music-device-preview" class="device-preview-img" alt="Device Preview" style="display:none; max-width:100%; max-height:144px;">
                                </div>
                            </div>

                            <!-- Track Info (Kare: just the essentials — name + artist) -->
                            <div class="music-tracker-card active" id="music-track-status" style="display:flex; flex-direction:column; gap:8px;">
                                <div class="music-track-info" style="margin-top: 0;">
                                    <h4 id="music-track-name">No Music Playing</h4>
                                    <p id="music-artist-name">Spotify / Apple Music</p>
                                </div>
                                <!-- Cover art is pushed automatically on track change while sync is on
                                     (R11) — the manual push button is obsolete and was removed. -->
                            </div>
                        </div>
                    </div>
                    
                    <!-- Stock Prices Widget -->
                    <div class="card glass-card" id="widget-card-stock" style="min-width:0; overflow:hidden;">
                        <div class="card-header flex-header">
                            <h3>Live Stocks &amp; Crypto Tickers</h3>
                            <span class="active-indicator"></span>
                        </div>
                        <div class="card-body" style="min-width:0; overflow:hidden;">
                            <!-- Preview on top. min-width:0 on flex children so the
                                 ticker box can shrink to fit narrow columns (Kare:
                                 fits the container, Rams #5 unobtrusive). -->
                            <div style="display:flex; gap:12px; margin-bottom:12px; align-items:stretch; min-width:0;">
                                <div class="device-preview-wrap large" style="margin:0; flex-shrink:0;">
                                    <img id="ticker-device-preview" class="device-preview-img" alt="" style="display:none;">
                                </div>
                                <div class="widget-preview-ticker" id="ticker-preview-box" style="flex:1; min-width:0; margin:0; padding:12px;">
                                    <div class="mini-canvas-view" style="min-width:0;">
                                        <div class="ticker-arrow-mock">▲</div>
                                        <div class="ticker-price-mock">$64,285</div>
                                        <div class="ticker-name-mock">BTC</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Input below -->
                            <div class="form-group">
                                <div class="flex-row">
                                    <input type="text" id="stock-symbol-input" placeholder="Symbol e.g. AAPL, BTC-USD" class="text-input" value="BTC-USD">
                                    <button id="apply-stock-btn" class="glow-btn compact">Display</button>
                                    <button id="add-ticker-btn" class="glow-btn compact ghost">+ Save</button>
                                </div>
                            </div>

                            <div id="tickers-list" class="tickers-list"></div>
                        </div>
                    </div>
 
                    <!-- System Monitor -->
                    <div class="card glass-card" id="widget-card-sysmon" style="min-width:0; overflow:hidden;">
                        <div class="card-header flex-header">
                            <h3>System Monitor</h3>
                            <span class="active-indicator"></span>
                        </div>
                        <div class="card-body" style="min-width:0;">
                            <!-- Device preview (the actual frame the device shows).
                                 Above-the-fold: just the dark frame, no white panel. -->
                            <div style="display:flex; justify-content:center; margin-bottom:12px;">
                                <div class="device-preview-wrap large" style="margin:0; flex-shrink:0;">
                                    <img id="sysmon-device-preview" class="device-preview-img" alt="" style="display:none;">
                                </div>
                            </div>

                            <!-- Three labeled bars: CPU (green) / MEM (blue) / BAT (yellow).
                                 Colors match the on-device bar colors so it's recognizable
                                 in 1 second (Rams #4). No white/gray background panels. -->
                            <div class="sysmon-bars" style="display:flex; flex-direction:column; gap:6px; margin-bottom:10px;">
                                <div class="sysmon-bar-row" data-stat="cpu">
                                    <span class="sysmon-bar-label" style="color:#00ffb4;">CPU</span>
                                    <div class="sysmon-bar-track">
                                        <div class="sysmon-bar-fill" data-fill-color="#00ffb4" style="width:0%; background:#00ffb4;"></div>
                                    </div>
                                    <b class="sysmon-bar-value" id="sysmon-cpu" style="color:#00ffb4;">–</b>
                                </div>
                                <div class="sysmon-bar-row" data-stat="mem">
                                    <span class="sysmon-bar-label" style="color:#5aaaff;">MEM</span>
                                    <div class="sysmon-bar-track">
                                        <div class="sysmon-bar-fill" data-fill-color="#5aaaff" style="width:0%; background:#5aaaff;"></div>
                                    </div>
                                    <b class="sysmon-bar-value" id="sysmon-mem" style="color:#5aaaff;">–</b>
                                </div>
                                <div class="sysmon-bar-row" data-stat="bat">
                                    <span class="sysmon-bar-label" style="color:#00ff64;">BAT</span>
                                    <div class="sysmon-bar-track">
                                        <div class="sysmon-bar-fill" data-fill-color="#00ff64" style="width:0%; background:#00ff64;"></div>
                                    </div>
                                    <b class="sysmon-bar-value" id="sysmon-bat" style="color:#00ff64;">–</b>
                                </div>
                            </div>
                            <div class="hc-actions" style="display:flex; gap:10px; align-items:center;">
                                <button id="sysmon-display-btn" class="glow-btn compact" style="margin:0;">Push to Device</button>
                                <label class="hc-toggle" style="margin:0;"><input type="checkbox" id="sysmon-live" checked> Live (5s)</label>
                            </div>
                        </div>
                        <!-- Weather (moved from Tools to Live Widgets, R11 item 8d) -->
                        <div class="card glass-card" id="widget-card-weather">
                            <div class="card-header flex-header"><h3>Weather</h3></div>
                            <div class="card-body">
                                <p class="panel-hint" style="margin-top:0;">Push the current weather to the device's built-in weather widget (pairs with the °C/°F toggle in Settings → Devices).</p>
                                <button id="push-weather-btn" class="glow-btn">Push weather to device</button>
                            </div>
                        </div>
                    </div>
    `,
    settings: `
                <!-- R15 §1+§7: tab chrome is now .tabs-row + .tab-btn
                     (defined in tabs.css) — same active state as Channels and
                     Tools. The legacy class names are aliased in settings.css
                     for backward compat with the JS selectors. -->
                <div class="tabs-row" role="tablist" aria-label="Settings">
                    <button class="tab-btn active" data-settings-tab="settings-devices" data-tab="settings-devices" role="tab" aria-selected="true">Devices</button>
                    <button class="tab-btn" data-settings-tab="settings-divoom" data-tab="settings-divoom" role="tab" aria-selected="false">Divoom</button>
                    <button class="tab-btn" data-settings-tab="settings-routines" data-tab="settings-routines" role="tab" aria-selected="false">Routines</button>
                    <button class="tab-btn" data-settings-tab="settings-connectivity" data-tab="settings-connectivity" role="tab" aria-selected="false">Connectivity</button>
                    <button class="tab-btn" data-settings-tab="settings-appearance" data-tab="settings-appearance" role="tab" aria-selected="false">Appearance</button>
                </div>

                <!-- 1. DEVICES TAB -->
                <div class="settings-tab-content active" id="settings-devices">
                    <div class="grid-layout">
                        <!-- BLE Scanner -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Bluetooth Scanner</h3>
                            </div>
                            <div class="card-body">
                                <div style="display:flex; gap:10px; margin-bottom:15px;">
                                    <div style="flex:1;">
                                        <label class="form-label" style="font-size:10px; margin-bottom:4px; display:block;">Timeout (s)</label>
                                        <input type="number" id="scan-timeout" min="3" max="60" value="15" class="text-input">
                                    </div>
                                    <div style="flex:1;">
                                        <label class="form-label" style="font-size:10px; margin-bottom:4px; display:block;">Devices</label>
                                        <input type="number" id="scan-limit" min="0" max="10" value="4" class="text-input">
                                    </div>
                                </div>

                                <button id="scan-btn" class="glow-btn">
                                    <span class="spinner" id="scan-spinner"></span> Scan Devices
                                </button>

                                <div style="margin-top: 20px;">
                                    <label style="font-size:11px; color:rgba(255,255,255,0.45); margin-bottom:8px; display:block;">Discovered Bluetooth Screens</label>
                                    <table class="braun-table">
                                        <thead>
                                            <tr>
                                                <th>Device Name</th>
                                                <th>Address</th>
                                                <th>Resolution</th>
                                                <th>Speaker</th>
                                            </tr>
                                        </thead>
                                        <tbody id="device-list">
                                            <tr><td colspan="4" class="empty-list">No Bluetooth screens found.</td></tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>

                        <!-- Wi-Fi Devices -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Wi-Fi Screens</h3>
                            </div>
                            <div class="card-body">
                                <div style="display:flex; gap:10px; margin-bottom:15px;">
                                    <div style="flex:2;">
                                        <label class="form-label" style="font-size:10px; margin-bottom:4px; display:block;">IP Address</label>
                                        <input type="text" id="lan-ip-input" class="text-input" placeholder="192.168.1.42">
                                    </div>
                                    <div style="flex:1;">
                                        <label class="form-label" style="font-size:10px; margin-bottom:4px; display:block;">Token</label>
                                        <input type="number" id="lan-token-input" class="text-input" value="0" min="0">
                                    </div>
                                    <div style="display:flex; align-items:flex-end;">
                                        <button id="add-lan-btn" class="glow-btn compact" style="margin-bottom:0; height:38px;">Add</button>
                                    </div>
                                </div>
                                <div class="lan-probe-result" id="lan-probe-result" style="margin-bottom:10px;"></div>

                                <div style="margin-top: 10px;">
                                    <label style="font-size:11px; color:rgba(255,255,255,0.45); margin-bottom:8px; display:block;">Registered Wi-Fi Screens</label>
                                    <table class="braun-table">
                                        <thead>
                                            <tr>
                                                <th>IP Address</th>
                                                <th>Token</th>
                                                <th>Resolution</th>
                                                <th>Speaker</th>
                                                <th>Action</th>
                                            </tr>
                                        </thead>
                                        <tbody id="lan-device-list">
                                            <tr><td colspan="5" class="empty-list">No Wi-Fi screens registered.</td></tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                        <!-- Device Settings (moved from Tools → Settings, R11 item 8e) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Device Settings</h3></div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:14px;">
                                <label class="hc-toggle"><input type="checkbox" id="hour24-toggle"> 24-hour clock</label>
                                <label class="hc-toggle"><input type="checkbox" id="tempf-toggle"> Fahrenheit (°F)</label>
                                <label class="hc-toggle"><input type="checkbox" id="lowpower-toggle"> Low-power mode</label>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; min-width:96px;">Device name</span>
                                    <input type="text" id="device-name-input" class="text-input" maxlength="24" style="flex:1; min-width:140px;" placeholder="Name">
                                    <button id="device-name-save" class="glow-btn compact">Save</button>
                                </div>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; min-width:96px;">Auto power-off</span>
                                    <input type="number" id="auto-off-min" class="text-input" min="0" max="240" value="0" style="width:80px;" title="minutes (0 = off)">
                                    <span style="font-size:12px; color:var(--text-muted);">min</span>
                                    <button id="auto-off-save" class="glow-btn compact">Save</button>
                                </div>
                                <div style="display:flex; gap:10px;">
                                    <button id="sync-time-btn" class="glow-btn" style="flex:1;">Sync time from this Mac</button>
                                </div>
                            </div>
                        </div>
                        <!-- Display (moved from Tools → Settings, R11 item 8e) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Display</h3></div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:14px;">
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; min-width:96px;">Orientation</span>
                                    <select id="screen-dir-select" class="text-input" style="flex:1; min-width:120px;">
                                        <option value="0">0° (normal)</option>
                                        <option value="1">90°</option>
                                        <option value="2">180°</option>
                                        <option value="3">270°</option>
                                    </select>
                                </div>
                                <label class="hc-toggle"><input type="checkbox" id="screen-mirror-toggle"> Mirror / flip display</label>
                                <p class="panel-hint" style="margin:0;">Orientation support is device-dependent; the exact angle mapping may vary by model.</p>
                            </div>
                        </div>
                        <!-- R15 §4: Danger zone is its own card so destructive
                             actions aren't buried at the bottom of an unrelated
                             card. Visual treatment (red border, warning text)
                             unchanged from when it lived inside Display. -->
                        <div class="card glass-card danger-card">
                            <div class="card-header"><h3>Danger zone</h3></div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:10px;">
                                <p class="panel-hint" style="margin:0;">Factory reset wipes the device's stored configuration. This cannot be undone.</p>
                                <button id="factory-reset-btn" class="glow-btn danger">Factory reset device…</button>
                            </div>
                        </div>
                        <!-- Notification (moved from Tools → Settings, R11 item 8e) -->
                        <div class="card glass-card">
                            <div class="card-header"><h3>Notification</h3></div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:12px;">
                                <p class="panel-hint" style="margin-top:0;">Trigger the device's notification display for an app. (Manual — does not mirror your Mac's real notifications.)</p>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <span class="form-label" style="font-size:12px; min-width:60px;">App</span>
                                    <select id="notif-app-select" class="text-input" style="flex:1; min-width:140px;">
                                        <option value="6">WhatsApp</option>
                                        <option value="7">Text message</option>
                                        <option value="2">Instagram</option>
                                        <option value="4">Facebook</option>
                                        <option value="5">Twitter</option>
                                        <option value="13">Messenger</option>
                                        <option value="3">Snapchat</option>
                                        <option value="8">Skype</option>
                                        <option value="9">LINE</option>
                                        <option value="10">WeChat</option>
                                        <option value="11">QQ</option>
                                        <option value="12">Viber</option>
                                        <option value="1">KakaoTalk</option>
                                        <option value="14">Other</option>
                                    </select>
                                </div>
                                <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                                    <input type="text" id="notif-text" class="text-input" maxlength="128" style="flex:1; min-width:140px;" placeholder="Optional text">
                                    <button id="notif-send" class="glow-btn compact">Send</button>
                                </div>
                            </div>
                        </div>
                        <!-- R14 §3 — macOS Notification Mirroring -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>macOS Notifications</h3>
                                <span class="status-pill" id="macnotif-status-pill">unknown</span>
                            </div>
                            <div class="card-body" style="display:flex; flex-direction:column; gap:12px;">
                                <p class="panel-hint" style="margin-top:0;">Mirror incoming macOS notifications onto the device. Uses a private SQLite DB that Apple does not document — see <code>docs/NOTIFICATIONS_SETUP.md</code> for tradeoffs.</p>
                                <label class="hc-toggle">
                                    <input type="checkbox" id="macnotif-toggle">
                                    <span id="macnotif-toggle-label">Mirror macOS notifications</span>
                                </label>
                                <div id="macnotif-detail" class="panel-hint" style="font-family: var(--font-mono); font-size: 11px;">
                                    Status: loading...
                                </div>
                                <details>
                                    <summary class="form-label" style="cursor:pointer; user-select:none;">Routing rules</summary>
                                    <p class="panel-hint" style="margin-top:6px;">Each rule maps a macOS app/bundle-id substring to a Divoom notification type. First match wins. Edit JSON; <em>Save</em> persists to <code id="macnotif-routing-path">~/.config/divoom-control/notification_routing.json</code> and hot-reloads.</p>
                                    <textarea id="macnotif-rules-json" class="text-input" rows="10" spellcheck="false" style="font-family: var(--font-mono); font-size: 11px; width: 100%; resize: vertical; min-height: 180px;"></textarea>
                                    <div style="display:flex; gap:8px; align-items:center; margin-top:6px;">
                                        <button id="macnotif-rules-save" class="glow-btn compact">Save</button>
                                        <button id="macnotif-rules-reset" class="glow-btn compact secondary">Reset to defaults</button>
                                        <span id="macnotif-rules-msg" class="panel-hint" style="font-size: 11px;"></span>
                                    </div>
                                </details>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 2. DIVOOM TAB -->
                <div class="settings-tab-content" id="settings-divoom">
                    <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 540px;">
                        <!-- Divoom Cloud -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Divoom Cloud</h3>
                            </div>
                            <div class="card-body">
                                <div class="form-group">
                                    <input type="email" id="settings-email" class="text-input" placeholder="Email Address">
                                </div>
                                <div class="form-group">
                                    <input type="password" id="settings-password" class="text-input" placeholder="Account Password">
                                </div>
                                <button id="save-creds-btn" class="glow-btn pulse-glow" style="display:inline-flex; align-items:center; justify-content:center;">
                                    <svg class="kare-icon" viewBox="0 0 16 16" style="margin-right: 6px;">
                                        <path d="M2,2 L11,2 L14,5 L14,14 L2,14 Z" fill="none" stroke="currentColor" stroke-width="2"/>
                                        <rect x="5" y="2" width="5" height="4" fill="none" stroke="currentColor" stroke-width="1"/>
                                        <rect x="7" y="3" width="1" height="2"/>
                                        <rect x="4" y="9" width="8" height="5" fill="none" stroke="currentColor" stroke-width="1.5"/>
                                    </svg>
                                    Save Credentials
                                </button>
                                <div id="divoom-cloud-status-box" style="margin-top: 15px; padding: 12px; border-radius: 6px; font-size: 12px; font-weight: 600; display: none; align-items: center; gap: 8px;"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 3. ROUTINES TAB (Round 6 — moved from Monthly Best, see
                     docs/PLANNING_ROUND5.md §3 Option B. Set-and-forget automation
                     lives here, not with the live channels. Naming: "Auto-Sync
                     Gallery" instead of "Hot-Channel Schedule" per user pick.) -->
                <div class="settings-tab-content" id="settings-routines">
                    <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 540px;">
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Auto-Sync Gallery</h3>
                            </div>
                            <div class="card-body">
                                <p class="panel-hint" style="margin-top: 0;">Automatically re-fetch and push the Divoom Cloud gallery to your devices on a schedule. Runs in the background while the app is open.</p>
                                <div class="form-group" style="display:flex; align-items:center; gap:10px; margin-bottom: 14px;">
                                    <label class="hc-toggle" style="margin:0;">
                                        <input type="checkbox" id="routines-auto-sync-enabled">
                                        <span>Enable auto-sync</span>
                                    </label>
                                </div>
                                <div class="form-group">
                                    <label class="form-label" style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom: 4px; display:block;">Sync every</label>
                                    <select id="routines-auto-sync-interval" class="custom-select" style="width:100%;">
                                        <option value="3600">1 hour</option>
                                        <option value="21600">6 hours</option>
                                        <option value="43200">12 hours</option>
                                        <option value="86400">24 hours</option>
                                        <!-- R15 §4: long-interval options for users who
                                             only want a weekly / monthly refresh of the
                                             Monthly Best gallery. -->
                                        <option value="604800">7 days</option>
                                        <option value="2592000">30 days</option>
                                    </select>
                                </div>
                                <div style="display:flex; align-items:center; gap:10px; margin-top: 14px;">
                                    <button id="routines-auto-sync-save" class="glow-btn" style="margin:0;">Save Schedule</button>
                                    <span id="routines-auto-sync-status" class="panel-hint"></span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 4. CONNECTIVITY TAB (Connectivity & Privacy legend moved here) -->
                <div class="settings-tab-content" id="settings-connectivity">
                    <h3 style="font-size:13px; margin-bottom:12px; color:rgba(255,255,255,0.6);">Connectivity & Privacy</h3>
                    <div class="connectivity-legend">
                        <div class="connectivity-legend-row">
                            <div class="connectivity-legend-badge" style="display:flex; align-items:center; gap:8px; width:120px; flex-shrink:0;">
                                <div class="transport-dot active" style="background:#3b82f6; color:#3b82f6; box-shadow:0 0 6px #3b82f6; width:8px; height:8px; border-radius:50%;"></div>
                                <span style="font-size:12px; font-weight:600; color:var(--text-main);">Bluetooth</span>
                            </div>
                            <div class="connectivity-legend-text">
                                <strong>Bluetooth</strong>
                                <span>100% local. Commands go directly to the device over Bluetooth. Nothing ever leaves your machine.</span>
                            </div>
                        </div>
                        <div class="connectivity-legend-row">
                            <div class="connectivity-legend-badge" style="display:flex; align-items:center; gap:8px; width:120px; flex-shrink:0;">
                                <div class="transport-dot active" style="background:#22c55e; color:#22c55e; box-shadow:0 0 6px #22c55e; width:8px; height:8px; border-radius:50%;"></div>
                                <span style="font-size:12px; font-weight:600; color:var(--text-main);">Local Network</span>
                            </div>
                            <div class="connectivity-legend-text">
                                <strong>Local Network</strong>
                                <span>100% local. Talks directly to the device's built-in HTTP server. No internet, no account. WiFi-capable devices only.</span>
                            </div>
                        </div>
                        <div class="connectivity-legend-row">
                            <div class="connectivity-legend-badge" style="display:flex; align-items:center; gap:8px; width:120px; flex-shrink:0;">
                                <div class="transport-dot active" style="background:#f59e0b; color:#f59e0b; box-shadow:0 0 6px #f59e0b; width:8px; height:8px; border-radius:50%;"></div>
                                <span style="font-size:12px; font-weight:600; color:var(--text-main);">Divoom Cloud</span>
                            </div>
                            <div class="connectivity-legend-text">
                                <strong>Divoom Cloud</strong>
                                <span>Sends commands to Divoom's servers. Required for: gallery browsing, clock face store, community features. Requires a Divoom account.</span>
                            </div>
                        </div>
                        <div class="connectivity-legend-row">
                            <div class="connectivity-legend-badge" style="display:flex; align-items:center; gap:8px; width:120px; flex-shrink:0;">
                                <div class="transport-dot active" style="background:#ef4444; color:#ef4444; box-shadow:0 0 6px #ef4444; width:8px; height:8px; border-radius:50%;"></div>
                                <span style="font-size:12px; font-weight:600; color:var(--text-main);">Public Cloud</span>
                            </div>
                            <div class="connectivity-legend-text">
                                <strong>Public Cloud</strong>
                                <span>Used for weather, stock prices, album art lookups. 3rd-party services — no Divoom account required. Data is anonymous.</span>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 5. APPEARANCE TAB -->
                <div class="settings-tab-content" id="settings-appearance">
                    <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 540px;">
                        <!-- Aesthetic Theme Mode -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Theme</h3>
                            </div>
                            <div class="card-body">
                                <div class="tabs-row theme-buttons" role="tablist" aria-label="Theme">
                                    <button class="tab-btn theme-mode-btn active" data-theme="dark" role="tab" aria-selected="true" title="Dark Mode">
                                        <svg class="kare-icon tab-icon" viewBox="0 0 16 16" aria-hidden="true">
                                            <path d="M12,2 C10,2 6,4 6,9 C6,13 9,14 12,14 C6,16 2,12 2,8 C2,4 6,2 12,2 Z" fill="currentColor"/>
                                        </svg>
                                        Dark
                                    </button>
                                    <button class="tab-btn theme-mode-btn" data-theme="light" role="tab" aria-selected="false" title="Light Mode">
                                        <svg class="kare-icon tab-icon" viewBox="0 0 16 16" aria-hidden="true">
                                            <circle cx="8" cy="8" r="3" fill="currentColor"/>
                                            <path d="M8,1 L8,3 M8,13 L8,15 M1,8 L3,8 M13,8 L15,8 M3,3 L4.5,4.5 M11.5,11.5 L13,13 M3,13 L4.5,11.5 M11.5,4.5 L13,3" stroke="currentColor" stroke-width="2"/>
                                        </svg>
                                        Light
                                    </button>
                                    <button class="tab-btn theme-mode-btn" data-theme="system" role="tab" aria-selected="false" title="System Auto">
                                        <svg class="kare-icon tab-icon" viewBox="0 0 16 16" aria-hidden="true">
                                            <rect x="1" y="2" width="14" height="10" rx="1" fill="none" stroke="currentColor" stroke-width="2"/>
                                            <rect x="6" y="12" width="4" height="2"/>
                                            <rect x="4" y="14" width="8" height="1"/>
                                        </svg>
                                        Auto
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
    `
};
