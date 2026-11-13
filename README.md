# Gate Theme Studio

A designer-first editor for the **Divoom Times Gate** (5 × 128×128 LCD). Design each
panel visually in the browser, then push it to the device over your LAN.

Local web app: one Python agent + a browser UI. Same URL works from a phone on the
same Wi-Fi. Nothing is hosted; the device API is LAN-only (see
[`divoom-theme-studio-brief.md`](divoom-theme-studio-brief.md)).

**Status:** milestones M1 (transport proof) and M2 (MVP) are implemented.
M3–M5 are listed at the end.

---

## Requirements

- Windows, macOS or Linux
- Python 3.11+
- Node 20+ — only to build the UI bundle

## Install

```bash
conda create -n divoom-studio python=3.13 -y
conda activate divoom-studio
pip install -r server/requirements.txt

cd ui && npm install && npm run build && cd ..
```

The UI build lands in `server/gate_studio/static/` and is served by the agent.

## Run

```bash
cd server
python -m gate_studio
```

It prints the editor URL with a one-time `?token=`, opens your browser, and (when no
device is saved yet) asks Divoom's discovery service for Times Gates on this network.

```
Gate Theme Studio
  editor : http://localhost:8765/?token=...
  data   : C:\Users\you\AppData\Roaming\GateThemeStudio
  device : not configured — use the connection wizard in the editor
```

Useful flags: `--port`, `--no-browser`, `--no-discovery`, `--data-dir <path>`, and
`--lan` (see [phone access](#phone-access)).

## First run in 60 seconds

1. Open the URL the agent printed.
2. Pick a theme in the toolbar — *NVIDIA HUD*, *Minimal Mono* or *Retro Terminal* —
   or choose one from the cards shown on an empty panel.
3. Click **Connect device** and follow the wizard:
   - **Scan network**, or type the IP the Divoom app shows for the device.
   - **Probe ports 80 and 9000** — the wizard reports which hardware revision
     answered and shows the device's raw reply.
   - Enter the **LocalToken** if your firmware needs one (Divoom app → device
     settings → the number). Leave empty otherwise.
   - **Send test tile** — a numbered, framed square should appear on that panel.
4. Press **Send to device**.

## Editing

- **Panel rail** — the five panels, with live thumbnails rendered by the agent.
- **Stage** — the real 128×128 geometry at 4×. Drag a layer's box to move it; it snaps
  to whole pixels.
- **Layers** — any number per panel. **Add metric** inserts a sensor readout, **Add text**
  inserts a label, clock or date. Reorder, hide or delete from the list.
- **Inspector** — per panel: background colour or image (fit / crop / stretch, dim),
  accent colour. Per layer: metric, widget (big number or bar), position, size, colour,
  text size, decimals, unit, gauge min/max, alignment.
- **Live preview** streams from the agent at the configured refresh interval (1.5 s by
  default) using real sensor values, so what you see is what gets sent.
- Edits autosave to `config.json`; **Send** pushes the current design.

### Device wizard errors

The three failure modes are reported separately, because each has a different fix:

| Kind | Meaning | Fix |
| --- | --- | --- |
| `refused` | Host reachable, port closed | Try the other port (80 = HW 400, 9000 = HW 402) |
| `timeout` | No reply | Wrong IP, other network, device asleep, or it never got internet after boot |
| `token` | Device answered, rejected the call | Add/correct the LocalToken |

Whatever the device replied is shown verbatim in the wizard and in **Troubleshooting**.

## Metrics

| Metric | Source |
| --- | --- |
| CPU %, RAM %, disk %, network up/down | psutil |
| GPU % / temp / VRAM / fan | NVML (`nvidia-ml-py`), NVIDIA only |
| CPU temp, AMD/Intel GPU temp | LibreHardwareMonitor's WMI namespace, if it is running |

Metrics the machine cannot supply render as `--` on the panel, never as a wrong
number. CPU temperature needs LibreHardwareMonitor running with enough privilege to
expose `root/LibreHardwareMonitor`; without it you get `--` and everything else keeps
working. Nothing in v1 asks for elevation.

## Phone access

```bash
python -m gate_studio --lan
```

Binds `0.0.0.0` and prints `http://<pc-ip>:8765/?token=...`. The token guards the API,
media and the preview socket; the static page itself is public. The agent warns in the
terminal that the editor is now reachable from your network.

## Data

One folder (override with `--data-dir` or `GATE_STUDIO_DATA_DIR`):

```
%APPDATA%\GateThemeStudio\      (macOS: ~/Library/Application Support/GateThemeStudio)
├── config.json                 device + settings + current theme
├── token                       generated on first run
└── media/                      uploaded background images
```

## Tests

```bash
cd server
python -m pytest
```

Covers the transport (against a fake gate), renderer geometry, sensor collection,
presets, and the HTTP/WebSocket API. No hardware or elevation needed.

## How it works

```
Browser UI (React)  ──HTTP/WS──▶  Agent (FastAPI)  ──HTTP──▶  Times Gate
```

- **Rendering is server-side**: the whole 128×128 panel is drawn with Pillow, encoded
  as JPEG (2.5–6 KB per frame) and pushed with `Draw/SendHttpGif`. The device's text
  commands are never used for layout.
- **Two hardware revisions**: `POST http://<ip>/post` (HW 400) or
  `POST http://<ip>:9000/divoom_api` (HW 402). The wizard probes both.
- **LocalToken** is injected into every request body when set.
- **PicIDs** are monotonic per process, and `Draw/ResetHttpGifId` is sent at startup, so
  panels do not get stuck on "loading".
- **Panel addressing**: frames carry a length-5 `LcdArray` mask; single-panel commands
  use `LcdIndex`.
- **Fonts**: a bundled 5×7 pixel font (`render/font.py`) drawn at integer scales —
  lowercase is folded to uppercase by design.

Key files:

```
server/gate_studio/
├── api.py            REST + WebSocket
├── auth.py           bearer token gate
├── config.py         %APPDATA% storage, config.json, media/
├── models.py         theme / panel / layer / device schema
├── presets.py        preset loader + presets/*.json
├── device/           transport, error taxonomy, discovery
├── render/           font, widgets, backgrounds, renderer
└── sensors/          psutil collector, NVML + LibreHardwareMonitor
ui/src/               React editor
```

## Not in this milestone

- GIF and video backgrounds, panorama across five panels, sparkline and ring gauges,
  thermometer, undo/redo, per-panel copy (M3)
- Tray icon, autostart, automatic re-push after reboot or network loss, skipping
  identical frames, theme export/import UI, "hand back to Divoom face" (M4)
- Divoom account import of gallery backgrounds, multiple devices, Docker image (M5)

Also deliberately absent: any elevation prompt (temps degrade instead), and any cloud
component — a hosted page cannot reach a LAN device.
