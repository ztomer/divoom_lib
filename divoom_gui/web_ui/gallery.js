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
    // The gallery auto-loads on tab activation + on classify change. There is
    // no "Fetch Gallery" button (removed in R32 §A2). `loadGallery()` is the
    // canonical entry point and is exposed on `window` for tests + hooks.
    function readTargetSize() {
        const bannerResText = document.getElementById("banner-device-res")?.textContent || "16x16";
        if (bannerResText.includes("64")) return 64;
        if (bannerResText.includes("32")) return 32;
        return 16;
    }

    // ── Gallery style helpers (shared with routines) ──
    window.getGalleryStyle = function(prefix) {
        const tabs = document.getElementById(prefix + "-gallery-tabs");
        if (!tabs) return 18;
        const active = tabs.querySelector(".tab-btn.active");
        return parseInt(active?.getAttribute("data-style")) || 18;
    };
    window.setGalleryStyle = function(prefix, style) {
        const tabs = document.getElementById(prefix + "-gallery-tabs");
        if (!tabs) return;
        tabs.querySelectorAll(".tab-btn").forEach(b => {
            b.classList.toggle("active", b.getAttribute("data-style") === String(style));
        });
    };

    function loadGallery() {
        const classify = window.getGalleryStyle("gallery-classify");
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

    // R32 §A2: the gallery style is remembered per device in config.ini.
    function activeDeviceAddr() {
        return (document.getElementById("banner-device-mac")?.textContent || "").trim();
    }
    window.persistGalleryStyle = function(classify) {
        if (window.pywebview?.api?.set_gallery_style) {
            window.pywebview.api.set_gallery_style(activeDeviceAddr(), parseInt(classify) || 18);
        }
    };
    // Load the active device's preferred style into the dropdown. Returns a
    // promise so callers can fetch with the restored style applied.
    window.loadPreferredGalleryStyle = function() {
        if (window.pywebview?.api?.get_gallery_style) {
            return window.pywebview.api.get_gallery_style(activeDeviceAddr()).then(style => {
                if (style !== null && style !== undefined) window.setGalleryStyle("gallery-classify", style);
                return style;
            });
        }
        return Promise.resolve(18);
    };

    // R32 §A2: auto-fetch on classify (gallery style) change. Also persist
    // the chosen style as the preferred style for the active device.
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("#gallery-classify-tabs .tab-btn");
        if (!btn) return;
        document.querySelectorAll("#gallery-classify-tabs .tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        loadGallery();
        if (window.persistGalleryStyle) window.persistGalleryStyle(btn.getAttribute("data-style"));
    });

    // R32 §A3: each tile carries a selection checkbox (checked by default).
    // `buildGalleryItem` is the single source of tile markup for both the
    // bulk renderGallery() and the progressive onGalleryItemLoaded() paths.
    function buildGalleryItem(art, idx) {
        const item = document.createElement("div");
        item.className = "gallery-item";
        const previewSrc = art.preview_url ? art.preview_url : "assets/pixoo.png";
        item.innerHTML = `
                <input type="checkbox" class="gallery-item-check" checked title="Include this image">
                <div class="gallery-item-preview-box">
                    <img src="${previewSrc}" class="gallery-item-preview" alt="${art.name}">
                </div>
                <div class="gallery-item-info">
                    <h5>${art.name}</h5>
                    <span>️ ${art.likes}</span>
                </div>
            `;
        const check = item.querySelector(".gallery-item-check");
        // The checkbox carries the selection; clicking the tile toggles it.
        item.addEventListener("click", (e) => {
            if (e.target === check) return;
            check.checked = !check.checked;
            item.classList.toggle("selected", check.checked);
        });
        check.addEventListener("change", () => {
            item.classList.toggle("selected", check.checked);
        });
        item.classList.add("selected");
        item.dataset.idx = String(idx);
        return item;
    }

    // Checked artworks, in display order. Falls back to ALL loaded artworks
    // when the gallery has no checkbox DOM yet (e.g. before first render).
    window.getCheckedGalleryArtworks = function() {
        const arts = window.DivoomState.loadedArtworks || [];
        const checks = galleryContainer
            ? galleryContainer.querySelectorAll(".gallery-item-check")
            : [];
        if (!checks.length) return arts.slice();
        const out = [];
        checks.forEach((cb, i) => { if (cb.checked && arts[i]) out.push(arts[i]); });
        return out;
    };

    function setAllChecks(state) {
        if (!galleryContainer) return;
        galleryContainer.querySelectorAll(".gallery-item").forEach(item => {
            const cb = item.querySelector(".gallery-item-check");
            if (cb) cb.checked = state;
            item.classList.toggle("selected", state);
        });
    }

    const selectAllBtn = document.getElementById("gallery-select-all-btn");
    if (selectAllBtn) selectAllBtn.addEventListener("click", () => setAllChecks(true));
    const clearBtn = document.getElementById("gallery-clear-btn");
    if (clearBtn) clearBtn.addEventListener("click", () => setAllChecks(false));

    function renderGallery(artworks) {
        if (galleryContainer) galleryContainer.innerHTML = "";

        if (!artworks || artworks.length === 0) {
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">No gallery items found for classification.</div>`;
            return;
        }

        artworks.forEach((art, idx) => {
            const item = buildGalleryItem(art, idx);
            if (galleryContainer) {
                galleryContainer.appendChild(item);
                lazyLoadAnimatedPreview(item, art.file_id, idx);
            }
        });
    }

    // R32 §A3: "Update Device" pushes every CHECKED gallery image to the
    // currently-connected device (was: a single click-selected artwork).
    const batchSyncBtn = document.getElementById("batch-sync-btn");
    if (batchSyncBtn) {
        batchSyncBtn.addEventListener("click", () => {
            const checked = window.getCheckedGalleryArtworks();
            if (!checked.length) {
                window.showToast("Select at least one image first.", "error");
                return;
            }
            const fileIds = checked.map(a => a.file_id).filter(Boolean);
            window.showToast(`Pushing ${fileIds.length} image(s) to the device…`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.sync_hot_channel(JSON.stringify(fileIds)).then(json => {
                    try {
                        const r = JSON.parse(json);
                        if (r.ok) window.showToast(`Pushed ${r.synced.length} image(s)`, "success", " BLE");
                        else window.showToast(`Pushed ${r.synced.length}, ${r.failed.length} failed`, "error");
                    } catch (e) { window.showToast("Push failed", "error"); }
                    // R32 §C2: mirror the last pushed image as the device preview.
                    const last = checked[checked.length - 1];
                    const activeMac = (document.getElementById("banner-device-mac")?.textContent || "").trim();
                    if (last && last.preview_url && activeMac && window.setDevicePreview) {
                        window.setDevicePreview(activeMac, last.preview_url);
                    }
                });
            }
        });
    }

    // ── 2. MULTI-TARGET SYNC (Routines → "Sync devices now") ──
    // The button now lives in Settings → Routines (R32 §B); the handler stays
    // here so it shares the gallery selection state.
    const syncAllBtn = document.getElementById("sync-all-btn");
    if (syncAllBtn) {
        syncAllBtn.addEventListener("click", () => {
            const checked = window.getCheckedGalleryArtworks();
            if (!checked.length) {
                window.showToast("Open Monthly Best and select images first.", "error");
                return;
            }
            const fileIds = checked.map(a => a.file_id).filter(Boolean);
            window.showToast(`Syncing ${fileIds.length} image(s) to targets…`, "success");
            window.pywebview.api.sync_hot_channel(JSON.stringify(fileIds)).then(json => {
                try {
                    const r = JSON.parse(json);
                    if (r.ok) window.showToast(`Synced ${r.synced.length} image(s)`, "success", " BLE");
                    else window.showToast(`Synced ${r.synced.length}, ${r.failed.length} failed`, "error");
                } catch (e) { window.showToast("Sync failed", "error"); }
            });
        });
    }

    // ── 3. ROUTINE SYNC TARGETS (Settings → Routines device list) ──
    window.renderSyncTargets = function(candidates) {
        const el = document.getElementById("sync-targets-list");
        if (!el) return;
        if (!candidates || candidates.length === 0) {
            el.innerHTML = `<span class="empty-list">No devices — scan under Settings, or add a Wi-Fi screen.</span>`;
            return;
        }
        el.innerHTML = "";
        const styleNames = {18: "Recommend", 3: "Cartoon", 9: "Creative", 6: "Nature"};
        const styleOptions = [18, 3, 9, 6];
        candidates.forEach(c => {
            const row = document.createElement("div");
            row.className = "sync-device-row";
            row.style.cssText = "display:flex; align-items:center; gap:8px; padding:6px 0;";

            const color = window.deviceColor(c.address);
            const accent = document.createElement("span");
            accent.className = "device-accent-dot";
            accent.style.background = color;
            accent.style.boxShadow = `0 0 6px ${color}`;
            accent.style.marginRight = "4px";
            accent.style.flexShrink = "0";

            const name = document.createElement("span");
            name.className = "target-name";
            name.textContent = c.name;
            name.style.flex = "0 0 auto";

            // Per-device gallery style tabs.
            const styleTabs = document.createElement("div");
            styleTabs.className = "tabs-row";
            styleTabs.style.cssText = "flex:1; margin:0 8px;";
            styleTabs.setAttribute("role", "tablist");
            const currentStyle = c.gallery_style || 18;
            styleOptions.forEach(s => {
                const btn = document.createElement("button");
                btn.className = "tab-btn" + (s === currentStyle ? " active" : "");
                btn.textContent = styleNames[s];
                btn.setAttribute("data-style", s);
                btn.addEventListener("click", () => {
                    styleTabs.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    persistDeviceGallery(c.address, s);
                });
                styleTabs.appendChild(btn);
            });

            const toggle = document.createElement("label");
            toggle.className = "switch";
            toggle.style.margin = "0";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = c.address;
            cb.checked = !!c.selected;
            cb.addEventListener("change", persistSyncTargets);
            const slider = document.createElement("span");
            slider.className = "slider-round";
            toggle.append(cb, slider);

            row.append(accent, name, styleTabs, toggle);
            el.appendChild(row);
        });
    }

    function persistDeviceGallery(address, style) {
        // Gather all current gallery overrides and persist.
        const rows = document.querySelectorAll("#sync-targets-list .sync-device-row");
        const galleries = {};
        rows.forEach(row => {
            const cb = row.querySelector("input[type=checkbox]");
            if (!cb) return;
            const addr = cb.value;
            const active = row.querySelector(".tabs-row .tab-btn.active");
            if (active) {
                galleries[addr] = parseInt(active.getAttribute("data-style")) || 18;
            }
        });
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_sync_targets) {
            window.pywebview.api.set_sync_targets(
                JSON.stringify(Array.from(document.querySelectorAll("#sync-targets-list input:checked")).map(i => i.value)),
                JSON.stringify(galleries)
            );
        }
    }

    function persistSyncTargets() {
        const checked = Array.from(document.querySelectorAll("#sync-targets-list input:checked")).map(i => i.value);
        const rows = document.querySelectorAll("#sync-targets-list .sync-device-row");
        const galleries = {};
        rows.forEach(row => {
            const cb = row.querySelector("input[type=checkbox]");
            if (!cb) return;
            const addr = cb.value;
            const active = row.querySelector(".tabs-row .tab-btn.active");
            if (active) {
                galleries[addr] = parseInt(active.getAttribute("data-style")) || 18;
            }
        });
        if (window.pywebview && window.pywebview.api && window.pywebview.api.set_sync_targets) {
            window.pywebview.api.set_sync_targets(
                JSON.stringify(checked),
                JSON.stringify(galleries)
            );
        }
    }

    window.updateSyncTargetList = function() {
        if (window.pywebview && window.pywebview.api && window.pywebview.api.get_sync_candidates) {
            window.pywebview.api.get_sync_candidates().then(json => {
                try { window.renderSyncTargets(JSON.parse(json)); } catch (e) { /* ignore */ }
            });
        }
    }

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
            const currentIdx = window.DivoomState.loadedArtworks.length - 1;
            const item = buildGalleryItem(art, currentIdx);

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

    // Auto-fetch Monthly Best on tab activation. `loadGallery()` is
    // idempotent — a re-entry just refreshes from cache.
    window.addEventListener("tab-changed", (e) => {
        if (e.detail.tab === "monthly-best") loadGallery();
    });

    // Mount initializers. R32 §A2: restore the active device's preferred
    // gallery style before rendering the cached gallery on startup.
    setTimeout(() => {
        window.updateSyncTargetList();
        window.loadPreferredGalleryStyle().finally(() => window.loadCachedGalleryOnStartup());
    }, 1500);
});
