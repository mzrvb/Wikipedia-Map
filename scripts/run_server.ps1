# Runs WikiMap for LAN access. Differs from the dev command (README) in two ways:
# no --reload (that's a dev-only file watcher, wasted overhead on a server), and
# --host 0.0.0.0 so other devices on the network can reach it, not just this machine.
Set-Location "$PSScriptRoot\.."
& .\.venv\Scripts\Activate.ps1
uvicorn wikimap.server.app:app --host 0.0.0.0 --port 8000
