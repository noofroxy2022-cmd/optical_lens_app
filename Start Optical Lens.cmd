@echo off
setlocal
set "API_PORT=8000"
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',8000); exit 1 } catch { exit 0 } finally { $c.Dispose() }"
if errorlevel 1 set "API_PORT=8001"
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',%API_PORT%); exit 1 } catch { exit 0 } finally { $c.Dispose() }"
if errorlevel 1 (
  echo API port %API_PORT% is already in use. Close the other server and try again.
  pause
  exit /b 1
)
powershell -NoProfile -Command "$c=New-Object Net.Sockets.TcpClient; try { $c.Connect('127.0.0.1',3000); exit 1 } catch { exit 0 } finally { $c.Dispose() }"
if errorlevel 1 (
  echo Dashboard port 3000 is already in use. Close the other dashboard and try again.
  pause
  exit /b 1
)
set "DATABASE_URL="
set "REACT_APP_API_URL=http://localhost:%API_PORT%"
set "BROWSER=none"
start "Optical Lens API" /D "%~dp0backend" cmd /k python -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT%
start "Optical Lens Dashboard" /D "%~dp0dashboard" cmd /k npm.cmd start
start "" http://localhost:3000
