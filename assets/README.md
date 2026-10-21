# Assets

Drop the source icon image here:

- `icon.png` — 512x512 (or larger) source PNG. Used for Tk window icon at runtime.
- `icon.ico` — multi-size ICO (16/32/48/64/256 px). Used by PyInstaller as the executable icon.
- `logo-28.png` — 28x28 downscale of `icon.png` shown next to the app name in the sidebar header.
- `logo-96.png` — 96x96 downscale of `icon.png` shown in the empty video area.

`icon.png` must keep a transparent background (RGBA); every other icon file is derived from it.

To regenerate `icon.ico` from `icon.png`:

```
pip install pillow
python -c "from PIL import Image; im = Image.open('icon.png'); im.save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
```

To regenerate `logo-28.png` / `logo-96.png`:

```
python -c "from PIL import Image; im = Image.open('icon.png'); [im.resize((n,n), Image.LANCZOS).save(f'logo-{n}.png', optimize=True) for n in (28, 96)]"
```
