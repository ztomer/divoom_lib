/* templates_routines.js — Routines panel (Schedule + Time) */
window.DivoomTemplates = window.DivoomTemplates || {};
window.DivoomTemplates.routines = `
        <div class="tabs-section" style="width:100%; box-sizing:border-box;">
        <div class="tabs-row" role="tablist" aria-label="Routines">
            <button class="tab-btn active" data-routines-tab="routines-schedule" data-tab="routines-schedule" role="tab" aria-selected="true"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2" width="12" height="12" rx="2" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M5 8L8 11L12 5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Schedule</button>
            <button class="tab-btn" data-routines-tab="routines-time" data-tab="routines-time" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5V8l2.5 1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Time</button>
        </div>
        </div>

        <!-- SCHEDULE sub-tab (ex-Settings → Routines) -->
        <div class="routines-subtab-content active" id="routines-schedule">
        <!-- Device rows are now just dot + name + toggle, so the card no longer
             needs the R34 760px width — 560px kills the dead middle space. -->
        <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 560px;">
            <div class="card glass-card">
                <div class="card-header flex-header">
                    <h3>Auto-Sync Gallery</h3>
                    <label class="switch">
                        <input type="checkbox" id="routines-auto-sync-enabled">
                        <span class="slider-round"></span>
                    </label>
                </div>
                <div class="card-body">
                    <div id="sync-targets-list" class="sync-targets-list" style="margin-bottom:14px;"></div>

                    <div style="margin-bottom:14px;">
                        <label class="form-label" style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:6px; display:block;">Sync every</label>
                        <div class="tabs-row" role="tablist" id="routines-interval-tabs">
                            <button class="tab-btn active" data-interval="3600">1h</button>
                            <button class="tab-btn" data-interval="21600">6h</button>
                            <button class="tab-btn" data-interval="43200">12h</button>
                            <button class="tab-btn" data-interval="86400">24h</button>
                            <button class="tab-btn" data-interval="604800">7d</button>
                            <button class="tab-btn" data-interval="2592000">30d</button>
                        </div>
                    </div>

                    <span id="routines-auto-sync-status" class="panel-hint" style="display:block; margin-top:8px;"></span>
                </div>
            </div>
        </div>
        </div>

        <!-- TIME sub-tab (ex-Tools → Time) -->
        <div class="routines-subtab-content" id="routines-time">
        <div class="grid-layout" style="grid-template-columns: 1fr; max-width: 600px;">
            <div class="card glass-card">
                <div class="card-header flex-header">
                    <h3>Alarms</h3>
                    <!-- R34 §4: table model — add/clear here, per-row remove, live writes. -->
                    <div class="row gap-8">
                        <button id="alarms-clear-btn" class="glow-btn compact" style="background:transparent; border:1px solid var(--secondary); color:var(--text-main); box-shadow:none;">Clear all</button>
                        <button id="alarms-add-btn" class="glow-btn compact">+ Add alarm</button>
                    </div>
                </div>
                <div class="card-body">
                    <p class="panel-hint" style="margin-top:0;">Changes are sent to the device immediately. Click a weekday cell to toggle it.</p>
                    <div id="alarms-list" class="alarms-list"></div>
                </div>
            </div>
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
    `;
