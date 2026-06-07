/* gallery.js — Divoom Cloud community gallery fetcher and Monthly Best scheduling syncs */

document.addEventListener("DOMContentLoaded", () => {
    const galleryContainer = document.getElementById("gallery-container");

    function lazyLoadAnimatedPreview(item, fileId, index) {
        if (fileId && window.pywebview && window.pywebview.api && window.pywebview.api.get_animated_preview) {
            setTimeout(() => {
                window.pywebview.api.get_animated_preview(fileId).then(gifUrl => {
                    if (gifUrl) {
                        const img = item.querySelector(".gallery-item-preview");
                        if (img) img.src = gifUrl;
                    }
                });
            }, 50 * index);
        }
    }
    
    // ── 1. CLOUD GALLERY FETCH AND SYNC ──
    // R15 §2: the gallery now auto-loads on tab activation + on classify
    // change. The "Fetch Gallery" button is hidden (kept in the DOM as
    // a ghost for backwards compat) so the auto-fetch flow can still
    // .click() it from a single place. `loadGallery()` is the canonical
    // entry point and is also exposed on `window` for tests.
    function readTargetSize() {
        const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
        if (bannerResText.includes("64")) return 64;
        if (bannerResText.includes("32")) return 32;
        return 16;
    }

    function loadGallery() {
        const classify = parseInt(document.getElementById("gallery-classify")?.value || "18");
        if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">Fetching public community gallery...</div>`;
        window.DivoomState.loadedArtworks = [];
        window.DivoomState.selectedArtworkIndex = null;
        const targetSize = readTargetSize();
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.fetch_gallery(classify, targetSize)
                .then(artworksJson => {
                    const artworks = JSON.parse(artworksJson);
                    if (artworks.error) {
                        window.showToast(artworks.error, "error");
                        if (galleryContainer) {
                            galleryContainer.innerHTML = `<div class="empty-list" style="color:#ef4444; padding:20px; font-weight:600; text-align:center;">️ ${artworks.error}</div>`;
                        }
                        return;
                    }
                    window.DivoomState.loadedArtworks = artworks;
                    window.DivoomState.selectedArtworkIndex = null;
                    renderGallery(artworks);
                    window.showToast("Gallery loaded from cache", "success", " Cloud");
                });
        }
    }

    // Expose for tests + the auto-fetch hooks below.
    window.loadGallery = loadGallery;

    // The button is hidden in the UI (R15 §2) but is still in the DOM as
    // a ghost so existing click-style call sites in dev tools still work.
    const loadGalleryBtn = document.getElementById("load-gallery-btn");
    if (loadGalleryBtn) loadGalleryBtn.addEventListener("click", loadGallery);

    // R15 §2: auto-fetch on classify change.
    const classifySelect = document.getElementById("gallery-classify");
    if (classifySelect) classifySelect.addEventListener("change", loadGallery);

    function renderGallery(artworks) {
        if (galleryContainer) galleryContainer.innerHTML = "";
        
        if (!artworks || artworks.length === 0) {
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">No gallery items found for classification.</div>`;
            return;
        }
        
        artworks.forEach((art, idx) => {
            const item = document.createElement("div");
            item.className = "gallery-item";
            
            const previewSrc = art.preview_url ? art.preview_url : "assets/pixoo.png";
            
            item.innerHTML = `
                <div class="gallery-item-preview-box">
                    <img src="${previewSrc}" class="gallery-item-preview" alt="${art.name}">
                </div>
                <div class="gallery-item-info">
                    <h5>${art.name}</h5>
                    <span>️ ${art.likes}</span>
                </div>
            `;
            
            item.addEventListener("click", () => {
                const items = galleryContainer.querySelectorAll(".gallery-item");
                items.forEach(it => it.classList.remove("active"));
                item.classList.add("active");
                window.DivoomState.selectedArtworkIndex = idx;
            });
            
            if (galleryContainer) {
                galleryContainer.appendChild(item);
                lazyLoadAnimatedPreview(item, art.file_id, idx);
            }
        });
    }

    const batchSyncBtn = document.getElementById("batch-sync-btn");
    if (batchSyncBtn) {
        batchSyncBtn.addEventListener("click", () => {
            if (window.DivoomState.selectedArtworkIndex === null) {
                window.showToast("Please select an artwork from the gallery list first!", "error");
                return;
            }
            
            const artwork = window.DivoomState.loadedArtworks[window.DivoomState.selectedArtworkIndex];
            window.showToast(`Downloading and syncing '${artwork.name}'...`, "success");
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.batch_sync_artwork(JSON.stringify(artwork))
                    .then(res => {
                        if (res) window.showToast(`'${artwork.name}' synced`, "success", " BLE");
                        else window.showToast("Failed to batch sync artwork", "error");
                    });
            }
        });
    }

    // ── 2. MULTI-TARGET MONTHLY BEST SYNC ALL ──
    const syncAllBtn = document.getElementById("sync-all-btn");
    if (syncAllBtn) {
        syncAllBtn.addEventListener("click", () => {
            if (!window.DivoomState.loadedArtworks || window.DivoomState.loadedArtworks.length === 0) {
                window.showToast("Fetch the gallery first.", "error");
                return;
            }
            const fileIds = window.DivoomState.loadedArtworks.map(a => a.file_id).filter(Boolean);
            window.showToast(`Syncing ${fileIds.length} artworks to targets…`, "success");
            window.pywebview.api.sync_hot_channel(JSON.stringify(fileIds)).then(json => {
                try {
                    const r = JSON.parse(json);
                    if (r.ok) window.showToast(`Synced ${r.synced.length} artworks`, "success", " BLE");
                    else window.showToast(`Synced ${r.synced.length}, ${r.failed.length} failed`, "error");
                } catch (e) { window.showToast("Sync failed", "error"); }
            });
        });
    }

    // ── 3. AUTOMATED HOT-CHANNEL SCHEDULE ──
    window.renderSyncTargets = function(candidates) {
        const el = document.getElementById("sync-targets-list");
        if (!el) return;
        if (!candidates || candidates.length === 0) {
            el.innerHTML = `<span class="empty-list">No devices — scan under Settings, or add a Wi-Fi screen.</span>`;
            return;
        }
        el.innerHTML = "";
        candidates.forEach(c => {
            const row = document.createElement("label");
            row.className = "target-row";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = c.address;
            cb.checked = !!c.selected;
            cb.addEventListener("change", persistSyncTargets);
            
            const color = window.deviceColor(c.address);
            const accent = document.createElement("span");
            accent.className = "device-accent-dot";
            accent.style.background = color;
            accent.style.boxShadow = `0 0 6px ${color}`;
            accent.style.marginRight = "6px";
            
            const name = document.createElement("span");
            name.className = "target-name";
            name.textContent = c.name;
            // Round 6 (docs/PLANNING_ROUND5.md §3.b): drop the BT MAC
            // address from the target row. The address is already shown
            // in Settings → Bluetooth Scanner, and at 23% column width
            // the 17-char monospace string crowded the device name.
            row.append(cb, accent, name);
            el.appendChild(row);
        });
    }

    function persistSyncTargets() {
        const checked = Array.from(document.querySelectorAll("#sync-targets-list input:checked")).map(i => i.value);
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_sync_targets) {
            window.pywebview.api.set_sync_targets(JSON.stringify(checked));
        }
    }

    window.updateSyncTargetList = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_sync_candidates) {
            window.pywebview.api.get_sync_candidates().then(json => {
                try { window.renderSyncTargets(JSON.parse(json)); } catch (e) { /* ignore */ }
            });
        }
    }

    // R15 §2: the "Refresh" button on the Devices card was removed; the
    // list auto-refreshes on a 30s timer + on tab activation.
    // `updateSyncTargetList` is still exposed for callers that need a
    // manual refresh (e.g. settings.js).

    window.onGalleryItemLoaded = function(classify, targetSize, index, total, itemB64) {
        try {
            const currentClassify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            const currentTargetSize = readTargetSize();
            if (currentClassify !== classify || currentTargetSize !== targetSize) return;
            
            const rawJson = atob(itemB64);
            const art = JSON.parse(rawJson);
            
            if (index === 0) {
                if (galleryContainer) galleryContainer.innerHTML = "";
                window.DivoomState.loadedArtworks = [];
            }
            
            window.DivoomState.loadedArtworks.push(art);
            
            const item = document.createElement("div");
            item.className = "gallery-item";
            const previewSrc = art.preview_url ? art.preview_url : "assets/pixoo.png";
            
            item.innerHTML = `
                <div class="gallery-item-preview-box">
                    <img src="${previewSrc}" class="gallery-item-preview" alt="${art.name}">
                </div>
                <div class="gallery-item-info">
                    <h5>${art.name}</h5>
                    <span>️ ${art.likes}</span>
                </div>
            `;
            
            const currentIdx = window.DivoomState.loadedArtworks.length - 1;
            item.addEventListener("click", () => {
                const items = galleryContainer.querySelectorAll(".gallery-item");
                items.forEach(it => it.classList.remove("active"));
                item.classList.add("active");
                window.DivoomState.selectedArtworkIndex = currentIdx;
            });
            
            if (galleryContainer) {
                galleryContainer.appendChild(item);
                lazyLoadAnimatedPreview(item, art.file_id, currentIdx);
            }
        } catch (e) {
            console.error("Failed to render progressive gallery item:", e);
        }
    };

    window.onGalleryBackgroundFetched = function(classify, targetSize, b64Data) {
        try {
            const rawJson = atob(b64Data);
            const artworks = JSON.parse(rawJson);
            const currentClassify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            const currentTargetSize = readTargetSize();
            if (currentClassify === classify && currentTargetSize === targetSize) {
                window.DivoomState.loadedArtworks = artworks;
                window.DivoomState.selectedArtworkIndex = null;
                renderGallery(artworks);
                window.showToast("Gallery updated with latest monthly best! ", "success");
            }
        } catch (e) {
            console.error("Failed to process background gallery fetch:", e);
        }
    };

    window.loadCachedGalleryOnStartup = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.load_cached_gallery) {
            window.pywebview.api.load_cached_gallery().then(artworksJson => {
                if (artworksJson && artworksJson !== "[]") {
                    try {
                        const artworks = JSON.parse(artworksJson);
                        window.DivoomState.loadedArtworks = artworks;
                        window.DivoomState.selectedArtworkIndex = null;
                        renderGallery(artworks);
                    } catch (e) {
                        console.error("Failed to parse cached gallery on startup:", e);
                    }
                }
            });
        }
    };

    // R15 §2: Auto-fetch Monthly Best on tab activation.
    // `loadGallery()` is idempotent — if a fetch is already in flight
    // (or the list is non-empty), the fetch is still a no-op refresh,
    // which is the desired behavior on tab re-entry.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail.tab === "monthly-best") loadGallery();
    });

    // Mount initializers
    // Note: loadHotChannelSchedule was renamed to loadRoutinesAutoSync and
    // moved to settings.js. It loads on tab change / Routines sub-tab
    // click, so we don't pre-emptively call it here.
    setTimeout(() => {
        window.updateSyncTargetList();
        window.loadCachedGalleryOnStartup();
    }, 1500);
});
