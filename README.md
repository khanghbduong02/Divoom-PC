# Gate Theme Studio

A designer-first editor for the **Divoom Times Gate** (5 × 128×128 LCD). Design each
panel visually in the browser; the app keeps the display updated over your LAN.

Local web app: one small Windows app + a browser UI. Same URL works from a phone on the
same Wi-Fi. Nothing is hosted; the device API is LAN-only (see
[`divoom-theme-studio-brief.md`](divoom-theme-studio-brief.md)).

**Status:** milestones M1 (transport proof), M2 (MVP) and the always-on parts of M4
(tray, autostart, automatic re-push, frame skipping) are implemented.

---

## For users (no Python, no terminal)

You need one file: **`GateThemeStudio.exe`** (ask whoever built it for you, or build it
yourself with the steps below).

1. **Put it anywhere** you like — Desktop, Documents, a folder on `D:`. There is no
   installer and nothing else to download.
2. **Double-click it.** Windows may show a blue *"Windows protected your PC"* box
   because the file is not code-signed: click **More info → Run anyway**.
3. The editor opens in your browser and a small icon appears in the notification area
   (bottom-right of the taskbar, possibly behind the `^` arrow).
4. **Connect the display** once:
   - Put the Times Gate on the same Wi-Fi as the PC and leave it powered on.
   - **Close the Divoom phone app** while you set this up — the display only accepts one
     connection and the phone app holds it.
   - In the editor press **Connect a display**, then **Find displays**, then pick the Gate
     that shows up. If it is not found, type the IP the Divoom app shows and press
     **Probe**.
   - That is permanent — the app reconnects by itself from then on.
5. **Design.** Pick a panel, choose a reading from the metric list and press
   **Add metric**, or **Add text** for a label. Drag things on the panel to move them,
   drag a corner to resize. Drag the dots next to a panel to reorder panels.
6. **Nothing to save or send.** Edits are saved as you type and sent to the display
   within a couple of seconds. The **Send** button is only for an instant refresh.

The app **starts with Windows** and keeps the display live. Closing the browser tab does
not stop it. To stop it for good, right-click the tray icon and choose **Quit Gate Theme
Studio** (or untick *Start with Windows* in **Settings**).

With the tray icon you can also: open the editor, send immediately, pause/resume updates,
and open Settings.

**Use it from your phone:** Settings → *Let other devices on my network open the editor*
→ restart the app → open the phone address it prints. The link contains a key, so treat
it like a password. Only do this on a network you trust.

**Where your designs live:** `%APPDATA%\GateThemeStudio` (the exact path is shown in
Settings). Back up that folder to keep your themes; delete it to start clean.

**Uninstalling:** Quit from the tray, untick *Start with Windows*, delete the exe and the
data folder above. Nothing else is written to the system.

---

## For developers

### Requirements

- Windows, macOS or Linux
- Python 3.11+
- Node 20+ — only to build the UI bundle

### Install (once)

```bash
conda create -n divoom-studio python=3.13 -y
conda activate divoom-studio
pip install -r server/requirements.txt

cd ui && npm install && npm run build && cd ..
```

The UI build lands in `server/gate_studio/static/` (gitignored) and is served by the
agent. Rebuild it after any UI change.

### Run

```bash
cd server
python -m gate_studio
```

It prints the editor URL with a token, opens your browser, starts the update loop and
shows a tray icon. When no device is saved yet it also asks Divoom's discovery service
for Times Gates on this network.

```
Gate Theme Studio
  editor : http://localhost:8765/?token=...
  data   : C:\Users\you\AppData\Roaming\GateThemeStudio
  device : 192.168.68.51:9000 (hw402)
  updates: on, every 2s
```

Flags:

| Flag | Effect |
| --- | --- |
| `--port 8765` | HTTP port |
| `--lan` | also bind `0.0.0.0` so phones can connect (or use the Settings toggle) |
| `--silent` | no browser window (what Windows autostart uses) |
| `--no-browser` | print the URL but do not open a browser |
| `--no-tray` | run headless (for servers, CI, debugging) |
| `--no-discovery` | skip the startup LAN scan |
| `--data-dir <path>` | use another data folder |
| `--host <addr>` | explicit bind address |

