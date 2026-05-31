// Divoom Wall Dashboard Javascript Core Logic
// Hooks UI events directly to pywebview Python API bridge.

document.addEventListener("DOMContentLoaded", () => {
    
    // Tab Navigation
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
    
    // Ambient Light Swatches
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
    
    customColorInput.addEventListener("input", (e) => {
        colorSwatches.forEach(s => s.classList.remove("active"));
        selectedColor = e.target.value.replace("#", "");
    });
    
    // Brightness Slider
    const brightnessSlider = document.getElementById("brightness-slider");
    const brightnessVal = document.getElementById("brightness-val");
    brightnessSlider.addEventListener("input", (e) => {
        brightnessVal.textContent = e.target.value;
    });
    
    // Channel selection
    const channelCards = document.querySelectorAll(".channel-card");
    let activeChannel = "clock";
    
    channelCards.forEach(card => {
        card.addEventListener("click", () => {
            channelCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            activeChannel = card.getAttribute("data-channel");
            
            // Switch channel directly via python API
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.switch_channel(activeChannel)
                    .then(res => {
                        if (res) showToast("Switched channel successfully", "success");
                        else showToast("Failed to switch channel", "error");
                    });
            }
        });
    });
    
    // Toast notifications
    function showToast(message, type = "success") {
        const toast = document.getElementById("toast");
        toast.className = `toast ${type} show`;
        toast.textContent = message;
        
        setTimeout(() => {
            toast.classList.remove("show");
        }, 3000);
    }
    
    // Store discovered devices
    let discoveredDevices = [];
    // Store assigned slots mapping coordinates (x_y -> device_address)
    let assignedSlots = {};
    
    // Rebuild Display Wall grid slots
    const gridColsInput = document.getElementById("grid-cols");
    const gridRowsInput = document.getElementById("grid-rows");
    const wallGrid = document.getElementById("wall-grid");
    
    function rebuildGrid() {
        const cols = parseInt(gridColsInput.value) || 2;
        const rows = parseInt(gridRowsInput.value) || 2;
        
        wallGrid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
        wallGrid.innerHTML = "";
        
        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                const key = `${x}_${y}`;
                const cell = document.createElement("div");
                cell.className = "grid-cell";
                cell.setAttribute("data-x", x);
                cell.setAttribute("data-y", y);
                
                if (assignedSlots[key]) {
                    const dev = discoveredDevices.find(d => d.address === assignedSlots[key]);
                    const devName = dev ? dev.name : assignedSlots[key];
                    cell.classList.add("assigned");
                    cell.innerHTML = `
                        <div class="grid-cell-label">Slot [${x}, ${y}]</div>
                        <div class="grid-cell-device">${devName}</div>
                        <div class="grid-cell-remove" data-key="${key}">×</div>
                    `;
                } else {
                    cell.innerHTML = `
                        <div class="grid-cell-label">Slot [${x}, ${y}]</div>
                        <div class="grid-cell-device" style="opacity: 0.4;">Empty</div>
                    `;
                }
                
                // Clicking grid slot allows assigning a discovered device
                cell.addEventListener("click", (e) => {
                    if (e.target.classList.contains("grid-cell-remove")) {
                        const keyToRemove = e.target.getAttribute("data-key");
                        delete assignedSlots[keyToRemove];
                        rebuildGrid();
                        // Sync slots config to Python
                        if (window.pywebview && window.pywebview.api) {
                            window.pywebview.api.update_wall_slots(JSON.stringify(assignedSlots));
                        }
                        e.stopPropagation();
                        return;
                    }
                    
                    if (discoveredDevices.length === 0) {
                        showToast("Please scan Bluetooth devices first!", "error");
                        return;
                    }
                    
                    // Show assignment prompt
                    showAssignmentDialog(x, y);
                });
                
                wallGrid.appendChild(cell);
            }
        }
    }
    
    function showAssignmentDialog(x, y) {
        const key = `${x}_${y}`;
        // Simple HTML dropdown prompt inside toast overlay or browser prompt
        // To keep PyWebView clean without full dialog modal stylings, let's create a select menu dynamically
        const options = discoveredDevices.map(d => `<option value="${d.address}">${d.name}</option>`).join("");
        
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
        popup.style.minWidth = "280px";
        popup.style.backdropFilter = "blur(15px)";
        
        popup.innerHTML = `
            <h3 style="font-family: var(--font-display); font-size:16px; margin-bottom:15px; color:#fff;">Assign Device to [${x}, ${y}]</h3>
            <select id="assign-select" class="custom-select" style="width:100%; margin-bottom:15px;">
                ${options}
            </select>
            <div style="display:flex; gap:10px; justify-content:flex-end;">
                <button id="assign-cancel" class="glow-btn compact" style="background:rgba(255,255,255,0.05); color:#fff; box-shadow:none;">Cancel</button>
                <button id="assign-confirm" class="glow-btn compact" style="background:linear-gradient(135deg, var(--secondary), #7b2cbf); color:#fff; box-shadow:none;">Assign</button>
            </div>
        `;
        
        document.body.appendChild(popup);
        
        document.getElementById("assign-cancel").addEventListener("click", () => {
            popup.remove();
        });
        
        document.getElementById("assign-confirm").addEventListener("click", () => {
            const addr = document.getElementById("assign-select").value;
            assignedSlots[key] = addr;
            popup.remove();
            rebuildGrid();
            
            // Sync slots config to Python backend
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.update_wall_slots(JSON.stringify(assignedSlots));
            }
            showToast("Device assigned to grid slot", "success");
        });
    }
    
    document.getElementById("rebuild-grid-btn").addEventListener("click", rebuildGrid);
    rebuildGrid(); // Initial build
    
    // BLE Scanning
    const scanBtn = document.getElementById("scan-btn");
    const scanSpinner = document.getElementById("scan-spinner");
    const deviceListUl = document.getElementById("device-list");
    
    scanBtn.addEventListener("click", () => {
        scanSpinner.style.display = "inline-block";
        scanBtn.disabled = true;
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.scan_devices()
                .then(devicesJson => {
                    scanSpinner.style.display = "none";
                    scanBtn.disabled = false;
                    
                    const devices = JSON.parse(devicesJson);
                    discoveredDevices = devices;
                    deviceListUl.innerHTML = "";
                    
                    if (devices.length === 0) {
                        deviceListUl.innerHTML = `<li class="empty-list">No Divoom screens found in range.</li>`;
                        showToast("No BLE screens discovered.", "error");
                        return;
                    }
                    
                    devices.forEach(d => {
                        const li = document.createElement("li");
                        li.innerHTML = `
                            <span>${d.name}</span>
                            <span class="device-mac">${d.address}</span>
                        `;
                        
                        li.addEventListener("click", () => {
                            // Direct connect to device from list
                            showToast(`Connecting to ${d.name}...`, "success");
                            document.getElementById("global-status-dot").className = "status-indicator connecting";
                            document.getElementById("global-status-text").textContent = "Connecting...";
                            
                            window.pywebview.api.connect_single_device(d.address)
                                .then(res => {
                                    if (res) {
                                        showToast(`Successfully connected to ${d.name}!`, "success");
                                        document.getElementById("global-status-dot").className = "status-indicator connected";
                                        document.getElementById("global-status-text").textContent = `Connected: ${d.name}`;
                                    } else {
                                        showToast(`Failed to connect to ${d.name}`, "error");
                                        document.getElementById("global-status-dot").className = "status-indicator disconnected";
                                        document.getElementById("global-status-text").textContent = "Disconnected";
                                    }
                                });
                        });
                        
                        deviceListUl.appendChild(li);
                    });
                    
                    showToast(`Discovered ${devices.length} screens!`, "success");
                    rebuildGrid(); // Update list of available devices inside grid arranger dropdowns
                });
        } else {
            scanSpinner.style.display = "none";
            scanBtn.disabled = false;
            showToast("Web interface API unavailable.", "error");
        }
    });
    
    // Light Controls Apply
    document.getElementById("apply-light-btn").addEventListener("click", () => {
        const brightness = parseInt(brightnessSlider.value);
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_solid_light(selectedColor, brightness)
                .then(res => {
                    if (res) showToast("Ambient light applied successfully", "success");
                    else showToast("Failed to apply ambient light", "error");
                });
        }
    });
    
    // Clock Controls Apply
    document.getElementById("apply-clock-btn").addEventListener("click", () => {
        const style = parseInt(document.getElementById("clock-style-select").value);
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.set_clock(style)
                .then(res => {
                    if (res) showToast("Clock style applied", "success");
                    else showToast("Failed to apply clock", "error");
                });
        }
    });
    
    // Split and Push to Wall
    document.getElementById("apply-wall-art").addEventListener("click", () => {
        const path = document.getElementById("file-path-input").value.trim();
        const cellSize = parseInt(document.getElementById("grid-cell-size").value) || 16;
        
        if (!path) {
            showToast("Please provide a local file path!", "error");
            return;
        }
        
        if (Object.keys(assignedSlots).length === 0) {
            showToast("Please arrange at least one device on the grid first!", "error");
            return;
        }
        
        showToast("Splitting image & streaming quadrants...", "success");
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.display_wall_image(path, cellSize)
                .then(res => {
                    if (res) showToast("Display wall updated successfully!", "success");
                    else showToast("Failed to display image wall", "error");
                });
        }
    });
    
    // Tab 3: Fetch Gallery List
    const galleryContainer = document.getElementById("gallery-container");
    let loadedArtworks = [];
    let selectedArtworkIndex = null;
    
    document.getElementById("load-gallery-btn").addEventListener("click", () => {
        const classify = parseInt(document.getElementById("gallery-classify").value);
        galleryContainer.innerHTML = `<div class="empty-list">Fetching public community gallery...</div>`;
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.fetch_gallery(classify)
                .then(artworksJson => {
                    const artworks = JSON.parse(artworksJson);
                    loadedArtworks = artworks;
                    selectedArtworkIndex = null;
                    galleryContainer.innerHTML = "";
                    
                    if (artworks.length === 0) {
                        galleryContainer.innerHTML = `<div class="empty-list">No gallery items found for classification.</div>`;
                        return;
                    }
                    
                    artworks.forEach((art, idx) => {
                        const item = document.createElement("div");
                        item.className = "gallery-item";
                        item.innerHTML = `
                            <div class="gallery-item-name">${art.name}</div>
                            <div class="gallery-item-meta">
                                <span>Likes: ${art.likes}</span>
                                <span class="gallery-item-magic">Magic: ${art.magic}</span>
                            </div>
                        `;
                        
                        item.addEventListener("click", () => {
                            const items = document.querySelectorAll(".gallery-item");
                            items.forEach(it => it.classList.remove("selected"));
                            item.classList.add("selected");
                            selectedArtworkIndex = idx;
                        });
                        
                        galleryContainer.appendChild(item);
                    });
                    
                    showToast("Public gallery fetched successfully!", "success");
                });
        }
    });
    
    // Batch Sync Monthly Best to Grid Wall
    document.getElementById("batch-sync-btn").addEventListener("click", () => {
        if (selectedArtworkIndex === null) {
            showToast("Please select an artwork from the gallery list first!", "error");
            return;
        }
        
        const artwork = loadedArtworks[selectedArtworkIndex];
        showToast(`Downloading and syncing '${artwork.name}'...`, "success");
        
        if (window.pywebview && window.pywebview.api) {
            window.pywebview.api.batch_sync_artwork(JSON.stringify(artwork))
                .then(res => {
                    if (res) showToast(`Artwork '${artwork.name}' displayed!`, "success");
                    else showToast("Failed to batch sync artwork", "error");
                });
        }
    });
    
});
