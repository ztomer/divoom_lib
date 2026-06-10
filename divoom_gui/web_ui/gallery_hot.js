/* gallery_hot.js — device HOT channel update with in-button progress bar.
 * On tab activation the hot manifest is fetched automatically so the user
 * can see what Divoom's curated set contains before clicking the update
 * button. The button transforms into a progress bar during upload:
 *   - smooth animated fill with a readable status label
 *   - disabled + non-interactive while running
 *   - auto-resets after 3s on completion or failure
 * Rams: honest, self-explanatory, minimal. Kare: clear at a glance. */
document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("hot-update-btn");
    if (!btn) return;

    let _pollTimer = null;

    // ── Auto-fetch hot channel manifest on tab activation ──────────────
    window.addEventListener("tab-changed", (e) => {
        if (e.detail.tab === "hot-channel") loadHotPreview();
    });

    function loadHotPreview() {
        const list = document.getElementById("hot-preview-list");
        if (!list) return;

        window.pywebview?.api?.hot_update_preview?.().then(json => {
            let r;
            try { r = JSON.parse(json); } catch { r = {success: false}; }
            if (!r.success) {
                list.innerHTML = `<div class="hot-preview-empty">${r.error || "Could not load hot manifest"}</div>`;
                return;
            }
            renderHotPreview(r.items);
        });
    }

    function renderHotPreview(items) {
        const list = document.getElementById("hot-preview-list");
        if (!list) return;

        if (!items || items.length === 0) {
            list.innerHTML = '<div class="hot-preview-empty">No hot files available for this device.</div>';
            return;
        }

        // Tiles are image-only — the name/version live in the tooltip, so the
        // grid packs more art per row (Rams: omit the inessential).
        list.innerHTML = items.map((item, i) => {
            const name = item.name || item.file_id;
            return `<div class="hot-preview-item" title="${name} (v${item.version})">
                <img class="hot-preview-thumb" src="${item.preview_url || 'assets/pixoo.png'}"
                     alt="${name}" loading="lazy"
                     onerror="this.src='assets/pixoo.png'">
            </div>`;
        }).join("");

        // Lazy-load animated GIF previews for all hot channel items
        // (get_animated_preview handles download + decode from CDN on first access)
        items.forEach((item, i) => {
            if (item.file_id && window.pywebview?.api?.get_animated_preview) {
                const thumb = list.querySelectorAll(".hot-preview-thumb")[i];
                if (!thumb) return;
                window.pywebview.api.get_animated_preview(item.file_id).then(gifUrl => {
                    if (gifUrl) thumb.src = gifUrl;
                });
            }
        });
    }

    // ── Update button ───────────────────────────────────────────────────
    btn.addEventListener("click", () => {
        if (btn.disabled) return;
        if (window.requireDevice && !window.requireDevice()) return;

        const label = document.getElementById("hot-update-label");
        const wrap = document.getElementById("hot-progress-wrap");
        label.style.display = "none";
        wrap.style.display = "flex";
        btn.disabled = true;
        btn.classList.add("progress-active");

        window.pywebview?.api?.hot_channel_update?.().then(r => {
            _pollTimer = setInterval(pollProgress, 600);
        });
    });

    function pollProgress() {
        window.pywebview?.api?.hot_update_status?.().then(json => {
            let p;
            try { p = JSON.parse(json); } catch { return; }
            applyProgress(p);
            if (p.phase === "done" || p.phase === "error") {
                clearInterval(_pollTimer);
                _pollTimer = null;
                finishProgress(p);
            }
        });
    }

    function applyProgress(p) {
        const fill = document.getElementById("hot-progress-fill");
        const text = document.getElementById("hot-progress-text");
        if (!fill || !text) return;

        let pct = 0;
        let msg = "Starting\u2026";

        switch (p.phase) {
            case "starting":
                pct = 0;
                msg = "Preparing\u2026";
                break;
            case "fetching_manifest":
                pct = 2;
                msg = "Fetching list\u2026";
                break;
            case "downloading":
                pct = 5 + (p.current / p.total) * 45;
                msg = `Downloading ${p.current}/${p.total}`;
                break;
            case "uploading":
                pct = 50 + (p.current / p.total) * 48;
                msg = `Uploading ${p.current}/${p.total}`;
                break;
        }

        fill.style.width = `${Math.round(pct)}%`;
        text.textContent = msg;
    }

    function finishProgress(p) {
        const fill = document.getElementById("hot-progress-fill");
        const text = document.getElementById("hot-progress-text");

        if (p.phase === "done") {
            fill.style.width = "100%";
            const result = p.result || {};
            const n = (result.served || []).length;
            text.textContent = n ? `${n} file${n > 1 ? "s" : ""} updated` : "Up to date";
            fill.style.background = "linear-gradient(90deg, #166534, #22c55e)";
            btn.classList.remove("progress-active");
            btn.classList.add("progress-ok");
            window.showToast(
                n ? `Hot channel updated (${n} file${n > 1 ? "s" : ""})`
                   : "Hot channel already up to date",
                "success", " BLE");
        } else {
            fill.style.width = "100%";
            text.textContent = p.error ? `Failed: ${p.error}` : "Update failed";
            fill.style.background = "linear-gradient(90deg, #7f1d1d, #ef4444)";
            btn.classList.remove("progress-active");
            btn.classList.add("progress-fail");
            window.showToast(`Hot update failed: ${p.error || "unknown"}`, "error");
        }

        setTimeout(resetButton, 3000);
    }

    function resetButton() {
        const label = document.getElementById("hot-update-label");
        const wrap = document.getElementById("hot-progress-wrap");
        const fill = document.getElementById("hot-progress-fill");

        label.style.display = "";
        wrap.style.display = "none";
        if (fill) fill.style.width = "0%";
        btn.disabled = false;
        btn.classList.remove("progress-active", "progress-ok", "progress-fail");
    }
});
