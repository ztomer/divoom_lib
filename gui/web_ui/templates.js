/* templates.js — House large HTML views as template strings to keep index.html under 500 LOC */

window.DivoomTemplates = {
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
                                <button id="load-gallery-btn" class="glow-btn compact">Fetch Gallery</button>
                            </div>
                        </div>
                        <div class="card-body" style="flex:1; overflow:hidden; min-height:0; display:flex; flex-direction:column;">
                            <!-- Dynamic Grid with preview covers -->
                            <div class="gallery-grid" id="gallery-container" style="flex:1; overflow-y:auto; min-height:0;">
                                <div class="empty-list">Click "Fetch Gallery" to load public artworks.</div>
                            </div>
                        </div>
                    </div>

                    <!-- Right: Sync Controls Card -->
                    <div class="card glass-card" style="display:flex; flex-direction:column;">
                        <div class="card-header flex-header">
                            <h3>Sync Targets &amp; Schedule</h3>
                            <button id="refresh-targets-btn" class="glow-btn compact ghost">Refresh</button>
                        </div>
                        <div class="card-body" style="overflow-y:auto;">
                            <!-- Sync targets (4.c): explicit device multi-select -->
                            <div class="hot-channel" style="margin-top: 0; padding-top: 0; border-top: none;">
                                <div id="sync-targets-list" class="sync-targets-list" style="margin-bottom: 12px;">
                                    <span class="empty-list">No devices — scan under Settings, or add a Wi-Fi screen.</span>
                                </div>

                                <div class="hc-actions">
                                    <button id="batch-sync-btn" class="glow-btn">Sync Selected Art</button>
                                    <button id="sync-all-btn" class="glow-btn secondary">Sync All → Targets</button>
                                </div>

                                <!-- Automatic hot-channel schedule (4.d) -->
                                <div class="hc-schedule">
                                    <div class="hc-label">Automatic Hot-Channel Schedule</div>
                                    <label class="hc-toggle">
                                        <input type="checkbox" id="hc-enabled"> Enable scheduled sync (runs headless)
                                    </label>
                                    <label class="slider-label">Sync every
                                        <select id="hc-interval" class="custom-select small">
                                            <option value="3600">1 hour</option>
                                            <option value="21600">6 hours</option>
                                            <option value="43200">12 hours</option>
                                            <option value="86400">24 hours</option>
                                        </select>
                                    </label>
                                    <button id="hc-save-schedule-btn" class="glow-btn compact">Save Schedule</button>
                                    <span id="hc-schedule-status" class="panel-hint"></span>
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
                            <h3>Mac playing cover track</h3>
                            <span class="active-indicator">● Active</span>
                        </div>
                        <div class="card-body">
                            <div class="music-tracker-card" id="music-track-status">
                                <div class="music-previews-container">
                                    <div class="music-cover-preview">
                                        <div class="cover-vinyl"></div>
                                        <img id="music-cover-img" src="assets/pixoo.png" alt="Vinyl Cover">
                                    </div>
                                    <div class="music-device-preview-wrap">
                                        <img id="music-device-preview" class="device-preview-img" alt="Device Preview" style="display:none;">
                                        <span class="hc-label">On Device</span>
                                    </div>
                                </div>
                                <div class="music-track-info">
                                    <h4 id="music-track-name">No Music Playing</h4>
                                    <p id="music-artist-name">Spotify / Apple Music</p>
                                    <!-- Winamp Retro pixelated spectrum visualizer -->
                                    <div class="winamp-visualizer">
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                        <div class="winamp-bar"><div class="winamp-fill"></div></div>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="toggle-control-bar" style="margin-top: 20px;">
                                <div class="toggle-control">
                                    <label class="switch">
                                        <input type="checkbox" id="music-sync-toggle">
                                        <span class="slider-round"></span>
                                    </label>
                                    <span style="font-weight: 500;">Enable Live Song Sync</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Stock Prices Widget -->
                    <div class="card glass-card" id="widget-card-stock">
                        <div class="card-header flex-header">
                            <h3>Live Stocks &amp; Crypto Tickers</h3>
                            <span class="active-indicator">● Active</span>
                        </div>
                        <div class="card-body">
                            <div class="form-group">
                                <div class="flex-row">
                                    <input type="text" id="stock-symbol-input" placeholder="Symbol e.g. AAPL, BTC-USD" class="text-input" value="BTC-USD">
                                    <button id="apply-stock-btn" class="glow-btn compact">Display</button>
                                    <button id="add-ticker-btn" class="glow-btn compact ghost">+ Save</button>
                                </div>
                            </div>

                            <div id="tickers-list" class="tickers-list"></div>

                            <div class="device-preview-wrap">
                                <span class="hc-label">On-device preview</span>
                                <img id="ticker-device-preview" class="device-preview-img" alt="" style="display:none;">
                            </div>

                            <div class="widget-preview-ticker" id="ticker-preview-box">
                                <div class="mini-canvas-view">
                                    <div class="ticker-arrow-mock">▲</div>
                                    <div class="ticker-price-mock">$64,285</div>
                                    <div class="ticker-name-mock">BTC</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- System Monitor -->
                    <div class="card glass-card" id="widget-card-sysmon">
                        <div class="card-header flex-header">
                            <h3>System Monitor</h3>
                            <span class="active-indicator">● Active</span>
                        </div>
                        <div class="card-body">
                            <div class="sysmon-readout">
                                <div class="sysmon-stat"><span class="sysmon-label">CPU</span><b id="sysmon-cpu">–</b></div>
                                <div class="sysmon-stat"><span class="sysmon-label">MEM</span><b id="sysmon-mem">–</b></div>
                                <div class="sysmon-stat"><span class="sysmon-label">BAT</span><b id="sysmon-bat">–</b></div>
                            </div>
                            <div class="device-preview-wrap">
                                <span class="hc-label">On-device preview</span>
                                <img id="sysmon-device-preview" class="device-preview-img" alt="" style="display:none;">
                            </div>
                            <div class="hc-actions">
                                <button id="sysmon-display-btn" class="glow-btn compact">Display on Device</button>
                                <label class="hc-toggle"><input type="checkbox" id="sysmon-live"> Live (5s)</label>
                            </div>
                        </div>
                    </div>

                    <!-- Notification Center Widget Card -->
                    <div class="card glass-card" id="widget-card-notif">
                        <div class="card-header flex-header">
                            <h3>Notification Center</h3>
                            <span class="active-indicator">● Active</span>
                        </div>
                        <div class="card-body">
                            <p class="panel-hint" style="margin-top: 0; margin-bottom: 12px;">Trigger simulated alerts or monitor incoming notifications on screen.</p>
                            
                            <div class="form-group">
                                <label class="form-label">Simulate App Alert</label>
                                    <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 8px;">
                                        <button class="glow-btn compact ghost notif-trigger-btn" data-app="Mail"><img src="assets/mail_pixel.png" style="width:14px; height:14px; vertical-align:middle; margin-right:4px; image-rendering:pixelated;">Mail</button>
                                        <button class="glow-btn compact ghost notif-trigger-btn" data-app="WhatsApp"><img src="assets/whatsapp_pixel.png" style="width:14px; height:14px; vertical-align:middle; margin-right:4px; image-rendering:pixelated;">WhatsApp</button>
                                        <button class="glow-btn compact ghost notif-trigger-btn" data-app="Telegram"><img src="assets/telegram_pixel.png" style="width:14px; height:14px; vertical-align:middle; margin-right:4px; image-rendering:pixelated;">Telegram</button>
                                    </div>
                            </div>
                            
                            <div class="device-preview-wrap">
                                <span class="hc-label">On-device preview</span>
                                <img id="notif-device-preview" class="device-preview-img" alt="" style="display:none;">
                            </div>
                        </div>
                    </div>
                </div>
    `,
    settings: `
                <!-- Settings Sub-Tabs Navigation -->
                <div class="settings-tabs-nav">
                    <button class="settings-tab-btn active" data-settings-tab="settings-devices">Devices</button>
                    <button class="settings-tab-btn" data-settings-tab="settings-divoom">Divoom</button>
                    <button class="settings-tab-btn" data-settings-tab="settings-appearance">Appearance</button>
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
                                            </tr>
                                        </thead>
                                        <tbody id="device-list">
                                            <tr><td colspan="2" class="empty-list">No Bluetooth screens found.</td></tr>
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
                                                <th>Action</th>
                                            </tr>
                                        </thead>
                                        <tbody id="lan-device-list">
                                            <tr><td colspan="3" class="empty-list">No Wi-Fi screens registered.</td></tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Connectivity & Privacy Legend -->
                    <div style="margin-top:24px;">
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

                <!-- 3. APPEARANCE TAB -->
                <div class="settings-tab-content" id="settings-appearance">
                    <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 540px;">
                        <!-- Aesthetic Theme Mode -->
                        <div class="card glass-card">
                            <div class="card-header">
                                <h3>Theme</h3>
                            </div>
                            <div class="card-body">
                                <div class="theme-buttons">
                                    <button class="theme-mode-btn active" data-theme="dark" title="Dark Mode">
                                        <svg class="kare-icon" viewBox="0 0 16 16" style="margin-right: 4px;">
                                            <path d="M12,2 C10,2 6,4 6,9 C6,13 9,14 12,14 C6,16 2,12 2,8 C2,4 6,2 12,2 Z" fill="currentColor"/>
                                        </svg>
                                        Dark
                                    </button>
                                    <button class="theme-mode-btn" data-theme="light" title="Light Mode">
                                        <svg class="kare-icon" viewBox="0 0 16 16" style="margin-right: 4px;">
                                            <circle cx="8" cy="8" r="3" fill="currentColor"/>
                                            <path d="M8,1 L8,3 M8,13 L8,15 M1,8 L3,8 M13,8 L15,8 M3,3 L4.5,4.5 M11.5,11.5 L13,13 M3,13 L4.5,11.5 M11.5,4.5 L13,3" stroke="currentColor" stroke-width="2"/>
                                        </svg>
                                        Light
                                    </button>
                                    <button class="theme-mode-btn" data-theme="system" title="System Auto">
                                        <svg class="kare-icon" viewBox="0 0 16 16" style="margin-right: 4px;">
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
