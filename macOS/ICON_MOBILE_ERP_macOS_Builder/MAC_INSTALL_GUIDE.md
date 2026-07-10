# ICON MOBILE ERP - macOS Install Guide

This project is now prepared for macOS laptops.

## Option 1 - Easy source install

Use this when you copy the full project folder to a Mac.

1. Copy the folder `IMERP V GM` to the Mac Desktop.
2. Open Terminal.
3. Run:

```zsh
cd "$HOME/Desktop/IMERP V GM"
chmod +x mac_install.sh RUN_MAC_APP.command BUILD_MAC_APP.sh
./mac_install.sh
```

After setup, run the app anytime by double-clicking:

```text
RUN_MAC_APP.command
```

## Option 2 - Build a real macOS app

This must be run on a Mac. macOS apps cannot be correctly built from Windows.

Easy method: unzip the transfer package on the Mac, then double-click
`BUILD_MAC_INSTALLER.command`. If macOS does not run it directly, open Terminal
in the extracted folder and use the commands below.

```zsh
cd "$HOME/Desktop/IMERP V GM"
chmod +x BUILD_MAC_APP.sh
./BUILD_MAC_APP.sh
```

The build output will be:

```text
dist/ICON MOBILE ERP.app
dist/ICON_MOBILE_ERP_macOS.dmg
```

You can copy the `.app` to Applications, or send the `.dmg` to another Mac.
When the DMG opens, drag `ICON MOBILE ERP` onto the `Applications` shortcut.
The app and DMG use the supplied blue-and-white ICON MOBILE logo as the macOS icon.

## Data location

When running from source, data stays inside the project folder:

```text
data/
invoices/
backups/
exports/
images/
logs/
```

When running as a packaged macOS `.app`, data is stored safely here:

```text
~/Library/Application Support/IMERP V GM/
```

This keeps the database and invoices writable even if the app is copied to Applications.

## First open security note

If macOS blocks the app because it is from an unidentified developer:

1. Right-click `ICON MOBILE ERP.app`
2. Click `Open`
3. Click `Open` again

This is normal for unsigned local business apps.
