# Divoom Control Center: Next Phase Requirements & Design Council Review

This document captures the next phase requirements for the Divoom Control Center and presents a critical review by the Design Council (Steve Jobs, Dieter Rams, and Susan Kare) prior to implementation.

---

##  The Next Phase Requirements

### 1. Custom Art Channel
*   **Switching Channel Fix**: Investigate and repair why switching to the "Custom Art / Design" channel does not change the active channel correctly on the physical device.
*   **Duplicate Image & Gallery History**:
    *   Remove the duplicate display of the same image in both the preview box and the offline gallery cache grid.
    *   Extend the offline cache width so the content stretches all the way to the right.
    *   Change the cache section to display a history of the **last 5 selected/pushed items** (filmstrip cache).
*   **Ambient Mode Upgrades**:
    *   Replace static previews with loop-animated pixel previews for the 5 ambient lighting effects (Plain, Love, Plants, Sleeping, No Mosquitto).
    *   Remove the "Apply Ambient Color" button. Apply all swatches, custom colors, and ambient effect modes **immediately** upon selection.
    *   Unify the custom color picker with the preset color swatches into a single cohesive layout.

### 2. Monthly Best Gallery
*   **Restore Preview Animations**:
    *   Avoid static previews as the final state. Previews must be fully animated.
    *   Speed up the binary decoding/transcoding, or use a static first-frame image only as an intermediate step (progressive loading) before displaying the full animation.

### 3. Live Widgets
*   **Real Target Synchronization**: Connect the backend for all live widgets (Stocks, System Monitor) so they actually stream and synchronize their frames with the connected Divoom hardware in real-time.
*   **System Audio Loopback**:
    *   Do not capture from the microphone for the Winamp visualizer (microphone recording degrades visualizer responsiveness and captures ambient noise).
    *   Read frequencies directly from the macOS system audio output (loopback capture).
*   **Immediate Widget Activation**:
    *   Remove the "Enable Live Song Sync" toggle switch.
    *   Activate widget syncing immediately when the Live Widgets panel is loaded/selected.
*   **Layout Inversion (Preview on Top)**:
    *   Reorganize the widget cards to place the on-device preview at the top, and input selectors/buttons at the bottom.
    ```
    ┌──────────────────────────┐
    │     [ DEVICE PREVIEW ]   │
    ├──────────────────────────┤
    │     [ INPUT SELECTORS ]  │
    └──────────────────────────┘
    ```
*   **Notification Center Refactoring**:
    *   Remove simulated alerts (such as the Telegram outline clipping issue).
    *   Integrate actual system-level notifications (macOS alerts/ANCS), or remove the notifications widget card completely if OS integration is not feasible.
*   **Music Widget Label**: Rename "Mac playing cover track" to "Live cover art".

### 4. Navigation & Appbar
*   **Settings Navigation**: Move the "Settings" menu option to the very bottom of the sidebar panel.
*   **Appbar Connection Tooltips**: Repair the tooltips for connection transport status dots (BLE, LAN, Cloud, External) as they currently do not display on hover.

---

##  The Design Council Review

### 1. Steve Jobs (Focus, Simplicity, & Clarity)
> *"We must design with absolute focus. The Apply button on the Ambient tab was a crutch for slow engineering; removing it and applying changes immediately is the only right way. The same goes for the Music Sync toggle—why make the user click a switch after they've already navigated to the Music tab? Of course they want it synced!*
>
> *Moving the preview to the top of the cards is a major victory for clarity. Visual hierarchy must dictate that the output is king. If we cannot sync real macOS alerts, we must discard simulated alerts entirely. Real artists ship real features, not simulated toys. Repair the Appbar tooltips immediately; hidden information that remains unreadable is a failure."*

### 2. Dieter Rams (Braun Functionalism & Less, but Better)
> *"Unifying the color picker and swatches makes the layout honest and logical. A physical radio has its speaker or screen on top, with dials and inputs below. Inverting the widget cards to put previews on top matches this natural physical metaphor.*
>
> *Reading visualizer frequencies from system audio output rather than a microphone is crucial for technical honesty—microphone capture introduces ambient pollution and distorts the representation. Moving Settings to the bottom of the sidebar is correct; utility configuration should never compete with primary operational tasks."*

### 3. Susan Kare (Iconography & Pixel Usability)
> *"Pixel art must move. Restoring animations in the Monthly Best gallery is essential for visual delight. We can load a static first-frame instantly as a placeholder, but we must stream the animated GIF frames in the background. *
>
> *Displaying the same image twice in the Custom Art tab was a visual layout bug. Replacing that space with a visual history strip of the 'Last 5 Selected Items' (like a filmstrip) adds actual utility. The 5 ambient modes need loop-animated previews to make their retro effects instantly recognizable."*

---

## ️ Implementation Strategy & Technical Analysis

### A. Line Count Constraints (Strict < 500 LOC per file)
Before writing any code, we must ensure we stay well below the 500-line limit for files like [widgets.js](file:///Users/ztomer/Projects/divoom-control/gui/web_ui/widgets.js) (currently 409 lines) and [widgets.css](file:///Users/ztomer/Projects/divoom-control/gui/web_ui/widgets.css) (currently 451 lines).
*   **Widgets HTML/JS**: We will keep the JavaScript event handlers highly consolidated. Instead of verbose nested callbacks, we will delegate logic to shared backend APIs.
*   **Widgets CSS**: We will clean up unused CSS declarations (e.g., simulated notification alert styles, microphone-specific indicators) to keep the file under 500 lines.

### B. Custom Art Channel Mappings
*   *The Problem*: The Divoom protocol expects a specific channel-switching command code (`0x45`) with a payload representing the active screen index (e.g., `0x05` for custom design animation). Some devices reject it if sent while a previous drawing stream is active.
*   *The Solution*: Add protocol-level validation to clear/interrupt current active loops before executing a channel switch.

### C. macOS Audio Loopback (Virtual Sound Card)
*   *The Problem*: macOS has security restrictions blocking direct system-wide loopback capture unless a virtual audio device (like BlackHole) is installed.
*   *The Solution*:
    1.  Implement a loopback device scanner in Python.
    2.  If BlackHole/Loopback/Soundflower is found, bind to it.
    3.  If not, default back to default microphone input and output a warning/tip banner in the UI: *"To capture system sound directly, install the free BlackHole audio driver."*

### D. Layout Inversion
*   We will modify the grid templates in [templates.js](file:///Users/ztomer/Projects/divoom-control/gui/web_ui/templates.js) and [widgets.js](file:///Users/ztomer/Projects/divoom-control/gui/web_ui/widgets.js) to rearrange the HTML block structure:
    ```html
    <!-- Correct Physical Metaphor layout -->
    <div class="card-body">
        <div class="device-preview-wrap">...</div>
        <div class="card-controls">...</div>
    </div>
    ```
