/* gallery_hot.js — R36b: device HOT channel update (split from gallery.js,
   500-LOC rule). The button stores Divoom's curated hot set into the
   device's hot rotation via the daemon's APK-equivalent hot_update flow. */
document.addEventListener("DOMContentLoaded", () => {
    const hotUpdateBtn = document.getElementById("hot-update-btn");
    if (hotUpdateBtn) {
        hotUpdateBtn.addEventListener("click", () => {
            if (hotUpdateBtn.disabled) return;
            if (window.requireDevice && !window.requireDevice()) return;
            const lbl = document.getElementById("hot-update-label");
            hotUpdateBtn.disabled = true;
            if (lbl) lbl.textContent = "Updating Hot Channel…";
            window.pywebview?.api?.hot_channel_update?.().then(json => {
                let r = {};
                try { r = JSON.parse(json); } catch (e) { /* fallthrough */ }
                hotUpdateBtn.disabled = false;
                if (lbl) lbl.textContent = "Update Hot Channel";
                if (r.success) {
                    const n = (r.served || []).length;
                    window.showToast(n ? `Hot channel updated (${n} file${n > 1 ? "s" : ""})`
                                       : "Hot channel already up to date", "success", " BLE");
                } else {
                    window.showToast(`Hot update failed: ${r.error || "unknown"}`, "error");
                }
            });
        });
    }
});
