# Euro-Office icon set (Classic palette)

Everything is generated from the SVG masters in `source/`. If a design changes, re-export from those; don't edit the PNGs by hand.

```
source/        SVG masters, palette.json, filetypes.json (extension → group, MIME, primary/template)
windows/       .ico files (app + one per extension) and MSIX/Store PNGs
macos/         AppIcon.iconset + AppIcon.icns, one .icns per extension
linux/         freedesktop hicolor theme tree (apps + mimetypes, PNG sizes + scalable SVG)
web/           favicon.svg/.ico, apple-touch-icon, PWA icons + manifest.webmanifest
mobile/        iOS 1024 marketing icon, Android adaptive + legacy launcher icons, tablet tiles
```

## The artwork

| Asset | Use |
|---|---|
| `euro-office-logo.svg` | Main logo: the frameless three-page stack. Default everywhere except where a platform forces a tile shape. |
| `euro-office-tile-rounded.svg` | Alternative tile: the same stack on EU blue (#003399) in a rounded square. Use for tablets/mobile. |
| `euro-office-tile-square.svg` | Same tile with square corners, for platforms that apply their own mask (iOS, apple-touch-icon). |
| `euro-office-android-foreground.svg` | Stack only, scaled into the Android adaptive-icon safe zone. Background is `#003399`. |
| `filetypes/<ext>.svg` | File icon master (used at 32 px and above). |
| `filetypes/16px/<ext>-16.svg` | Simplified-badge version (two text lines, 2×2 grid, and so on), used at 24 px and below. |

**Small sizes:** every bitmap up to 24 px uses the simplified master, because Windows uses the 20 and 24 px frames instead of 16 at 125% and 150% display scaling. Larger sizes use the full master. All bitmaps have real alpha transparency: nothing is drawn behind the artwork.

## Windows

- **App:** `windows/app/euro-office.ico` contains 16, 20, 24, 32, 40, 48, 64, 96 and 256 px. Embed it as the executable's icon resource.
- **File types:** `windows/filetypes/<ext>.ico` contains 16–256 px. Register each one under the extension's ProgID, e.g. `HKCR\EuroOffice.Document.docx\DefaultIcon = "...\docx.ico"`.
- **Format inside the .ico files:** Microsoft's recommended layout. Every size below 256 is a 32-bit BMP with an alpha channel plus a 1-bit transparency mask, and 256 px is PNG-compressed.
- **Previews:** in Explorer's Large/Extra large views, `.ico` files are previewed like photos, on a white card. That card isn't part of the file. Use Details/List view, or a shortcut's Change Icon dialog, to see the real result.
- **MSIX/Store:** basic logos are in `windows/app/msix/`. Add scale variants if the packaging tool asks for them.

## macOS

- **App:** `macos/app/AppIcon.iconset` is the canonical source. Running `iconutil -c icns AppIcon.iconset` rebuilds the .icns on a Mac, or you can drop the PNGs into an Xcode asset catalog's AppIcon set.
  - The bundled `AppIcon.icns` was built on Linux and leaves out the 16 and 32 px 1× entries. macOS downscales for those, but rebuild with iconutil for a pixel-perfect set.
  - macOS uses the blue tile, not the frameless logo, laid out on Apple's grid (tile ≈ 80% of the canvas, transparent margin, soft shadow). On macOS 26, an icon that isn't a rounded square gets put inside a grey tile.
- **Documents:** `macos/filetypes/<ext>.icns`. Reference them from `CFBundleDocumentTypes` → `CFBundleTypeIconFile` in Info.plist.

## Linux (freedesktop)

Copy `linux/icons/hicolor` into `/usr/share/icons/hicolor` (or `~/.local/share/icons/hicolor`, or the Flatpak's `/app/share/icons/hicolor`), then run:

```
gtk-update-icon-cache -f -t /usr/share/icons/hicolor
```

- **App:** `Icon=euro-office` in the `.desktop` file.
- **File types:** icons are named after the MIME type with `/` replaced by `-`. For example, `.docx` uses `application-vnd.openxmlformats-officedocument.wordprocessingml.document.svg`.
- **Shared MIME types:** `.ppt`, `.pps` and `.pot` share `application/vnd.ms-powerpoint`, and `.html`/`.htm` share `text/html`. Each of these pairs gets one icon (the designs are the same anyway).
- **Check before release:** the MIME types for `.docxf`, `.oform`, `.hwp` and `.hwpx` are best guesses. Check them against the shared-mime-info definitions the app installs, and rename those icon files to match.

## Web

```html
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="32x32">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
```

- The "any" icons are the frameless logo.
- The "maskable" icons put the stack on full-bleed blue, inside the 80% safe zone.

## Mobile and tablet

- **iOS/iPadOS:** `mobile/ios/AppIcon-1024.png` is square, opaque, with no rounded corners (iOS applies its own mask). Generate the size set with Xcode's single-size app icon.
- **Android:** copy `mobile/android/res` into the app module. The adaptive icon uses the blue background colour and the foreground stack. The `ic_launcher.png` files are the pre-Android 8 fallback.
  - There's no monochrome (themed-icon) layer yet.
- **Tablet tiles:** rounded tiles at 512 and 1024 px, for store listings or launchers that don't mask.

## Palette

| Role | Hex |
|---|---|
| Brand background | #003399 |
| Logo pages | #1FA463 (green) and #FFCC00 (gold), white front page |
| Documents | #2F6FDE |
| Spreadsheets | #1FA463 |
| Presentations | #F39C12 |
| PDF / fixed layout | #E0443A |
| Diagrams | #6F4CD6 |
| Text and web | #5B6B85 |
| E-books | #8D5B3C |

**Main formats** (.docx, .dotx, .docxf, .xlsx, .xlsm, .xltx, .xlsb, .pptx, .pptm, .ppsx, .potx, .pdf, .vsdx) show a pop-out badge. Templates invert the badge: white fill with a coloured outline.
