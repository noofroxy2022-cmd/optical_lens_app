# Windows Release Procedure

Reproducible sequence for building the Eyzon Optics Windows release and
installer from this repository. `npm run build` has been executed
successfully in this environment; the PyInstaller and Inno Setup commands
below have been confirmed valid for the installed tool version but not
yet executed end-to-end.

## 1. Prerequisite
`main` is at a verified, clean production source state: `git status` shows
a clean working tree, `git diff --check` is clean, and the target commit
has already passed backend, `SellerSafety.test.js`, and full frontend
verification.

## 2. Dashboard production build
```
cd dashboard
npm run build
```
Produces `dashboard/build/`, which `backend/EyzonOptics.spec` packages as
`../dashboard/build`.

## 3. PyInstaller build
Run from `backend/`:
```
python -m PyInstaller --distpath ../release EyzonOptics.spec
```
This is a one-file build. `--distpath` sends the executable directly to
`release/EyzonOptics.exe`. Use the forward-slash form (`../release`), not
`..\release`: the backslash form is shell-fragile (an intervening shell
layer can consume the backslash before PyInstaller sees it, silently
producing a wrong output path); PyInstaller/Python accept `/` in paths on
Windows and it resolves to the same repo-root `release/` directory
without that risk. No manual copy step is required.

## 4. Required release files
`release/` must contain, together, before packaging:
- `release/EyzonOptics.exe` (from step 3)
- `release/Start Eyzon Optics.cmd` (tracked source:
  `installer/Start Eyzon Optics.cmd` — packaged by Inno Setup directly
  from there; keep the copy in `release/` in sync for local testing)
- `release/release_runtime.db` (a generated/staged copy - see step 5;
  never hand-edited)

## 5. Release DB staging
`backend/release_runtime.db` is the **authoritative release seed
database**. `release/release_runtime.db` is a **generated/staged copy**
of it, used only as this build's installer input - it is not the
authoritative file and not any installed customer's live database.
Never move or modify `backend/release_runtime.db` itself.

Run from the repository root (portable PowerShell, repository-relative
paths only - no username or machine-specific path):
```
New-Item -ItemType Directory -Force -Path release | Out-Null
Copy-Item -Path backend\release_runtime.db -Destination release\release_runtime.db -Force
(Get-FileHash backend\release_runtime.db -Algorithm SHA256).Hash
(Get-FileHash release\release_runtime.db -Algorithm SHA256).Hash
python -c "import sqlite3; c = sqlite3.connect('file:release/release_runtime.db?mode=ro', uri=True); print(c.execute('PRAGMA integrity_check').fetchone()[0])"
```
Require the two SHA-256 values to match exactly, and the integrity check
to print `ok`, before proceeding to Inno Setup. The copy always overwrites
the staged file so each release build is deterministic from the current
authoritative source - this is safe because it only ever touches the
build-time staging copy in `release/`, never an installed customer's
database. Customer-installed data is protected separately, at install
time, by Inno Setup's `onlyifdoesntexist` + `uninsneveruninstall` on this
same file (see step 8) - overwriting the staging copy here has no effect
on that.

## 6. Inno Setup build
Prerequisite: install the official Inno Setup 6 from JRSoftware
(jrsoftware.org / https://jrsoftware.org/isinfo.php).

Compiler resolution: if `ISCC.exe` is on PATH, invoke it directly. It is
not on PATH by default on every machine, so otherwise locate the actual
installed `ISCC.exe` and invoke it by its real absolute path - never
assume a fixed location. For example, in PowerShell:
```
$ISCC = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"  # EXAMPLE ONLY -
                                                          # a common default
                                                          # location, not a
                                                          # guarantee; point
                                                          # this at wherever
                                                          # ISCC.exe is
                                                          # actually installed
& $ISCC EyzonOptics.iss
```
Run from `installer/` either way (working directory = `installer/`,
input = `EyzonOptics.iss`).

## 7. Expected installer
Per `OutputDir=..` and `OutputBaseFilename=Eyzon-Optics-Setup` in
`EyzonOptics.iss`, this produces `Eyzon-Optics-Setup.exe` at the
repository root.

## 8. Database safety
`release_runtime.db` is installed by Inno Setup with `onlyifdoesntexist`
and `uninsneveruninstall` (`[Files]` in `EyzonOptics.iss`). An
upgrade install must never overwrite or delete an existing operational
database, and uninstall must never remove it. Never delete/replace
`release_runtime.db` during an upgrade unless a separately verified
database migration procedure explicitly requires it.

## 9. Verification checklist before tag/release
- [ ] `release/EyzonOptics.exe` starts
- [ ] backend starts successfully (port 8000 reachable)
- [ ] dashboard loads (port 3000 reachable)
- [ ] `release_runtime.db` integrity_check = ok
- [ ] seller search smoke test passes
- [ ] installer install/start test passes
- [ ] upgrade install preserves an existing operational DB
- [ ] uninstall preserves the DB (per `uninsneveruninstall`)
- [ ] `git diff --check` and `git status` are clean
- [ ] `installer/EyzonOptics.iss` `MyAppVersion` matches the version
      being released

## 10. Tagging
Tag the release (`git tag -a vX.Y.Z -m "..."`) only after every item in
the checklist above has been verified against the built artifacts.

## Known gaps
- `ISCC.exe` is not guaranteed to be on PATH after installing Inno Setup;
  step 6 documents resolving its actual installed location instead of
  assuming one.
