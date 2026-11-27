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
| `euro-office-logo.svg` | Main logo: four coloured pages fanned behind a white page with a navy title bar, blue star and text lines. Use from 24 px to about 96 px. |
| `euro-office-logo-large.svg` | Same logo with a slimmer title bar, for 128 px and up. |
| `euro-office-logo-16.svg` | Simplified version for 16–20 px: two back pages (teal and orange) and a bigger star, with no text lines. |
| `euro-office-logo-dark*.svg` | Dark-mode versions of the three above: pale grey card, EU-blue title bar and star, stronger shadow. |
| `euro-office-tile-rounded.svg` | Alternative tile: the logo on mist (#E8EEFA) in a rounded square. Use for tablets and mobile. |
| `euro-office-tile-square.svg` | Same tile with square corners, for platforms that apply their own mask (iOS, apple-touch-icon). |
| `euro-office-android-foreground.svg` | Logo only, scaled into the Android adaptive-icon safe zone. The background is mist, `#E8EEFA`. |
| `filetypes/<ext>.svg` | File icon master (used at 32 px and above). |
| `filetypes/pixel/<size>/<ext>-<size>.svg` | Hand-drawn pixel versions at 16, 20, 24 and 32 px. Every shape sits on whole pixels; render them at exactly that size. |

**App logo sizes:** bitmaps at 20 px and below use the 16 px logo, 24–96 px use the standard logo, and 128 px and up use the large logo. The exported app icons are edge to edge: the outer pages' corners touch the canvas, as in Windows' own icons. They have no outer drop shadow, which would otherwise eat into that size; the white page keeps its subtle shadow on the pages behind it.

**File icon sizes:** the 16, 20, 24 and 32 px bitmaps are the hand-drawn pixel icons (Windows uses the 20 and 24 px frames at 125% and 150% display scaling, and 32 at 200%). Linux's 22 px icon is the 20 px pixel icon centred on a 22 px canvas. Every other size is rendered from the vector master. All bitmaps have real alpha transparency: nothing is drawn behind the artwork.

## Windows

- **App:** `windows/app/euro-office.ico` contains 16, 20, 24, 32, 40, 48, 64, 96 and 256 px. Embed it as the executable's icon resource.
- **File types:** `windows/filetypes/<ext>.ico` contains 16–256 px. Register each one under the extension's ProgID, e.g. `HKCR\EuroOffice.Document.docx\DefaultIcon = "...\docx.ico"`.
- **Format inside the .ico files:** Microsoft's recommended layout. Every size below 256 is a 32-bit BMP with an alpha channel plus a 1-bit transparency mask, and 256 px is PNG-compressed.
- **Previews:** in Explorer's Large/Extra large views, `.ico` files are previewed like photos, on a white card. That card isn't part of the file. Use Details/List view, or a shortcut's Change Icon dialog, to see the real result.
- **MSIX/Store:** basic logos are in `windows/app/msix/`. Add scale variants if the packaging tool asks for them.

## macOS

- **App:** `macos/app/AppIcon.iconset` is the canonical source. Running `iconutil -c icns AppIcon.iconset` rebuilds the .icns on a Mac, or you can drop the PNGs into an Xcode asset catalog's AppIcon set.
  - macOS uses the mist tile, not the frameless logo, laid out on Apple's grid (tile ≈ 80% of the canvas, transparent margin, soft shadow). On macOS 26, an icon that isn't a rounded square gets put inside a grey tile.
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
- The "maskable" icons put the logo on full-bleed mist (#E8EEFA), inside the 80% safe zone.

## Mobile and tablet

- **iOS/iPadOS:** `mobile/ios/AppIcon-1024.png` is square, opaque, with no rounded corners (iOS applies its own mask). Generate the size set with Xcode's single-size app icon.
- **Android:** copy `mobile/android/res` into the app module. The adaptive icon uses the mist background colour (#E8EEFA) and the foreground logo. The `ic_launcher.png` files are the pre-Android 8 fallback.
  - There's no monochrome (themed-icon) layer yet.
- **Tablet tiles:** rounded tiles at 512 and 1024 px, for store listings or launchers that don't mask.

## Palette

| Role | Hex |
|---|---|
| Brand blue | #003399 |
| App tile background (mist) | #E8EEFA |
| Logo pages | #2F6FDE, #1FA463, #F39C12, #E0443A behind a white page; title bar #14213D, star #0B3A9E (16 px back pages: #249488, #EA7026) |
| Documents | #2F6FDE |
| Spreadsheets | #1FA463 |
| Presentations | #F39C12 |
| PDF / fixed layout | #E0443A |
| Diagrams | #6F4CD6 |
| Text and web | #5B6B85 |
| E-books | #8D5B3C |

**Main formats** (.docx, .dotx, .docxf, .xlsx, .xlsm, .xltx, .xlsb, .pptx, .pptm, .ppsx, .potx, .pdf, .vsdx) show a pop-out badge. Templates invert the badge: white fill with a coloured outline.
