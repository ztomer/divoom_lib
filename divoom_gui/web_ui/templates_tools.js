/* templates_tools.js — Tools panel template */
window.DivoomTemplates = window.DivoomTemplates || {};
window.DivoomTemplates.tools = `
        <!-- R24 r2: tabs on a glass strip (.tabs-section), identical to Channels +
             Settings. Full-width to match the content cards below. -->
        <div class="tabs-section" style="width:100%; box-sizing:border-box;">
        <div class="tabs-row" role="tablist" aria-label="Tools">
            <button class="tab-btn active" data-tools-tab="tools-time" data-tab="tools-time" role="tab" aria-selected="true"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.5V8l2.5 1.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Time</button>
            <button class="tab-btn" data-tools-tab="tools-sessions" data-tab="tools-sessions" role="tab" aria-selected="false"><svg class="tab-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="9" r="5" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 9V6M6.5 2.5h3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>Sessions</button>
        </div>
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
                        <!-- FM Radio (moved into Tools, R11 item 8c). R24 #5: hidden
                             by default; shown only for FM-capable models on connect. -->
                        <div class="card glass-card" id="fm-radio-card" style="display:none;">
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
    `;
