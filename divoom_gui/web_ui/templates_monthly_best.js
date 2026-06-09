/* templates_monthly_best.js — Monthly Best / Gallery panel template

   R32 §A: the gallery is now a single full-width card.
   - §A1: the right-hand "Devices" card moved to Settings → Routines.
   - §A2: the gallery style dropdown sits where the old fetch button was
     (the button is gone — fetch auto-fires on style change and on tab
     activation). The dropdown also drives the per-device preferred style.
   - §A3: each gallery tile carries a selection checkbox (all checked by
     default). "Select All" / "Clear" (virtual-wall button styling) toggle
     them; the "Gallery" / "Divoom Cloud" header chrome is gone. */
window.DivoomTemplates = window.DivoomTemplates || {};
window.DivoomTemplates.monthlyBest = `                <div class="monthly-best-layout">
                    <div class="card glass-card" style="height: 100%;">
                        <div class="card-header flex-header">
                            <div class="gallery-select-actions row gap-8">
                                <button id="gallery-select-all-btn" class="gallery-select-btn" title="Select every image">Select All</button>
                                <button id="gallery-clear-btn" class="gallery-select-btn" title="Deselect every image">Clear</button>
                            </div>
                            <div class="header-actions">
                                <div class="tabs-row" role="tablist" id="gallery-classify-tabs" style="margin:0;">
                                    <button class="tab-btn active" data-style="18">Recommend</button>
                                    <button class="tab-btn" data-style="3">Cartoon</button>
                                    <button class="tab-btn" data-style="9">Creative</button>
                                    <button class="tab-btn" data-style="6">Nature</button>
                                </div>
                            </div>
                        </div>
                        <div class="card-body">
                            <div class="gallery-grid" id="gallery-container" style="flex:1; overflow-y:auto; min-height:0; margin-bottom:12px;">
                                <div class="empty-list">Loading community gallery...</div>
                            </div>
                            <div class="gallery-actions flex gap-10" style="margin-top:auto;">
                                <button id="batch-sync-btn" class="glow-btn" style="flex:1; margin:0;">
                                    <span id="batch-sync-label">Update Device</span>
                                    <span id="batch-sync-status" class="sync-status-text"></span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
    `;
