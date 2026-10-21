# Assets

Drop the source icon image here:

- `icon.png` — 512x512 (or larger) source PNG. Used for Tk window icon at runtime.
- `icon.ico` — multi-size ICO (16/32/48/64/256 px). Used by PyInstaller as the executable icon.
- `logo-28.png` — 28x28 downscale of `icon.png` shown next to the app name in the sidebar header.

To regenerate `icon.ico` from `icon.png`:

```
pip install pillow
python -c "from PIL import Image; im = Image.open('icon.png'); im.save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
```

To regenerate `logo-28.png`:

```
python -c "from PIL import Image; Image.open('icon.png').resize((28,28), Image.LANCZOS).save('logo-28.png', optimize=True)"
```
