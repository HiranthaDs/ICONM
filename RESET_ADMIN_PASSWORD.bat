@echo off
cd /d "%~dp0"
py -3 -c "from database import execute, make_hash, now_iso; execute(\"UPDATE users SET password_hash=?, updated_at=? WHERE username='admin'\", (make_hash('ICONM@2026'), now_iso())); print('Admin password reset to ICONM@2026')"
pause
