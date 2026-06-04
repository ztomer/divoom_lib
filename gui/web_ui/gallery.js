/* gallery.js — Divoom Cloud community gallery fetcher and Monthly Best scheduling syncs */

document.addEventListener("DOMContentLoaded", () => {
    const galleryContainer = document.getElementById("gallery-container");
    
    // ── 1. CLOUD GALLERY FETCH AND SYNC ──
    const loadGalleryBtn = document.getElementById("load-gallery-btn");
    if (loadGalleryBtn) {
        loadGalleryBtn.addEventListener("click", () => {
            const classify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">Fetching public community gallery...</div>`;
            window.DivoomState.loadedArtworks = [];
            window.DivoomState.selectedArtworkIndex = null;
            
            let targetSize = 16;
            const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
            if (bannerResText.includes("64")) {
                targetSize = 64;
            } else if (bannerResText.includes("32")) {
                targetSize = 32;
            }
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.fetch_gallery(classify, targetSize)
                    .then(artworksJson => {
                        const artworks = JSON.parse(artworksJson);
                        if (artworks.error) {
                            window.showToast(artworks.error, "error");
                            if (galleryContainer) {
                                galleryContainer.innerHTML = `<div class="empty-list" style="color:#ef4444; padding:20px; font-weight:600; text-align:center;">⚠️ ${artworks.error}</div>`;
                            }
                            return;
                        }
                        
                        window.DivoomState.loadedArtworks = artworks;
                        window.DivoomState.selectedArtworkIndex = null;
                        renderGallery(artworks);
                        window.showToast("Gallery loaded from cache", "success", "🟡 Cloud");
                    });
            }
        });
    }

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
                    <span>❤️ ${art.likes}</span>
                </div>
            `;
            
            item.addEventListener("click", () => {
                const items = galleryContainer.querySelectorAll(".gallery-item");
                items.forEach(it => it.classList.remove("active"));
                item.classList.add("active");
                window.DivoomState.selectedArtworkIndex = idx;
            });
            
            if (galleryContainer) galleryContainer.appendChild(item);
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
                        if (res) window.showToast(`'${artwork.name}' synced`, "success", "🔵 BLE");
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
                    if (r.ok) window.showToast(`Synced ${r.synced.length} artworks`, "success", "🔵 BLE");
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
            const addr = document.createElement("span");
            addr.className = "target-addr";
            addr.textContent = c.address;
            row.append(cb, accent, name, addr);
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

    const refreshTargetsBtn = document.getElementById("refresh-targets-btn");
    if (refreshTargetsBtn) refreshTargetsBtn.addEventListener("click", window.updateSyncTargetList);

    window.loadHotChannelSchedule = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_hot_channel_config) {
            window.pywebview.api.get_hot_channel_config().then(json => {
                try {
                    const cfg = JSON.parse(json);
                    const en = document.getElementById("hc-enabled");
                    const iv = document.getElementById("hc-interval");
                    const cl = document.getElementById("gallery-classify");
                    if (en) en.checked = !!cfg.enabled;
                    if (iv) iv.value = String(cfg.interval);
                    if (cl && cfg.classify != null) cl.value = String(cfg.classify);
                } catch (e) { /* ignore */ }
            });
        }
    }

    const hcSaveBtn = document.getElementById("hc-save-schedule-btn");
    if (hcSaveBtn) {
        hcSaveBtn.addEventListener("click", () => {
            const enabled = document.getElementById("hc-enabled")?.checked || false;
            const interval = parseInt(document.getElementById("hc-interval")?.value) || 3600;
            const classify = parseInt(document.getElementById("gallery-classify")?.value) || 18;
            window.pywebview.api.save_hot_channel_config(JSON.stringify({ enabled, interval, classify })).then(ok => {
                const st = document.getElementById("hc-schedule-status");
                if (st) st.textContent = ok ? (enabled ? "Saved — scheduled" : "Saved — disabled") : "Failed to save";
                window.showToast(ok ? "Schedule saved" : "Failed to save schedule", ok ? "success" : "error");
            });
        });
    }

    window.onGalleryItemLoaded = function(classify, targetSize, index, total, itemB64) {
        try {
            const currentClassify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            let currentTargetSize = 16;
            const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
            if (bannerResText.includes("64")) {
                currentTargetSize = 64;
            } else if (bannerResText.includes("32")) {
                currentTargetSize = 32;
            }
            
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
                    <span>❤️ ${art.likes}</span>
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
                
                const loadBtn = document.getElementById("load-gallery-btn");
                if (loadBtn) {
                    loadBtn.textContent = `Loading ${index + 1}/${total}...`;
                    if (index + 1 === total) {
                        loadBtn.textContent = "Fetch Gallery";
                    }
                }
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
            let currentTargetSize = 16;
            const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
            if (bannerResText.includes("64")) {
                currentTargetSize = 64;
            } else if (bannerResText.includes("32")) {
                currentTargetSize = 32;
            }
            
            if (currentClassify === classify && currentTargetSize === targetSize) {
                window.DivoomState.loadedArtworks = artworks;
                window.DivoomState.selectedArtworkIndex = null;
                renderGallery(artworks);
                window.showToast("Gallery updated with latest monthly best! 🟡", "success");
                const loadBtn = document.getElementById("load-gallery-btn");
                if (loadBtn) loadBtn.textContent = "Fetch Gallery";
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

    // Mount initializers
    setTimeout(() => {
        window.updateSyncTargetList();
        window.loadHotChannelSchedule();
        window.loadCachedGalleryOnStartup();
    }, 1500);
});
