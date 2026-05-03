# Assets

Drop the source icon image here:

- `icon.png` — 512x512 (or larger) source PNG. Used for Tk window icon at runtime.
- `icon.ico` — multi-size ICO (16/32/48/64/256 px). Used by PyInstaller as the executable icon.

To regenerate `icon.ico` from `icon.png`:

```
pip install pillow
python -c "from PIL import Image; im = Image.open('icon.png'); im.save('icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
```
