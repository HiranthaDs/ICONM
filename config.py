import shutil
import sys
from pathlib import Path

APP_NAME = "IMERP V GM"
APP_VERSION = "IMERP V GM FINAL 2026.07"

SOURCE_DIR = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, "frozen", False))
APP_ASSET_DIR = Path(getattr(sys, "_MEIPASS", SOURCE_DIR)).resolve() if FROZEN else SOURCE_DIR

if FROZEN and sys.platform == "darwin":
    BASE_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    BASE_DIR = SOURCE_DIR

DATA_DIR = BASE_DIR / "data"
INVOICE_DIR = BASE_DIR / "invoices"
BACKUP_DIR = BASE_DIR / "backups"
EXPORT_DIR = BASE_DIR / "exports"
IMAGE_DIR = BASE_DIR / "images"
ASSET_IMAGE_DIR = APP_ASSET_DIR / "images"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "imerp_v_gm.sqlite3"

for _p in [DATA_DIR, INVOICE_DIR, BACKUP_DIR, EXPORT_DIR, IMAGE_DIR, LOG_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

if ASSET_IMAGE_DIR.exists() and ASSET_IMAGE_DIR.resolve() != IMAGE_DIR.resolve():
    for _img in ASSET_IMAGE_DIR.iterdir():
        if _img.is_file() and _img.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            _dest = IMAGE_DIR / _img.name
            if not _dest.exists():
                try:
                    shutil.copy2(_img, _dest)
                except Exception:
                    pass

ADMIN_DEFAULT_PASSWORD = "ICONM@2026"
STAFF_DEFAULT_PASSWORD = "STAFF@2026"
SYNC_PASSWORD = "11111"
LOW_STOCK_DEFAULT = 3

PRODUCT_TYPES = [
    "Phone", "Laptop", "Accessories", "Tablet", "Smartwatch", "Audio", "Gaming", "Spare Part", "Service", "Other"
]
CONDITIONS = ["Brand New", "Used", "Open Box", "Refurbished", "Other"]
GENERAL_WARRANTIES = [
    "No Warranty", "7 Days Checking", "14 Days Checking", "1 Month Warranty", "3 Months Warranty", "6 Months Warranty", "1 Year Warranty", "Manual Days"
]
PAYMENT_METHODS = ["Cash", "Card", "Koko", "Bank Transfer", "Online Transfer", "Credit", "Custom"]
EXTENDED_WARRANTIES = ["No Extended", "1 Year Extended", "2 Years Extended", "3 Years Extended", "Manual Days"]
COMPANY_DEFAULTS = {
    "company_name": "ICON MOBILE",
    "company_phone": "070 144 2299",
    "company_address": "Sri Lanka",
    "company_email": "",
    "invoice_footer": "Thank you for choosing ICON MOBILE. Please keep this invoice for warranty claims. System by Hich web Development 0714112113.",
    "whatsapp_country_code": "94",
    "sync_password": SYNC_PASSWORD,
}
