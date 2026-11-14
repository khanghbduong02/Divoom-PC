# Divoom Times Gate — Theme Studio (project brief)

A designer-first replacement for the configuration-form approach used by existing
Times Gate tools. You design each of the five 128×128 panels visually, then push them
to the device over the local network.

Target: Times Gate only (5 × 128×128 LCD). Not Pixoo, not Times Frame.

---

## 1. Goals

1. **Design, don't configure.** Full-canvas editing with drag-and-drop layers, live
   preview, per-element colour/font/size.
2. **Presets that look finished.** Users should be able to pick a theme and press
   send within 60 seconds of first launch.
3. **Total layout freedom.** Any background (image / GIF / short video loop) plus any
   combination of PC metrics, graphs, text and clock elements, positioned anywhere.
4. **Runs anywhere, editable from a phone.** Local web app: one small executable, UI
   in the browser, same URL works from a phone on the same Wi-Fi.
5. **Never leaves the device blank.** Re-push automatically after reboots, network
   drops, or app restarts; one button to hand the screen back to Divoom's own faces.

### Non-goals for v1

- Cloud hosting of the editor itself (cannot reach a user's LAN — see §3).
- Logging into a Divoom account to browse the in-app gallery (§8).
- Multi-device scheduling, scenes, MQTT, Home Assistant (later, or never).
- Pixoo / Times Frame support.

---

## 2. Why a local web app rather than a hosted site

The device's HTTP API is only reachable on the local network. A public HTTPS page
cannot call `http://192.168.x.x` — browsers block private-network requests from public
origins, and mixed content is refused outright. So a hosted "just visit this URL" editor
is impossible without an agent running on the user's machine anyway.

**Therefore:** the product is a small local agent + browser UI.

- User installs one executable, launches it, it opens `http://localhost:8765`.
- The same URL is reachable from a phone on the same network (`http://<pc-ip>:8765`),
  behind a token, so the editor works on mobile with no separate app.
- A hosted website can still exist later for **sharing preset JSON files** only.

This also means one codebase covers Windows, macOS and Linux, since the UI is the
browser.

---

## 3. Architecture

```
[ Browser UI: canvas editor, presets, device setup ]
                     |  HTTP + WebSocket (localhost)
[ Local agent: rendering, sensors, device transport, scheduler ]
                     |  HTTP POST  (LAN)
[ Times Gate: 5 × 128×128 LCD ]
```

- **Agent**: Python 3.11+ (FastAPI + uvicorn) or Go/Rust if a single static binary is
  preferred. Python is faster to build and matches the ecosystem (Pillow for rendering,
  psutil for metrics).
- **UI**: React or Svelte, HTML canvas for the 128×128 preview (scaled up with
  nearest-neighbour so it reads like the real panel). Drag layers, snap to pixels.
- **Packaging**: PyInstaller folder/exe, plus an optional Docker image for NAS users.
- **Auth**: random token generated on first run, stored in the app data folder,
   required as `Authorization: Bearer` for anything other than the static page.
  Bind to `127.0.0.1` by default; an explicit "allow other devices" toggle binds
  `0.0.0.0` and warns that the UI is now visible on the LAN.
- **Storage**: one `config.json` + `media/` folder in `%APPDATA%\GateThemeStudio`.

---

## 4. Device protocol requirements (hard-won from existing tools)

- **Two hardware revisions, different endpoints:**
  - HW 400: `POST http://<ip>/post`
  - HW 402: `POST http://<ip>:9000/divoom_api`
  - The setup wizard must probe both and remember which one answered.
- **LocalToken**: newer firmware rejects local calls without an integer `LocalToken`
  in the request body (`{"error_code": "DeviceToken is err"}`). It is a number shown
  in the Divoom phone app under the device's settings. The wizard must accept it and
  inject it into every local call. Existing tools that omit it fail on these units.
- **Frame upload**: `Draw/SendHttpGif` with `PicData` = base64 JPEG, `PicWidth: 128`,
  `PicNum` = frame count (keep well under 60), `PicOffset` per frame, `LcdArray` =
  a length-5 mask selecting the panel(s).
- **PicID**: must be monotonically increasing per device. Send
  `Draw/ResetHttpGifId` at startup, increment from there, and reset before the
  firmware's frame cache fills (roughly 100 consecutive uploads). Oversized or
  repeated IDs leave the panel stuck on "loading".
- **Panel addressing** is per-panel for frames; some device commands want
  `LcdIndex` (0–4) instead. Keep both helpers.
- **Discovery**: `POST https://app.divoom-gz.com/Device/ReturnSameLANDevice` returns
  the device list (name, IP, MAC, DeviceId) — same call the official app makes. Fall
  back to a subnet probe of `<prefix>.1–254` asking `Channel/GetAllConf`.
- **Diagnostics are a feature**: on connection failure, report the distinction between
  *refused* (host reachable, nothing on that port → wrong revision/port), *timeout*
  (wrong IP, different network, device asleep), and *token error* (device answering
  but rejecting the request). Users must never see a raw stack trace.

### Rendering strategy

Render **the whole panel** in the agent and push it as one image. Do not use the
device's text commands for layout: they are single-line, fixed-height and per-command
quirky. Rendering app-side gives free positioning, arbitrary fonts, gradients, graphs
and icons.

- Canvas is 128×128; render at 128×128 with anti-aliasing off for the pixel look, or
  at 4× and downscale for smoother gauges. Ship 2–3 pixel bitmap fonts.
- A frame is ~6–10 KB JPEG, so 1 fps per panel is trivial on a LAN. Cap default
  refresh at 1–2 s and make it configurable.
- Skip sending a frame whose pixels are byte-identical to the last one sent.

---

## 5. Sensors

- **CPU/GPU temperature** on Windows needs a kernel-level reader. Use
  LibreHardwareMonitorLib (MIT, the same library every tool in this space uses) via
  its WMI namespace or the DLL. It requires elevation — ask once, or ship a small
  service, and be explicit in the UI about why.
- **GPU usage/temp**: NVML for NVIDIA, LibreHardwareMonitor for AMD/Intel.
- **CPU/RAM/disk/network**: psutil.
- **Unavailable metrics must render as a visible placeholder** (e.g. `--`), never as
  a wrong number or a crash.

---

## 6. Editor features

Per panel (0–4), independently:

- **Background layer**: image, GIF, or video. Video is converted to a short loop
  (target 8–12 s at ~5 fps, ≤ 40 frames). Fit modes: fit / crop / stretch. Optional
  panorama: one wide 640×128 image sliced across all five panels.
- **Layers** (any number, drag to position, snap to pixels):
  - Metric: CPU %, CPU temp, GPU %, GPU temp, VRAM, RAM, disk, net up/down, fan.
  - Widget renderers per metric: big number, horizontal bar, vertical bar, ring gauge,
    sparkline history (rolling 60 samples), thermometer, icon + value.
  - Text: static label, clock time, date.
  - Image/icon from a small bundled icon set.
- **Per-layer properties**: position, size, colour, font, decimals, unit suffix,
  label text, min/max for gauges.
- **Global panel properties**: background colour, padding, accent colour.
- **Live preview** at the true 128×128 geometry with the current sensor values.
- **Undo/redo**, duplicate a panel to another, copy layout between panels.

---

## 7. Presets (v1 ships six, all recolourable)

1. **NVIDIA HUD** — near-black, green accent, big temps, ring gauge for GPU.
2. **AMD Adrenalin** — dark charcoal, crimson accents, twin bars, sparkline.
3. **Minimal Mono** — white on black, huge numbers only, no chrome.
4. **Retro Terminal** — amber or green mono text, boxed layout, fake scanline.
5. **Synthwave Neon** — magenta/cyan, glow-style bars, gradient background.
6. **Divoom Pixel** — pastel pixel-art styling close to the official faces.

Each preset = a JSON theme: background reference, layer list, colours, fonts.
Users can export/import the JSON, so presets can be shared.

---

## 8. Known constraints to state in the UI

- **"Background from the Divoom app's gallery"** needs a Divoom account login
  (email/password → session token) to browse `GetImgLikeList` / `GetImgUploadList`
  and play via `Draw/SendRemote`. Recommend: v1 accepts a user file; add account
  import later only if users ask, and never store the password.
- **Only one controller per device.** Two apps fighting over the panels produces
  flicker. Detect and warn.
- **Device needs internet once** after boot before its local API comes up
  (cloud handshake via MQTT/HTTPS). If the LAN is isolated, nothing works.
- **Firmware varies.** Pin nothing, test against the user's unit, and always show the
  device's reply verbatim in a diagnostics pane.

---

## 9. Milestones

**M1 — transport proof (highest risk first)**
- Connection wizard: probe port 80 → 9000, ask for LocalToken, show the raw reply.
- Push a single test image to one panel. Success = a coloured square appears.

**M2 — MVP**
- Five panels, background image + up to 3 metric layers, big-number and bar widgets.
- Live preview, save/load, one preset. Manual "Send".

**M3 — comfort**
- Presets gallery, GIF/video backgrounds, panorama, sparkline + ring gauge, clock/date,
  per-layer colours and fonts, undo/redo.

**M4 — reliability**
- Tray icon, autostart, re-push after reboot/network loss, skip-identical frames,
  theme export/import, "hand back to Divoom face" button.

**M5 — extras (only if wanted)**
- Phone UI polish, Docker image, multiple devices, profile switch on game launch.

---

## 10. Acceptance checks

- Fresh machine, no config: wizard finds the device, one preset sent, visible on the
  hardware in under 2 minutes.
- Wrong port and wrong IP produce the two distinct, human-readable errors from §4.
- A device reboot recovers the layout without user action within one refresh cycle.
- A 40-frame looping background holds ~5 fps without stuck "loading" panels.
- CPU/GPU temps match what LibreHardwareMonitor's own UI reports.
- Phone on the same Wi-Fi can open the editor and change one colour.

---

## 11. Open questions

1. Windows-only for the agent in v1, or Mac/Linux too (UI is portable either way)?
2. Python + PyInstaller, or a single static Go/Rust binary?
3. Ship the sensor reader as an elevated helper service (install-time UAC) or run the
   whole app elevated (simpler, more intrusive)?
4. Is a public preset-sharing page wanted, or is JSON export enough?
