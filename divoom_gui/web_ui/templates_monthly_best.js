/* templates_monthly_best.js — Monthly Best / Gallery panel template */
window.DivoomTemplates = window.DivoomTemplates || {};
window.DivoomTemplates.monthlyBest = `                <div class="monthly-best-layout">
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
    `;