The UI dev server is optional: `cd ui && npm run dev`. Or just rebuild and reload
`http://localhost:8765`.

### Test

```bash
cd server
python -m pytest
```

Covers transport (against a fake gate), renderer geometry, sensor collection, presets,
config migration and the HTTP/WebSocket API. No hardware or elevation needed.

Quick manual checks:

```bash
# headless API smoke test on another port
cd server
python -m gate_studio --no-tray --no-browser --port 8799 --data-dir ../build/test-data

# in another terminal
curl -H "Authorization: Bearer $(cat build/test-data/token)" http://127.0.0.1:8799/api/health
curl -H "Authorization: Bearer $(cat build/test-data/token)" http://127.0.0.1:8799/api/system
```

### Build the single-file Windows app

```bash
conda activate divoom-studio
pip install -r server/requirements.txt     # installs pyinstaller

cd ui && npm run build && cd ..
cd server
python build_exe.py
```

Output: `server/dist/GateThemeStudio.exe` (one file, ~27 MB, no Python needed on the
target PC). It contains the UI, previews and presets; user data stays in `%APPDATA%`.

The packaged build registers itself in `HKCU\...\CurrentVersion\Run` as
`"…\GateThemeStudio.exe" --silent` while *Start with Windows* is on (it is on by
default). A source checkout never edits the registry unless you flip the switch.

Smoke-test the build without touching the registry or the tray:

```bash
cd server
./dist/GateThemeStudio.exe --no-tray --no-browser --port 8799 --data-dir ../build/exe-data
```

Windows Firewall will ask once if you enable phone access. The exe is unsigned, so a
fresh machine shows a SmartScreen prompt.

### First run in 60 seconds (dev)

1. Open the URL the agent printed.
2. Apply a theme from the toolbar — *NVIDIA HUD*, *Minimal Mono* or *Retro Terminal* — to
   all five panels, or start empty.
3. **Connect a display** → **Scan network** (or type the IP) → **Probe ports** → add the
   **LocalToken** if your firmware needs one → **Send test tile**.
4. Tweak and watch the display update itself.

## Editing

- **Panel rail** — the five panels with live thumbnails. Drag the grip dots to reorder
  (works with mouse and touch); any panel can be left empty.
- **Stage** — the real 128×128 geometry, scaled to the window (and to a phone) without
  losing pixel snapping. Drag a layer to move it, drag a corner handle to resize it. Text
  and numbers fill their box unless you untick **Scale text to fit the box**.
- **Layers** — any number per panel; everything may live on one panel. Pick a metric
  from the list and press **Add metric**, or **Add text** for a label, clock or date.
  Reorder, hide or delete from the list. Each metric can be shown as the **value right
  now**, a **progress bar**, or a **line graph** of the past 5 minutes to 3 hours
  (history builds while the app runs).
- **Inspector** — per panel: background colour or image (fit / crop / stretch, dim),
  accent colour, **Theme for this panel only**, **Remove all layers from this panel**.
  Per layer: metric, widget (big number or bar), position, size, colour, text sizing,
  decimals, unit, gauge min/max, alignment.
- **Toolbar** — choose a theme and press **All panels**; **Send** forces an immediate
  update; **Help** has the end-user guide; **Settings** controls updates, autostart,
  network access and whether temperatures read **°C or °F** (all panels);
  **Troubleshooting** shows the last device reply verbatim.

Edits autosave to `config.json`. The update loop re-renders every 2 s (configurable),
sends only panels whose pixels changed, retries after the display reboots, and clears
its cache once a minute so a display that was power-cycled still gets a fresh frame.

## Metrics

| Metric | Source |
| --- | --- |
| CPU %, RAM %, disk %, network up/down | psutil |
| GPU % / temp / VRAM / fan | NVML (`nvidia-ml-py`), NVIDIA only |
| CPU temp, AMD/Intel GPU temp | LibreHardwareMonitor's WMI namespace, if it is running |

