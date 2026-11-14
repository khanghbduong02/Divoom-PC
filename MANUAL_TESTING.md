# Manual testing

These commands use Git Bash on Windows. Run them from the repository root unless a step
changes directory.

## 1. Automated checks

```bash
conda activate divoom-studio

cd server
python -m pytest -q
cd ..

cd ui
npx tsc --noEmit
npm run build
cd ..
```

`npm run build` also copies the editor into `server/gate_studio/static/`, which is what the
agent serves.

## 2. Run the built editor locally

Keep this running in the first terminal:

```bash
cd server
python -m gate_studio --no-tray --no-browser --port 8799 --data-dir ../build/manual-data
```

Open the printed `editor : http://127.0.0.1:8799/?token=...` URL. This uses the same
production UI bundle the downloadable exe serves.

To use the Vite hot-reload server instead, keep the agent on port 8765 and run:

```bash
# terminal 1
cd server
python -m gate_studio --no-tray --no-browser --port 8765 --data-dir ../build/manual-data

# terminal 2
cd ui
npm run dev
```

Open `http://127.0.0.1:5173/?token=...`, reusing the token printed by the agent. Vite
proxies `/api`, `/media` and `/ws` to port 8765.

## 3. Check the API with curl

In a second Git Bash terminal, while the port 8799 agent is running:

```bash
TOKEN=$(cat build/manual-data/token)

curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8799/api/health
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8799/api/system
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8799/api/theme
```

On a fresh data directory, all five panels are empty. Confirm that **Send all** is a no-op:

```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8799/api/send
# {"results":[],"skipped":[0,1,2,3,4]}
```

Confirm saving a reusable theme:

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Manual test"}' \
  http://127.0.0.1:8799/api/library/themes
```

If the port 8799 agent is not running, the curl commands fail with connection refused.
The token is local access control, not an account password; do not post it publicly.

## 4. Test the downloadable exe

```bash
cd server
./dist/GateThemeStudio.exe --no-tray --no-browser --port 8799 --data-dir ../build/exe-test
```

Open the printed URL and confirm the editor loads. This does not touch the registry or
the tray while `--no-tray` is set. On this development PC Smart App Control may block the
unsigned exe; that is a Windows policy check, not an app crash. End users may see a
SmartScreen warning and can choose **More info → Run anyway**.

## 5. Test against the real Gate

1. Run `python -m gate_studio` normally (or launch the exe) with the real data folder.
2. Open the printed editor URL and use **Connect a display**.
3. Use **Send test tile** on one panel, then make a small design and press **Apply**.
4. Confirm only that panel changed.
5. Leave one panel empty, press **Send all**, and confirm the empty panel does not change.
6. Press **Pause updates for this screen**, then **Resume**.
7. Save a panel and a theme, reload the page, and load each one back.
8. Restart the app and confirm the display keeps updating.

Check the agent log and **Troubleshooting** if the device does not answer. The Divoom phone
app can hold the connection during setup; close it temporarily if probing fails.

## 6. Verify the public download

```bash
curl -L -o GateThemeStudio.exe \
  https://github.com/khanghbduong02/Divoom-PC/releases/latest/download/GateThemeStudio.exe
sha256sum GateThemeStudio.exe
# 2f3d4f3837f21d7a0870cde185acfff3060558f38b525dc418e37d50665d97db
```

The public download page is:
<https://site-5b02d7b84842479d9d6e7cd6dfc76009.freebuff.page>
