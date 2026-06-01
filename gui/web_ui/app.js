// Divoom Wall Dashboard Javascript Core Logic
// Hooks UI events directly to pywebview Python API bridge.

document.addEventListener("DOMContentLoaded", () => {
    
    // ── 1. FRAMELESS WINDOW TITLEBAR BUTTON BINDINGS ──
    const winMin = document.getElementById("win-min");
    const winMax = document.getElementById("win-max");
    const winClose = document.getElementById("win-close");

    if (winMin) {
        winMin.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.minimize_window();
            }
        });
    }
    if (winMax) {
        winMax.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.maximize_window();
            }
        });
    }
    if (winClose) {
        winClose.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.close_window();
            }
        });
    }

    // ── 2. TAB NAVIGATION ──
    const navButtons = document.querySelectorAll(".nav-btn");
    const tabContents = document.querySelectorAll(".tab-content");
    
    navButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            navButtons.forEach(b => b.classList.remove("active"));
            tabContents.forEach(t => t.classList.remove("active"));
            
            btn.classList.add("active");
            const targetTab = btn.getAttribute("data-tab");
            document.getElementById(targetTab).classList.add("active");
        });
    });
    
    // ── 2B. THEME SELECTOR WIRING ──
    const themeButtons = document.querySelectorAll(".theme-mode-btn");
    
    function applyTheme(theme) {
        document.body.classList.remove("theme-dark", "theme-light", "theme-system");
        document.body.classList.add(`theme-${theme}`);
        
        themeButtons.forEach(btn => {
            if (btn.getAttribute("data-theme") === theme) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });
        
        localStorage.setItem("aesthetic-theme", theme);
    }
    
    themeButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            const selectedTheme = btn.getAttribute("data-theme");
            applyTheme(selectedTheme);
        });
    });
    
    const savedTheme = localStorage.getItem("aesthetic-theme") || "dark";
    applyTheme(savedTheme);
    
    // ── 3. AMBIENT LIGHT SWATCHES ──
    const colorSwatches = document.querySelectorAll(".color-swatch");
    const customColorInput = document.getElementById("custom-color-input");
    let selectedColor = "00FFCC"; // Default
    
    colorSwatches.forEach(swatch => {
        swatch.addEventListener("click", () => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            swatch.classList.add("active");
            selectedColor = swatch.getAttribute("data-color");
        });
    });
    
    if (customColorInput) {
        customColorInput.addEventListener("input", (e) => {
            colorSwatches.forEach(s => s.classList.remove("active"));
            selectedColor = e.target.value.replace("#", "");
        });
    }
    
    // Brightness Slider
    const brightnessSlider = document.getElementById("brightness-slider");
    const brightnessVal = document.getElementById("brightness-val");
    if (brightnessSlider) {
        brightnessSlider.addEventListener("input", (e) => {
            brightnessVal.textContent = e.target.value;
        });
    }
    
    // Channel selection
    const channelCards = document.querySelectorAll(".channel-card");
    let activeChannel = "clock";
    
    channelCards.forEach(card => {
        card.addEventListener("click", () => {
            channelCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            activeChannel = card.getAttribute("data-channel");
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.switch_channel(activeChannel)
                    .then(res => {
                        if (res) showToast("Switched channel", "success", "🔵 BLE");
                        else showToast("Failed to switch channel", "error");
                    });
            }
        });
    });

    // Clock Face Previews
    const clockPreviewCards = document.querySelectorAll(".clock-preview-card");
    let selectedClockStyle = 0;
    clockPreviewCards.forEach(card => {
        card.addEventListener("click", () => {
            clockPreviewCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            selectedClockStyle = parseInt(card.getAttribute("data-style"));
        });
    });

    const applyClockBtn = document.getElementById("apply-clock-btn");
    if (applyClockBtn) {
        applyClockBtn.addEventListener("click", () => {
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_clock(selectedClockStyle)
                    .then(res => {
                        if (res) showToast("Clock style applied", "success", "🔵 BLE");
                        else showToast("Failed to apply clock", "error");
                    });
            }
        });
    }
    
    // Toast notifications
    function showToast(message, type = "success", transport = null) {
        const toast = document.getElementById("toast");
        toast.className = `toast ${type} show`;
        const transportSuffix = transport
            ? `<span class="toast-transport">${transport}</span>`
            : '';
        toast.innerHTML = message + transportSuffix;
        
        setTimeout(() => {
            toast.classList.remove("show");
        }, 3000);
    }
    
    // ── 4. FREE-FORM DRAG AND DROP CANVAS COORDINATOR ──
    let discoveredDevices = [];
    let assignedSlots = {}; // mac -> { x, y, width, height, size, name }
    
    const arrangerCanvas = document.getElementById("arranger-canvas");

    // Physical sizes specifications mapped to CSS dimensions (pixels)
    function getDeviceDimensions(name) {
        const lowerName = (name || "").toLowerCase();
        if (lowerName.includes("timoo")) {
            return { width: 110, height: 110, size: 16, image: "assets/timoo.png" };
        }
        if (lowerName.includes("ditoo")) {
            return { width: 90, height: 90, size: 16, image: "assets/ditoo.png" };
        }
        if (lowerName.includes("pixoo") && !lowerName.includes("64")) {
            return { width: 220, height: 220, size: 16, image: "assets/pixoo.png" };
        }
        if (lowerName.includes("pixoo") && lowerName.includes("64")) {
            return { width: 260, height: 260, size: 64, image: "assets/pixoo.png" }; // larger size
        }
        if (lowerName.includes("timebox") || lowerName.includes("evo")) {
            return { width: 100, height: 100, size: 16, image: "assets/timebox.png" };
        }
        return { width: 110, height: 110, size: 16, image: "assets/pixoo.png" }; // default fallback
    }

    function syncArrangerToPython() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.update_wall_slots(JSON.stringify(assignedSlots));
        }
    }

    function renderArrangerCanvas() {
        // Clear workspace
        arrangerCanvas.innerHTML = "";
        
        Object.keys(assignedSlots).forEach(mac => {
            const slot = assignedSlots[mac];
            const node = document.createElement("div");
            node.className = "arranger-node";
            node.style.left = `${slot.x}px`;
            node.style.top = `${slot.y}px`;
            node.style.width = `${slot.width}px`;
            node.style.height = `${slot.height}px`;
            
            node.innerHTML = `
                <div class="arranger-node-label">${slot.name}</div>
                <div class="arranger-node-mac">${mac}</div>
                <img src="${slot.image}" class="arranger-node-image" alt="node-mock">
                <div class="arranger-node-remove" data-mac="${mac}">×</div>
            `;
            
            // Absolute positioning dragging math handlers
            let isDragging = false;
            let startX, startY;
            let startLeft, startTop;
            
            node.addEventListener("mousedown", (e) => {
                if (e.target.classList.contains("arranger-node-remove")) {
                    const macToRemove = e.target.getAttribute("data-mac");
                    delete assignedSlots[macToRemove];
                    renderArrangerCanvas();
                    syncArrangerToPython();
                    e.stopPropagation();
                    return;
                }
                
                isDragging = true;
                node.classList.add("dragging");
                
                startX = e.clientX;
                startY = e.clientY;
                startLeft = parseInt(node.style.left) || 0;
                startTop = parseInt(node.style.top) || 0;
                
                e.preventDefault();
            });
            
            document.addEventListener("mousemove", (e) => {
                if (!isDragging) return;
                
                const deltaX = e.clientX - startX;
                const deltaY = e.clientY - startY;
                
                let newLeft = startLeft + deltaX;
                let newTop = startTop + deltaY;
                
                // Keep inside arranger boundary limits
                const maxLeft = arrangerCanvas.clientWidth - node.clientWidth;
                const maxTop = arrangerCanvas.clientHeight - node.clientHeight;
                
                newLeft = Math.max(0, Math.min(newLeft, maxLeft));
                newTop = Math.max(0, Math.min(newTop, maxTop));
                
                node.style.left = `${newLeft}px`;
                node.style.top = `${newTop}px`;
                
                // Update slots position cache
                assignedSlots[mac].x = newLeft;
                assignedSlots[mac].y = newTop;
            });
            
            document.addEventListener("mouseup", () => {
                if (isDragging) {
                    isDragging = false;
                    node.classList.remove("dragging");
                    syncArrangerToPython();
                }
            });
            
            arrangerCanvas.appendChild(node);
        });
    }

    // Add arranged Screen button click
    const addArrangerBtn = document.getElementById("add-arranger-screen-btn");
    if (addArrangerBtn) {
        addArrangerBtn.addEventListener("click", () => {
            if (discoveredDevices.length === 0) {
                showToast("Please scan Bluetooth devices first under Settings tab!", "error");
                return;
            }
            
            // Show assignments dropdown options prompt
            const options = discoveredDevices.map(d => `<option value="${d.address}">${d.name} (${d.address})</option>`).join("");
            
            const popup = document.createElement("div");
            popup.style.position = "fixed";
            popup.style.top = "50%";
            popup.style.left = "50%";
            popup.style.transform = "translate(-50%, -50%)";
            popup.style.background = "rgba(20, 24, 38, 0.98)";
            popup.style.border = "1px solid var(--secondary)";
            popup.style.borderRadius = "16px";
            popup.style.padding = "25px";
            popup.style.boxShadow = "0 10px 40px rgba(0,0,0,0.8)";
            popup.style.zIndex = "2000";
            popup.style.minWidth = "320px";
            popup.style.backdropFilter = "blur(15px)";
            
            popup.innerHTML = `
                <h3 style="font-family: var(--font-display); font-size:16px; margin-bottom:15px; color:#fff;">Add Screen to Arranger</h3>
                <select id="canvas-add-select" class="custom-select" style="width:100%; margin-bottom:15px;">
                    ${options}
                </select>
                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button id="canvas-add-cancel" class="glow-btn compact" style="background:rgba(255,255,255,0.05); color:#fff; box-shadow:none;">Cancel</button>
                    <button id="canvas-add-confirm" class="glow-btn compact" style="background:linear-gradient(135deg, var(--secondary), #7b2cbf); color:#fff; box-shadow:none;">Add Node</button>
                </div>
            `;
            
            document.body.appendChild(popup);
            
            document.getElementById("canvas-add-cancel").addEventListener("click", () => {
                popup.remove();
            });
            
            document.getElementById("canvas-add-confirm").addEventListener("click", () => {
                const addr = document.getElementById("canvas-add-select").value;
                popup.remove();
                
                if (assignedSlots[addr]) {
                    showToast("Device already placed on canvas!", "error");
                    return;
                }
                
                const dev = discoveredDevices.find(d => d.address === addr);
                const devName = dev ? dev.name : "Divoom Screen";
                const dims = getDeviceDimensions(devName);
                
                // Center node on placement
                const placementX = Math.round((arrangerCanvas.clientWidth - dims.width) / 2);
                const placementY = Math.round((arrangerCanvas.clientHeight - dims.height) / 2);
                
                assignedSlots[addr] = {
                    x: placementX,
                    y: placementY,
                    width: dims.width,
                    height: dims.height,
                    size: dims.size,
                    name: devName,
                    image: dims.image
                };
                
                renderArrangerCanvas();
                syncArrangerToPython();
                showToast("Device node added to arranger", "success");
            });
        });
    }

    // Clear Canvas
    const clearArrangerBtn = document.getElementById("clear-arranger-btn");
    if (clearArrangerBtn) {
        clearArrangerBtn.addEventListener("click", () => {
            assignedSlots = {};
            renderArrangerCanvas();
            syncArrangerToPython();
            showToast("Arranger canvas cleared", "success");
        });
    }
    
    // ── 5. BLE CONNECTION HELPER & SELECTOR POPULATION ──
    function connectDevice(name, address) {
        showToast(`Connecting to ${name}...`, "success");
        const statusDot = document.getElementById("global-status-dot");
        const statusText = document.getElementById("global-status-text");
        
        if (statusDot) statusDot.className = "status-indicator connecting";
        if (statusText) statusText.textContent = "Connecting...";
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.connect_single_device(address)
                .then(res => {
                    if (res) {
                        showToast(`Successfully connected to ${name}!`, "success");
                        if (statusDot) statusDot.className = "status-indicator connected";
                        if (statusText) statusText.textContent = `Connected: ${name}`;
                        
                        document.getElementById("banner-device-name").textContent = name;
                        document.getElementById("banner-device-mac").textContent = address;
                        
                        const dims = getDeviceDimensions(name);
                        document.getElementById("banner-device-image").src = dims.image;
                        document.getElementById("banner-device-res").textContent = `${dims.size}x${dims.size}`;
                        
                        const isSpeaker = name.toLowerCase().includes("timoo") || name.toLowerCase().includes("ditoo");
                        document.getElementById("banner-device-speaker").textContent = isSpeaker ? "Yes (Built-in)" : "No";
                        
                        const bannerSelect = document.getElementById("banner-device-select");
                        if (bannerSelect) bannerSelect.value = address;
                    } else {
                        showToast(`Failed to connect to ${name}`, "error");
                        if (statusDot) statusDot.className = "status-indicator disconnected";
                        if (statusText) statusText.textContent = "Disconnected";
                    }
                });
        }
    }

    let registeredLanDevices = [];

    function populateDeviceSelectors(devices) {
        const deviceListUl = document.getElementById("device-list");
        if (deviceListUl) {
            deviceListUl.innerHTML = "";
            if (devices.length === 0) {
                deviceListUl.innerHTML = `<li class="empty-list">No BLE screens found.</li>`;
            } else {
                devices.forEach(d => {
                    const li = document.createElement("li");
                    li.innerHTML = `
                        <span>${d.name}</span>
                        <span class="device-mac">${d.address}</span>
                    `;
                    li.addEventListener("click", () => {
                        connectDevice(d.name, d.address);
                    });
                    deviceListUl.appendChild(li);
                });
            }
        }
        updateDeviceSelectorDropdown();
    }

    function updateDeviceSelectorDropdown() {
        const bannerSelect = document.getElementById("banner-device-select");
        if (!bannerSelect) return;
        
        const currentMac = document.getElementById("banner-device-mac")?.textContent;
        bannerSelect.innerHTML = '<option value="">Select Screen...</option>';
        
        // Populate BLE devices
        discoveredDevices.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d.address;
            opt.textContent = `🔵 BLE: ${d.name} (${d.address})`;
            if (currentMac === d.address) opt.selected = true;
            bannerSelect.appendChild(opt);
        });
        
        // Populate Wi-Fi devices
        registeredLanDevices.forEach(d => {
            const opt = document.createElement("option");
            opt.value = `LAN:${d.ip}`;
            opt.textContent = `🟢 Wi-Fi: ${d.ip}`;
            if (currentMac === `LAN:${d.ip}`) opt.selected = true;
            bannerSelect.appendChild(opt);
        });
    }

    const bannerSelect = document.getElementById("banner-device-select");
    if (bannerSelect) {
        bannerSelect.addEventListener("change", (e) => {
            const addr = e.target.value;
            if (!addr) return;
            if (addr.startsWith("LAN:")) {
                const ip = addr.split("LAN:")[1];
                connectDevice(`Wi-Fi: ${ip}`, addr);
            } else {
                const dev = discoveredDevices.find(d => d.address === addr);
                const devName = dev ? dev.name : "Divoom Screen";
                connectDevice(devName, addr);
            }
        });
    }

    const scanBtn = document.getElementById("scan-btn");
    const scanSpinner = document.getElementById("scan-spinner");
    const deviceListUl = document.getElementById("device-list");
    
    if (scanBtn) {
        scanBtn.addEventListener("click", () => {
            const timeout = parseInt(document.getElementById("scan-timeout")?.value) || 15;
            const limit = parseInt(document.getElementById("scan-limit")?.value) || 0;

            if (scanSpinner) scanSpinner.style.display = "inline-block";
            scanBtn.disabled = true;
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.scan_devices_with_config(timeout, limit)
                    .then(devicesJson => {
                        if (scanSpinner) scanSpinner.style.display = "none";
                        scanBtn.disabled = false;
                        
                        const devices = JSON.parse(devicesJson);
                        discoveredDevices = devices;
                        populateDeviceSelectors(devices);
                        showToast(`Discovered ${devices.length} screens!`, "success");
                        renderArrangerCanvas(); 
                    });
            } else {
                if (scanSpinner) scanSpinner.style.display = "none";
                scanBtn.disabled = false;
                showToast("Web interface API unavailable.", "error");
            }
        });
    }
    
    // Light Controls Apply
    const applyLightBtn = document.getElementById("apply-light-btn");
    if (applyLightBtn) {
        applyLightBtn.addEventListener("click", () => {
            const brightness = brightnessSlider ? parseInt(brightnessSlider.value) : 100;
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.set_solid_light(selectedColor, brightness)
                    .then(res => {
                        if (res) showToast("Ambient light applied", "success", "🔵 BLE");
                        else showToast("Failed to apply ambient light", "error");
                    });
            }
        });
    }
    
    // Split and Push to Wall
    const applyWallArtBtn = document.getElementById("apply-wall-art");
    if (applyWallArtBtn) {
        applyWallArtBtn.addEventListener("click", () => {
            const path = document.getElementById("file-path-input").value.trim();
            const cellSize = 16; // default size
            
            if (!path) {
                showToast("Please provide a local file path!", "error");
                return;
            }
            
            if (Object.keys(assignedSlots).length === 0) {
                showToast("Please arrange at least one device on the canvas first!", "error");
                return;
            }
            
            showToast("Splitting image and syncing wall...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.apply_wall_image(path, cellSize)
                    .then(res => {
                        if (res) showToast("Synchronized display wall", "success", "🔵 BLE");
                        else showToast("Failed to split and push wall image", "error");
                    });
            }
        });
    }

    // Dynamic Live Preview for Split & Sync local GIF/PNG path input
    const filePathInput = document.getElementById("file-path-input");
    const filePreviewContainer = document.getElementById("file-preview-container");
    const filePreviewImg = document.getElementById("file-preview-img");

    if (filePathInput && filePreviewContainer && filePreviewImg) {
        const updatePreview = () => {
            const val = filePathInput.value.trim();
            if (val) {
                let src = val;
                if (!val.startsWith("http://") && !val.startsWith("https://") && !val.startsWith("file://") && !val.startsWith("data:")) {
                    if (val.startsWith("/")) {
                        src = "file://" + val;
                    } else {
                        src = "file:///" + val.replace(/\\/g, "/");
                    }
                }
                filePreviewImg.src = src;
                filePreviewContainer.style.display = "flex";
            } else {
                filePreviewImg.src = "";
                filePreviewContainer.style.display = "none";
            }
        };

        filePathInput.addEventListener("input", updatePreview);
        filePathInput.addEventListener("change", updatePreview);
    }
    
    // ── 6. CLOUD GALLERY WITH ANIMATED COVER PREVIEWS ──
    const galleryContainer = document.getElementById("gallery-container");
    let loadedArtworks = [];
    let selectedArtworkIndex = null;
    
    const loadGalleryBtn = document.getElementById("load-gallery-btn");
    if (loadGalleryBtn) {
        loadGalleryBtn.addEventListener("click", () => {
            const classify = parseInt(document.getElementById("gallery-classify")?.value || "18");
            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">Fetching public community gallery...</div>`;
            
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
                        loadedArtworks = artworks;
                        selectedArtworkIndex = null;
                        if (galleryContainer) galleryContainer.innerHTML = "";
                        
                        if (artworks.length === 0) {
                            if (galleryContainer) galleryContainer.innerHTML = `<div class="empty-list">No gallery items found for classification.</div>`;
                            return;
                        }
                        
                        artworks.forEach((art, idx) => {
                            const item = document.createElement("div");
                            item.className = "gallery-item";
                            
                            // Beautiful visual gif cover animation
                            const previewSrc = art.preview_url ? art.preview_url : "assets/pixoo.png";
                            
                            item.innerHTML = `
                                <div class="gallery-item-preview-box">
                                    <img src="${previewSrc}" alt="${art.name}">
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
                                selectedArtworkIndex = idx;
                            });
                            
                            if (galleryContainer) galleryContainer.appendChild(item);
                        });
                        
                        showToast("Gallery fetched", "success", "🟡 Cloud");
                    });
            }
        });
    }
    
    // Batch Sync Monthly Best to Grid Wall
    const batchSyncBtn = document.getElementById("batch-sync-btn");
    if (batchSyncBtn) {
        batchSyncBtn.addEventListener("click", () => {
            if (selectedArtworkIndex === null) {
                showToast("Please select an artwork from the gallery list first!", "error");
                return;
            }
            
            const artwork = loadedArtworks[selectedArtworkIndex];
            showToast(`Downloading and syncing '${artwork.name}'...`, "success");
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.batch_sync_artwork(JSON.stringify(artwork))
                    .then(res => {
                        if (res) showToast(`'${artwork.name}' synced`, "success", "🔵 BLE");
                        else showToast("Failed to batch sync artwork", "error");
                    });
            }
        });
    }

    // Live Widgets (macOS Music & Stocks Ticker)
    const musicSyncToggle = document.getElementById("music-sync-toggle");
    if (musicSyncToggle) {
        musicSyncToggle.addEventListener("change", (e) => {
            const enable = e.target.checked;
            const trackerStatus = document.getElementById("music-track-status");
            if (enable) {
                trackerStatus.classList.add("active");
                showToast("Enabled macOS Music track listener thread", "success");
            } else {
                trackerStatus.classList.remove("active");
                document.getElementById("music-track-name").textContent = "No Music Playing";
                document.getElementById("music-artist-name").textContent = "Spotify / Apple Music";
                showToast("Music synchronization stopped", "success");
            }

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.toggle_music_sync(enable);
            }
        });
    }

    // Poll live track info from backend every 3 seconds to update the UI
    setInterval(() => {
        if (musicSyncToggle && musicSyncToggle.checked && window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_current_track_info()
                .then(infoJson => {
                    if (infoJson) {
                        const info = JSON.parse(infoJson);
                        if (info && info.track) {
                            document.getElementById("music-track-name").textContent = info.track;
                            document.getElementById("music-artist-name").textContent = `${info.artist} (${info.source})`;
                            if (info.artwork_url) {
                                document.getElementById("music-cover-img").src = info.artwork_url;
                            }
                        }
                    }
                });
        }
    }, 3000);

    // Stock price submit
    const applyStockBtn = document.getElementById("apply-stock-btn");
    if (applyStockBtn) {
        applyStockBtn.addEventListener("click", () => {
            const symbol = document.getElementById("stock-symbol-input")?.value.trim().toUpperCase();
            if (!symbol) {
                showToast("Please enter a ticker symbol!", "error");
                return;
            }

            showToast(`Fetching Yahoo price data for ${symbol}...`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.apply_stock_ticker(symbol)
                    .then(resJson => {
                        if (resJson) {
                            const res = JSON.parse(resJson);
                            if (res.success) {
                                showToast(`Displaying ${symbol} price frame!`, "success", "🔴 Ext");
                                const priceMock = document.querySelector(".ticker-price-mock");
                                const arrowMock = document.querySelector(".ticker-arrow-mock");
                                const nameMock = document.querySelector(".ticker-name-mock");

                                if (nameMock) nameMock.textContent = symbol;
                                if (priceMock) priceMock.textContent = `$${res.price}`;
                                if (arrowMock) {
                                    arrowMock.textContent = res.change >= 0 ? "▲" : "▼";
                                    if (res.change >= 0) {
                                        arrowMock.style.color = "var(--secondary)";
                                    } else {
                                        arrowMock.style.color = "red";
                                    }
                                }
                            } else {
                                showToast(`Failed to fetch/display ${symbol}`, "error");
                            }
                        } else {
                            showToast("API return error", "error");
                        }
                    });
            }
        });
    }

    // Tab 5: Credentials Settings tab
    const saveCredsBtn = document.getElementById("save-creds-btn");
    if (saveCredsBtn) {
        saveCredsBtn.addEventListener("click", () => {
            const email = document.getElementById("settings-email").value.trim();
            const pwd = document.getElementById("settings-password").value.trim();

            if (!email || !pwd) {
                showToast("Email and Password are required!", "error");
                return;
            }

            showToast("Saving cloud credentials...", "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_credentials(email, pwd)
                    .then(res => {
                        if (res) {
                            showToast("Credentials configured & login cache generated!", "success");
                        } else {
                            showToast("Authentication failed. Please verify credentials.", "error");
                        }
                    });
            }
        });
    }

    // Load initial credentials & configurations from python backend on mount
    setTimeout(() => {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_config()
                .then(configJson => {
                    if (configJson) {
                        const conf = JSON.parse(configJson);
                        if (conf.email && document.getElementById("settings-email")) {
                            document.getElementById("settings-email").value = conf.email;
                        }
                        if (conf.timeout && document.getElementById("scan-timeout")) {
                            document.getElementById("scan-timeout").value = conf.timeout;
                        }
                        if (conf.limit && document.getElementById("scan-limit")) {
                            document.getElementById("scan-limit").value = conf.limit;
                        }
                        if (conf.slots) {
                            assignedSlots = conf.slots;
                            renderArrangerCanvas();
                        }
                    }
                });
            
            // Load preset listings
            window.pywebview.api.load_preset_names()
                .then(namesJson => {
                    if (namesJson) {
                        const names = JSON.parse(namesJson);
                        const select = document.getElementById("presets-select");
                        if (select) {
                            select.innerHTML = '<option value="">Load Preset...</option>';
                            names.forEach(name => {
                                const opt = document.createElement("option");
                                opt.value = name;
                                opt.textContent = name;
                                select.appendChild(opt);
                            });
                        }
                    }
                });
        }
    }, 1000);

    // Preset dropdown select event
    const presetsSelect = document.getElementById("presets-select");
    if (presetsSelect) {
        presetsSelect.addEventListener("change", (e) => {
            const name = e.target.value;
            if (!name) return;

            showToast(`Loading layout preset '${name}'...`, "success");
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.load_preset_by_name(name)
                    .then(slotsJson => {
                        if (slotsJson) {
                            assignedSlots = JSON.parse(slotsJson);
                            renderArrangerCanvas();
                            showToast(`Layout preset '${name}' applied!`, "success");
                        } else {
                            showToast("Failed to load layout slots from file", "error");
                        }
                    });
            }
        });
    }

    // Save Preset button click
    const savePresetBtn = document.getElementById("save-preset-btn");
    if (savePresetBtn) {
        savePresetBtn.addEventListener("click", () => {
            if (Object.keys(assignedSlots).length === 0) {
                showToast("No arranged screens to save!", "error");
                return;
            }

            const name = prompt("Enter a unique name for this screen wall layout preset:", "My Custom Wall");
            if (!name) return;

            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.save_preset(name, JSON.stringify(assignedSlots))
                    .then(res => {
                        if (res) {
                            showToast(`Saved wall layout preset '${name}'`, "success");
                            // Refresh selector options
                            window.pywebview.api.load_preset_names()
                                .then(namesJson => {
                                    if (namesJson) {
                                        const names = JSON.parse(namesJson);
                                        const select = document.getElementById("presets-select");
                                        if (select) {
                                            select.innerHTML = '<option value="">Load Preset...</option>';
                                            names.forEach(n => {
                                                const opt = document.createElement("option");
                                                opt.value = n;
                                                opt.textContent = n;
                                                select.appendChild(opt);
                                            });
                                        }
                                    }
                                });
                        } else {
                            showToast("Failed to save layout preset", "error");
                        }
                    });
            }
        });
    }

    // ── TRANSPORT STATUS POLLING (4-badge sidebar panel) ──────────────────
    function updateTransportPanel(status) {
        const transports = [
            { key: 'ble',      dotId: 'tr-ble-dot',   detailId: 'tr-ble-detail' },
            { key: 'lan',      dotId: 'tr-lan-dot',   detailId: 'tr-lan-detail' },
            { key: 'cloud',    dotId: 'tr-cloud-dot', detailId: 'tr-cloud-detail' },
            { key: 'external', dotId: 'tr-ext-dot',   detailId: 'tr-ext-detail' },
        ];
        transports.forEach(({ key, dotId, detailId }) => {
            const t = status[key];
            if (!t) return;
            const dot    = document.getElementById(dotId);
            const detail = document.getElementById(detailId);
            if (dot) {
                dot.className = `transport-dot ${t.available ? 'active' : 'inactive'}`;
            }
            if (detail && t.detail) {
                detail.textContent = t.detail;
            }
        });
    }

    function refreshTransportStatus() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.get_transport_status()
                .then(json => {
                    try { updateTransportPanel(JSON.parse(json)); } catch(e) {}
                })
                .catch(() => {});
        }
    }
    // Poll every 5 seconds
    setInterval(refreshTransportStatus, 5000);
    // Also fire once at startup after a short delay
    setTimeout(refreshTransportStatus, 1500);

    // ── Wi-Fi DEVICES MANAGER WIRING ──────────────────────────────────────
    function loadLanDevices() {
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_lan_devices()
                .then(json => {
                    try {
                        registeredLanDevices = JSON.parse(json);
                        renderLanDevicesList();
                        updateDeviceSelectorDropdown();
                    } catch(e) {
                        registeredLanDevices = [];
                    }
                });
        }
    }

    function renderLanDevicesList() {
        const ul = document.getElementById("lan-device-list");
        if (!ul) return;
        ul.innerHTML = "";
        if (registeredLanDevices.length === 0) {
            ul.innerHTML = '<li class="empty-list">No Wi-Fi screens registered.</li>';
            return;
        }
        registeredLanDevices.forEach(d => {
            const li = document.createElement("li");
            li.style.display = "flex";
            li.style.justifyContent = "space-between";
            li.style.alignItems = "center";
            li.innerHTML = `
                <span style="font-weight:600; cursor:pointer;">🟢 Wi-Fi Device (${d.ip})</span>
                <button class="glow-btn compact" style="margin:0; background:rgba(255, 68, 68, 0.15); border-color:#ef4444; color:#ef4444;" data-ip="${d.ip}">Delete</button>
            `;
            li.querySelector("span").addEventListener("click", () => {
                connectDevice(`Wi-Fi: ${d.ip}`, `LAN:${d.ip}`);
            });
            li.querySelector("button").addEventListener("click", (e) => {
                e.stopPropagation();
                const ip = e.target.getAttribute("data-ip");
                if (window.pywebview && window.pywebview.api) {
                    window.pywebview.api.delete_lan_device(ip)
                        .then(ok => {
                            if (ok) {
                                showToast("Deleted Wi-Fi device", "success");
                                loadLanDevices();
                            }
                        });
                }
            });
            ul.appendChild(li);
        });
    }

    const addLanBtn = document.getElementById("add-lan-btn");
    if (addLanBtn) {
        addLanBtn.addEventListener("click", () => {
            const ipInput = document.getElementById("lan-ip-input");
            const tokenInput = document.getElementById("lan-token-input");
            const probeResult = document.getElementById("lan-probe-result");
            
            const ip = (ipInput?.value || "").trim();
            const token = parseInt(tokenInput?.value || "0");
            if (!ip) { showToast("Enter an IP Address", "error"); return; }
            
            if (probeResult) { probeResult.textContent = "Connecting..."; probeResult.className = "lan-probe-result"; }
            
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.add_lan_device(ip, token)
                    .then(ok => {
                        if (ok) {
                            showToast(`Added Wi-Fi device: ${ip}`, "success");
                            if (probeResult) { probeResult.textContent = "Device registered successfully."; probeResult.className = "lan-probe-result success"; }
                            if (ipInput) ipInput.value = "";
                            if (tokenInput) tokenInput.value = "0";
                            loadLanDevices();
                        } else {
                            showToast("Failed to add Wi-Fi device", "error");
                            if (probeResult) { probeResult.textContent = "Could not register device."; probeResult.className = "lan-probe-result error"; }
                        }
                    });
            }
        });
    }

    // Load LAN config and devices on startup
    setTimeout(() => {
        loadLanDevices();
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.load_config()
                .then(() => {});
        }
    }, 1200);

    // ── 2C. SETTINGS SUB-TAB NAVIGATION ──
    const settingsTabButtons = document.querySelectorAll(".settings-tab-btn");
    const settingsTabContents = document.querySelectorAll(".settings-tab-content");

    settingsTabButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            settingsTabButtons.forEach(b => b.classList.remove("active"));
            settingsTabContents.forEach(t => t.classList.remove("active"));

            btn.classList.add("active");
            const targetSubTab = btn.getAttribute("data-settings-tab");
            document.getElementById(targetSubTab).classList.add("active");
        });
    });
    
});

