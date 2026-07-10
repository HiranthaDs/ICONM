import sys, platform, traceback
from pathlib import Path
from config import BASE_DIR, DB_PATH, LOG_DIR

log = []
def line(x):
    print(x); log.append(x)
try:
    line("ICON MOBILE SYSTEM - Diagnose")
    line("="*45)
    line(f"Python: {sys.version}")
    line(f"Executable: {sys.executable}")
    line(f"Platform: {platform.platform()}")
    line(f"Project folder: {BASE_DIR}")
    import tkinter
    line("[OK] tkinter installed")
    import sqlite3
    line(f"[OK] SQLite version: {sqlite3.sqlite_version}")
    import reportlab
    line("[OK] reportlab installed")
    try:
        import PIL
        line("[OK] Pillow installed")
    except Exception:
        line("[WARN] Pillow missing. Logo images still may work in PDF if reportlab can read them.")
    import database
    from database import query
    users = query("SELECT username, role, active FROM users")
    line(f"[OK] Database opened: {DB_PATH}")
    line(f"[OK] Users: {users}")
except Exception:
    line("[ERROR] Diagnose failed")
    line(traceback.format_exc())
finally:
    LOG_DIR.mkdir(exist_ok=True)
    (LOG_DIR / "diagnose.log").write_text("\n".join(log), encoding="utf-8")
    line(f"Diagnose log saved: {LOG_DIR / 'diagnose.log'}")
