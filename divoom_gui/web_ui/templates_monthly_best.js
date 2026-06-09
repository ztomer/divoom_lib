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
                    <div class="card glass-card" style="display:flex; flex-direction:column; height: 100%;">
                        <div class="card-header flex-header">
                            <div class="gallery-select-actions" style="display:flex; align-items:center; gap:8px;">
                                <button id="gallery-select-all-btn" class="glow-btn compact wall-tool-btn" title="Select every image">Select All</button>
                                <button id="gallery-clear-btn" class="glow-btn compact wall-tool-btn" title="Deselect every image">Clear</button>
                            </div>
                            <div class="header-actions">
                                <select id="gallery-classify" class="custom-select small">
                                    <option value="18">Recommend</option>
                                    <option value="3">Cartoon</option>
                                    <option value="9">Creative</option>
                                    <option value="6">Nature</option>
                                </select>
                            </div>
                        </div>
                        <div class="card-body" style="flex:1; overflow:hidden; min-height:0; display:flex; flex-direction:column;">
                            <div class="gallery-grid" id="gallery-container" style="flex:1; overflow-y:auto; min-height:0; margin-bottom:12px;">
                                <div class="empty-list">Loading community gallery...</div>
                            </div>
                            <div class="gallery-actions" style="margin-top:auto; display:flex; gap:10px;">
                                <button id="batch-sync-btn" class="glow-btn" style="flex:1; margin:0;">Update Device</button>
                            </div>
                        </div>
                    </div>
                </div>
    `;
