# Desktop icons

Tauri's bundler reads the icon paths listed under `bundle.icon` in
`src-tauri/tauri.conf.json`:

- `icons/32x32.png`
- `icons/128x128.png`
- `icons/128x128@2x.png`
- `icons/icon.icns` (macOS)
- `icons/icon.ico` (Windows)

Generate all of them from a single 1024×1024 master PNG using the
first-party Tauri CLI:

```bash
# From apps/desktop/
pnpm tauri icon path/to/voyagent-1024.png
```

That command writes every required size + format into this directory.
The master PNG should be opaque (no alpha outside the art) with at
least a 10% transparent margin around the glyph — Windows and macOS
both add system chrome on top of the icon.

## Placeholder

A real master artwork has not been committed yet. Until the brand team
delivers one, builds will fall back to Tauri's built-in default icon
and `tauri build` will warn. See `icon.placeholder.txt`.