Metrics the machine cannot supply render as `--`, never as a wrong number. Windows has
no unprivileged CPU-temperature API, so CPU temperature needs **LibreHardwareMonitor**
(or OpenHardwareMonitor) running as administrator: the agent reads its
`root/LibreHardwareMonitor` WMI namespace and picks the reading up within 30 seconds.
Without it everything else keeps working, and Troubleshooting explains the missing
reading with a download link. GPU temperatures come from NVML and need no helper.
Nothing asks for elevation.

Temperatures are stored in Celsius and drawn in the unit chosen in Settings. A line
graph follows one metric over the selected window (5 min–3 h), keeps gaps where a
reading was unavailable, and marks the newest sample.

## Phone access

Settings → *Let other devices on my network open the editor* (or `--lan`), then restart.
The agent binds `0.0.0.0` and prints `http://<pc-ip>:8765/?token=...`. The token guards
the API, media and the preview socket; the static page itself is public.

## Data

One folder (override with `--data-dir` or `GATE_STUDIO_DATA_DIR`):

```
%APPDATA%\GateThemeStudio\      (macOS: ~/Library/Application Support/GateThemeStudio)
├── config.json                 device + settings + current theme (+ schema version)
├── token                       generated on first run
├── agent.log                   log of the last runs
└── media/                      uploaded background images
```

## How it works

```
Browser UI (React)  ──HTTP/WS──▶  Agent (FastAPI)  ──HTTP──▶  Times Gate
                                      ▲
                              update loop (2 s)
```

- **Rendering is server-side**: the whole 128×128 panel is drawn with Pillow, encoded as
  JPEG and pushed with `Draw/SendHttpGif`. The device's text commands are never used for
  layout, so what you design is exactly what it shows.
- **Two hardware revisions**: `POST http://<ip>/post` (HW 400) or
  `POST http://<ip>:9000/divoom_api` (HW 402). The wizard probes both.
- **LocalToken** is injected into every request body when set.
- **PicIDs** are monotonic per process, and `Draw/ResetHttpGifId` is sent at startup, so
  panels do not get stuck on "loading".
- **Panel addressing**: frames carry a length-5 `LcdArray` mask; single-panel commands
  use `LcdIndex`.
- **Always-on loop**: a background thread re-renders with fresh sensor values, compares
  the encoded bytes per panel and only sends what changed. A device error never kills it;
  it backs off and retries.
- **Single instance**: launching the exe again detects the running agent and just opens
  the editor instead of starting a second copy.
- **Autostart** is a per-user `Run` entry, so no admin rights are involved.

Key files:

```
server/gate_studio/
├── __main__.py       startup: single instance, HTTP thread, tray, autostart
├── api.py            REST + WebSocket + update scheduler
├── auth.py           bearer token gate
├── config.py         %APPDATA% storage, config.json, migration, media/
├── desktop.py        tray icon + start-with-Windows helpers
├── models.py         theme / panel / layer / device schema
├── presets.py        preset loader + presets/*.json
├── device/           transport, error taxonomy, discovery
├── render/           font, widgets, backgrounds, renderer
└── sensors/          psutil collector, NVML + LibreHardwareMonitor
server/build_exe.py   one-file PyInstaller build
server/run_agent.py   entry point used by the packaged app
ui/src/               React editor
```

## Device wizard errors

The three failure modes are reported separately, because each has a different fix:

| Kind | Meaning | Fix |
| --- | --- | --- |
| `refused` | Host reachable, port closed | Try the other port (80 = HW 400, 9000 = HW 402) |
| `timeout` | No reply | Wrong IP, other network, device asleep, or it never got internet after boot |
| `token` | Device answered, rejected the call | Add/correct the LocalToken |

A CPU temperature stuck at `--` is not a display problem: install LibreHardwareMonitor,
run it as administrator and leave it running. Troubleshooting shows whether a sensor
source was found.

Whatever the device replied is shown verbatim in the wizard and in **Troubleshooting**.

## Not in this milestone

- GIF and video backgrounds, panorama across five panels, sparkline and ring gauges,
  thermometer, undo/redo, per-panel copy (M3)
- Theme export/import UI, "hand back to Divoom face" (M4 remainder)
- Divoom account import of gallery backgrounds, multiple devices, Docker image (M5)

Also deliberately absent: any elevation prompt (temps degrade instead), and any cloud
component — a hosted page cannot reach a LAN device.
