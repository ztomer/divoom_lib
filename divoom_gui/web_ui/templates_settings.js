/* templates_settings.js — Settings panel template */
window.DivoomTemplates = window.DivoomTemplates || {};
window.DivoomTemplates.settings = `                <!-- R15 §1+§7: tab chrome is now .tabs-row + .tab-btn
                     (defined in tabs.css) — same active state as Channels and
                     Tools. The glass-card wrapper unifies appearance with
                     the Channels tab row, which sits inside a card header. -->
                <div class="tabs-section" style="width:100%; box-sizing:border-box;">
                <div class="tabs-row" role="tablist" aria-label="Settings">
                    <button class="tab-btn active" data-settings-tab="settings-devices" data-tab="settings-devices" role="tab" aria-selected="true"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="12" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M6 13.5h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Devices</button>
                    <button class="tab-btn" data-settings-tab="settings-divoom" data-tab="settings-divoom" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M5 12h6a3 3 0 0 0 .4-6A4 4 0 0 0 4 7a3 3 0 0 0 1 5z" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>Divoom</button>
                    <button class="tab-btn" data-settings-tab="settings-routines" data-tab="settings-routines" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8a4.5 4.5 0 0 1 7.5-3.3M12.5 8a4.5 4.5 0 0 1-7.5 3.3" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M11 3v2H9M5 13v-2h2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Routines</button>
                    <button class="tab-btn" data-settings-tab="settings-connectivity" data-tab="settings-connectivity" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5a7 7 0 0 1 10 0M5.5 11a3.5 3.5 0 0 1 5 0" fill="none" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="13" r="1" fill="currentColor"/></svg>Connectivity</button>
                    <button class="tab-btn" data-settings-tab="settings-appearance" data-tab="settings-appearance" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 2a6 6 0 0 1 0 12z" fill="currentColor"/></svg>Appearance</button>
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
                        <!-- R15 §3: the Notification + macOS Notifications cards
                             moved to Live Widgets (siblings of the Weather card)
                             so all "things the device can show right now" live
                             in one place. -->
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

                    <!-- R15 §5: MCP server (Model Context Protocol) — exposes
                         12 device-control tools over stdio JSON-RPC. Connect
                         Claude Desktop, Cursor, Cline, or Continue to control
                         the device with natural language. See docs/MCP_SERVER.md. -->
                    <div class="card glass-card" style="margin-top:18px;">
                        <div class="card-header flex-header">
                            <h3>MCP Server</h3>
                            <span class="status-pill" id="mcp-status-pill">stopped</span>
                        </div>
                        <div class="card-body" style="display:flex; flex-direction:column; gap:10px;">
                            <p class="panel-hint" style="margin:0;">Spawns <code>divoom-control mcp-server</code> as a subprocess. Point any MCP-compatible client at this machine's <code>divoom-control</code> binary; see <code>docs/MCP_SERVER.md</code> for setup.</p>
                            <div style="display:flex; gap:10px; align-items:center;">
                                <button id="mcp-start-btn" class="glow-btn">Start</button>
                                <button id="mcp-stop-btn" class="glow-btn secondary" disabled>Stop</button>
                                <span id="mcp-status-detail" class="panel-hint" style="font-family: var(--font-mono); font-size: 11px; margin-left:8px;">PID: --</span>
                            </div>
                            <pre id="mcp-log" class="panel-hint" style="font-family: var(--font-mono); font-size: 11px; max-height: 140px; overflow-y: auto; background: rgba(0,0,0,0.25); padding: 8px; border-radius: 4px; margin: 0; white-space: pre-wrap;">No log entries yet.</pre>
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
    `;
