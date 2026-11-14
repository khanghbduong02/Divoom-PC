# Gate Theme Studio

A designer-first editor for the **Divoom Times Gate** (5 × 128×128 LCD). Design each
panel visually in the browser; the app keeps the display updated over your LAN.

Local web app: one small Windows app + a browser UI. Same URL works from a phone on the
same Wi-Fi. The editor is served by the app on your PC, not by a hosted dashboard; the
only online piece is the static [download page](https://site-5b02d7b84842479d9d6e7cd6dfc76009.freebuff.page).
The device API is LAN-only (see [`divoom-theme-studio-brief.md`](divoom-theme-studio-brief.md)).

**Status:** milestones M1 (transport proof), M2 (MVP) and the always-on parts of M4
(tray, autostart, automatic re-push, frame skipping) are implemented.

---

## For users (no Python, no terminal)

You need one file: **`GateThemeStudio.exe`**. Download it from the
[public download page](https://site-5b02d7b84842479d9d6e7cd6dfc76009.freebuff.page)
or the [latest GitHub release](https://github.com/khanghbduong02/Divoom-PC/releases/latest/download/GateThemeStudio.exe).
The source checkout and exe build steps are below for development.

1. **Put it anywhere** you like — Desktop, Documents, a folder on `D:`. There is no
   installer and nothing else to download; the sensor helper is inside the exe.
2. **Double-click it.** Windows may show a blue *"Windows protected your PC"* box
   because the file is not code-signed: click **More info → Run anyway**. If Windows
   instead says the app can't run and nothing offers *Run anyway*, Smart App Control is
   blocking unsigned software — see [Smart App Control](#smart-app-control) below.
3. On the first run a small window offers to install the CPU temperature helper. Choose
   **Yes** and approve the one Windows administrator prompt. It installs the signed
   PawnIO sensor driver, turns on LibreHardwareMonitor's local sensor server, and starts
   it at every login. You can decline and use **Troubleshooting → Enable CPU temperature**
   later; everything except CPU temperature works either way.
4. The editor opens in your browser and a small icon appears in the notification area
   (bottom-right of the taskbar, possibly behind the `^` arrow).
5. **Connect the display** once:
   - Put the Times Gate on the same Wi-Fi as the PC and leave it powered on.
   - If probing fails, close the Divoom phone app while you set this up — the display can
     be holding its connection. After setup it can stay open.
   - In the editor press **Connect a display**, then **Find displays**, then pick the Gate
     that shows up. If it is not found, type the IP the Divoom app shows and press
     **Probe**.
   - That is permanent — the app reconnects by itself from then on.
6. **Design.** Pick a panel, choose a reading from the metric list and press
   **Add metric**, or **Add text** for a label. Drag things on the panel to move them,
   drag a corner to resize. Drag the dots next to a panel to reorder panels. Colours can
   be picked, typed as a `#RRGGBB` value, or chosen from the recent-colour swatches.
7. **Apply when you like it.** Edits are saved in the editor but do not touch the Gate
   until you press **Apply** in the right panel (that screen only) or **Send all** in the
   top bar (every edited panel). Panels with no layers and the default background are
   left untouched, so they cannot blank screens you have not designed yet. To clear one
   screen, select it and press **Apply** while it is empty. The design already on the Gate
   keeps its sensor readings live. Use **Save theme** in the top bar to keep all five
   panels, or **Save panel** in the inspector to keep one screen, then load either from
   its saved list later. Loading a saved design only changes the editor; press **Apply**
   or **Send all** to send it.

The app **starts with Windows** and keeps the display live. Closing the browser tab does
not stop it. To stop it for good, right-click the tray icon and choose **Quit Gate Theme
Studio** (or untick *Start with Windows* in **Settings**).

With the tray icon you can also: open the editor, send immediately, pause/resume all
updates, and open Settings.

**Use it from your phone:** Settings → *Let other devices on my network open the editor*
→ restart the app → open the phone address it prints. The link contains a key, so treat
it like a password. Only do this on a network you trust.

**Where your designs live:** `%APPDATA%\GateThemeStudio` (the exact path is shown in
Settings). Back up that folder to keep your themes; delete it to start clean.

**Uninstalling:** Quit from the tray, untick *Start with Windows*, delete the exe and the
data folder above. If you enabled CPU temperature, also delete
`%LOCALAPPDATA%\GateThemeStudio` and the `LibreHardwareMonitor` task (Task Scheduler →
Task Scheduler Library). The PawnIO driver can be removed from Apps & features if nothing
else uses it.

### Smart App Control

Windows 11's Smart App Control only runs apps it considers reputable, and an unsigned
exe built on your own PC has no reputation. If double-clicking shows a block with no
*Run anyway* option, either run from source (below) or turn Smart App Control off in
Windows Security → App & browser control. Be aware that Windows does not allow turning
it back on without reinstalling Windows, so decide deliberately. For handing the app to
other people, code-sign the exe; that is also what removes the SmartScreen prompt.

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

For copy-paste UI, API, exe and real-device checks, see
[`MANUAL_TESTING.md`](MANUAL_TESTING.md).

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

Output: `server/dist/GateThemeStudio.exe` (one file, ~34 MB, no Python needed on the
target PC). It contains the UI, previews, presets, LibreHardwareMonitor and the sensor
setup script, so the one-time CPU permission prompt works on a clean PC; user data stays
in `%APPDATA%`. Building requires the helper at `tools/LibreHardwareMonitor` (the build
stops with a download hint if it is missing).

The packaged build registers itself in `HKCU\...\CurrentVersion\Run` as
`"…\GateThemeStudio.exe" --silent` while *Start with Windows* is on (it is on by
default). A source checkout never edits the registry unless you flip the switch. The
sensor helper is different: it is a separate `LibreHardwareMonitor` task that Windows
starts elevated at login, so the app itself never needs to run as administrator.

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
  accent colour, **Theme for this panel only**, **Save panel** / **Saved panel designs**,
  **Pause updates for this screen**, **Remove all layers from this panel**. Per layer:
  metric, widget (big number or bar), position, size, colour, text sizing, decimals,
  unit, gauge min/max, alignment.
- **Toolbar** — choose a built-in or saved theme and press **Apply**; **Save theme** keeps
  the current five-panel draft for reuse; **Send all** forces an immediate update of the
  edited panels and skips empty ones; **Help** has the end-user guide; **Settings** controls
  updates, Divoom-app hand-off, autostart, network access and whether temperatures read
  **°C or °F** (all panels); **Troubleshooting** shows the last device reply verbatim.

Edits autosave to `config.json` as a draft; the display keeps the last applied design.
The update loop re-renders that applied design every 2 s (configurable) so sensor values
stay live, sends only panels whose pixels changed, retries after the display reboots,
and clears its cache once a minute so a display that was power-cycled still gets a fresh
frame. Draft changes reach the display only through **Apply** (one panel) or
**Send all**.

### When the Divoom app changes a screen

Leave the phone app open. Every few seconds the agent reads the Divoom-app layout from
Divoom's cloud. If the phone app puts a face on a screen, that screen gets a **paused**
badge and stops receiving frames, so the two apps cannot overwrite each other. Press
**Resume** in the inspector to hand it back, or **Apply** to take it back immediately;
**Send all** resumes every screen. **Pause updates for this screen** does the same
without waiting for the phone app.

No Divoom account is needed. The local API cannot read pixels or the current face back,
so this uses the app-side cloud state; changes another program makes only through the
local API are not visible unless that program signals the pause endpoint
(`POST /api/panels/<0-4>/pause` with the editor token). If the cloud is unreachable the
watch reports that and normal sending continues; paused screens stay paused until you
resume them. The watch and check interval are in **Settings → Other apps**.

## Metrics

| Metric | Source |
| --- | --- |
| CPU %, RAM %, disk %, network up/down | psutil |
| GPU % / temp / VRAM / fan | NVML (`nvidia-ml-py`), NVIDIA only |
| CPU temp, AMD/Intel GPU temp | LibreHardwareMonitor's local web server, if it is running |

Metrics the machine cannot supply render as `--`, never as a wrong number. Windows has
no unprivileged CPU-temperature API, so CPU temperature needs **LibreHardwareMonitor**
running as administrator with its local web server on (Options → Remote Web Server →
Run). The agent reads `http://127.0.0.1:8085/data.json` every two seconds. LibreHardwareMonitor
0.9.5+ also needs its signed **PawnIO** driver; older releases still expose WMI and are
read that way.

Troubleshooting → **Enable CPU temperature** does that setup once: it installs PawnIO
(through winget), turns the web server on, and registers LibreHardwareMonitor as an
elevated logon task, so it starts hidden at every login. Windows shows one administrator
prompt the first time. Without it everything else keeps working, and Troubleshooting
explains the missing reading with a download link. GPU temperatures come from NVML and
need no helper.

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
├── saved.json                  named full-theme and single-panel saves
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
├── library.py        named user saves (saved.json)
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

A CPU temperature stuck at `--` is not a display problem: open Troubleshooting and press
**Enable CPU temperature**, then approve the single Windows prompt. It installs
LibreHardwareMonitor's PawnIO driver, enables its local sensor server and starts it at
every login. Troubleshooting shows whether a sensor source was found.

Whatever the device replied is shown verbatim in the wizard and in **Troubleshooting**.

## Not in this milestone

- GIF and video backgrounds, panorama across five panels, sparkline and ring gauges,
  thermometer, undo/redo, per-panel copy (M3)
- Theme export/import UI, "hand back to Divoom face" (M4 remainder)
- Divoom account import of gallery backgrounds, multiple devices, Docker image (M5)

Also deliberately absent: any elevation prompt (temps degrade instead), and any cloud
component — a hosted page cannot reach a LAN device.
