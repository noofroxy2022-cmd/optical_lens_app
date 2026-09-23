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
python -m PyInstaller --distpath ..\release EyzonOptics.spec
```
This is a one-file build. `--distpath` sends the executable directly to
`release/EyzonOptics.exe` (confirmed a valid PyInstaller CLI option via
`python -m PyInstaller --help` for the installed version; not yet run
end-to-end). No manual copy step is required.

## 4. Required release files
`release/` must contain, together, before packaging:
- `release/EyzonOptics.exe` (from step 3)
- `release/Start Eyzon Optics.cmd` (tracked source:
  `installer/Start Eyzon Optics.cmd` — packaged by Inno Setup directly
  from there; keep the copy in `release/` in sync for local testing)
- `release/release_runtime.db` (the approved/certified operational
  database — preserve as-is; never regenerate or overwrite it here)

## 5. Inno Setup build
Run from `installer/`:
```
ISCC.exe EyzonOptics.iss
```

## 6. Expected installer
Per `OutputDir=..` and `OutputBaseFilename=Eyzon-Optics-Setup` in
`EyzonOptics.iss`, this produces `Eyzon-Optics-Setup.exe` at the
repository root.

## 7. Database safety
`release_runtime.db` is installed by Inno Setup with `onlyifdoesntexist`
and `uninsneveruninstall` (`[Files]` in `EyzonOptics.iss`). An
upgrade install must never overwrite or delete an existing operational
database, and uninstall must never remove it. Never delete/replace
`release_runtime.db` during an upgrade unless a separately verified
database migration procedure explicitly requires it.

## 8. Verification checklist before tag/release
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

## 9. Tagging
Tag the release (`git tag -a vX.Y.Z -m "..."`) only after every item in
the checklist above has been verified against the built artifacts.

## Known gaps
- `release/release_runtime.db`'s own provenance/certification process is
  external to this procedure.
- `ISCC.exe` (Inno Setup) was not found on this machine at either default
  install location or on PATH; it must be installed before step 5 can run
  here.
