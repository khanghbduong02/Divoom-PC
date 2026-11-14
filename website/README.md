# Public download page

This is the static landing page linked from the README. It explains that Gate Theme Studio
is a local Windows app and links to the exe in GitHub Releases. The editor itself is served
by the local agent and is intentionally not hosted here.

- Freebuff Sites project: `7f9c2a4e-5b8d-4c3e-9a1f-2d6b7c8e9f01`
- Production: <https://site-5b02d7b84842479d9d6e7cd6dfc76009.freebuff.page>
- Preview: <https://site-924a537ad7774cb29da1693766cc5bb7.freebuff.page>
- Download asset: <https://github.com/khanghbduong02/Divoom-PC/releases/latest/download/GateThemeStudio.exe>

The page is plain HTML/CSS with a tiny Worker that serves `public/`. To preview it locally:

```bash
python -m http.server 8780 --directory website/public
```

Open <http://127.0.0.1:8780/>. Deploy with `website/deploy.json` through Freebuff Sites.
