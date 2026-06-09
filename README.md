# RichCore

RichCore is a Windows admin tool for UkraineGTA workflows: reports, VIP chat moderation, binds, player actions, optimization and AI-assisted replies.

## Start from source

Requirements:

- Windows
- Python 3.14
- Optional: FreeQwenApi running on `http://localhost:3264/api` for AI support

Run:

```powershell
py -3.14 launcher.py
```

RichCore must run as administrator. If it is started without admin rights, the launcher asks Windows to restart it with UAC elevation.

### FreeQwenApi support

By default RichCore uses FreeQwenApi-compatible chat completion endpoints. Set `ai/config.json` to point at your local FreeQwenApi server and use `dummy-key` as the default API key.

## Build EXE

```powershell
.\scripts\build.ps1
```

The compiled file is created at:

```text
dist\RichCore_v12\RichCore_v12.exe
dist\RichCore_v12.zip
```

The installer is created as `dist\RichCore_Setup.exe`.

## Auto-update

Source launches update with `git pull --ff-only` when this folder is a normal clone with an upstream branch. You can also update manually using `scripts\update_from_github.ps1`.

Compiled EXE launches update from the latest GitHub Release of:

```text
https://github.com/OlekseiyKolovanov/RichCore
```

To publish an update:

1. Bump the version in `src/atools/version.py` and `pyproject.toml`.
2. Commit and push changes.
3. Create a tag like `v1.0.2` and push it.
4. GitHub Actions builds `dist\RichCore_v12.zip` and uploads it to the Release.

Users will see an update prompt in RichCore and can update without downloading or reinstalling manually.
Release assets should be uploaded as `RichCore_v12.zip`; the updater also supports legacy single-exe assets.
If GitHub Actions is unavailable, run `.\scripts\build.ps1` locally and upload `dist\RichCore_v12.zip` to the Release manually.
The installer file name stays stable as `RichCore_Setup.exe`; do not create a separate installer filename for every version.
