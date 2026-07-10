# IMERP V GM - ICON MOBILE ERP/POS

Requested folder path:

```text
C:\Users\Hirantha Dias\Desktop\IMERP V GM
```

This is a complete Python + SQLite desktop ERP/POS system for ICON MOBILE with retail billing, exact IMEI stock, bulk accessories, partner/wholesale shops, FIFO payments, finance reports, premium PDFs, backup/restore and same-WiFi sync.

## Login

```text
Admin username: admin
Admin password: ICONM@2026

Staff username: staff
Staff password: STAFF@2026

Same-WiFi sync password: 11111
```

## Windows run commands

```powershell
cd "C:\Users\Hirantha Dias\Desktop\IMERP V GM"
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 diagnose.py
py -3 app.py
```

Or double-click:

```text
START_HERE.bat
```

## macOS run commands

Recommended: install Python 3 from python.org on the Mac, then run:

```zsh
cd "$HOME/Desktop/IMERP V GM"
chmod +x mac_install.sh RUN_MAC_APP.command BUILD_MAC_APP.sh
./mac_install.sh
```

After the first setup, open the app anytime by double-clicking:

```text
RUN_MAC_APP.command
```

## Build macOS .app / DMG

This must be done on a Mac. Apple/macOS apps cannot be correctly built from Windows.

```zsh
cd "$HOME/Desktop/IMERP V GM"
chmod +x BUILD_MAC_APP.sh
./BUILD_MAC_APP.sh
```

Output:

```text
dist/ICON MOBILE ERP.app
dist/ICON_MOBILE_ERP_macOS.dmg
```

When running as a packaged `.app`, the system stores database, invoices, backups and logs in:

```text
~/Library/Application Support/IMERP V GM/
```

See `MAC_INSTALL_GUIDE.md` for the full Mac install guide.

## Main workflow

### Inventory

- No manual Serialized/Bulk selector.
- Enter serial/IMEI lines for exact-unit devices.
- Leave serial/IMEI empty for bulk accessories.
- Quantity can open separate serial fields.
- Generate Auto IDs creates safe internal unit IDs.
- Restock keeps a full audit trail and weighted average cost.
- Stock Details popup shows unit-level cost, selling price, profit, supplier, status, invoice/reference and sold date.

### Billing

- Search by SKU, item name, full IMEI, or last 5 digits.
- Open All Items / Pick shows products and exact available units.
- Double-click an exact unit to cart.
- Add Direct Sale Item is for items bought from another shop and sold immediately without saving inventory stock.
- Direct sale items save bought-from shop, buying cost, selling price, warranty and client/invoice history for finance profit.
- Payment area calculates item total, extended warranty total, discount, paid and remaining due in real time.
- Saving invoice marks exact IMEIs as Sold and reduces bulk stock.
- PDF opens automatically and WhatsApp message can be sent.

### Partner Shops

- Shop profiles show issued amount, paid amount, due amount and past details.
- Issue items with custom wholesale selling price.
- Quick Payment allocates FIFO to oldest due invoices.
- Statement PDF and WhatsApp due message include total due and due items.

### Finance

- Admin sees revenue, COGS, gross profit, inventory assets, receivables and payment methods.
- Sales can be filtered by today/daily, weekly, monthly, annual/year and custom date range.
- Staff sees sold quantity report without money/profit values.

### PDF assets

Place optional images here:

```text
images/logo.png
images/logo watermark.png
images/Google reviews.png
images/Map Qr.png
images/google.png
images/googlemap.png
images/Warranty.png
```

The app will not crash if images are missing.

## Debug commands

```powershell
cd "C:\Users\Hirantha Dias\Desktop\IMERP V GM"
.\DEBUG_RUN.bat
notepad .\logs\diagnose.log
notepad .\logs\startup_error.log
notepad .\logs\app_run_error.log
```

## Files

```text
app.py              Main Apple-style desktop UI
database.py         SQLite schema and default users
services.py         Inventory, billing, partner, finance and backup logic
pdf_utils.py        Retail, wholesale and statement PDF generation
lan_sync.py         Same-WiFi sync helper
sync_server.py      Compatibility sync wrapper
diagnose.py         System diagnostic script
config.py           Paths, app constants and defaults
BUSINESS_LOGIC.md   Deep business rules and ERP logic notes
```
