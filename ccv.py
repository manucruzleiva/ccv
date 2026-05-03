"""
CCV - Capture Card Viewer.

GUI tkinter compacta + CLI. En Windows captura DirectShow via ffmpeg/ffplay
externos para mantenerse extremadamente ligero. Por defecto abre la GUI;
los subcomandos siguen disponibles para uso desde terminal.

Uso:
    pythonw ccv.py             # GUI (sin ventana de consola)
    python  ccv.py             # GUI con consola (debug)
    python  ccv.py console     # menu de consola
    python  ccv.py preview     # vista previa con audio
    python  ccv.py screenshot  # captura unica
    python  ccv.py record      # grabar (Enter para detener)
    python  ccv.py install     # verificar binarios + libs Python
    python  ccv.py shortcut    # crear acceso directo en Escritorio
    python  ccv.py build       # generar ccv.exe (PyInstaller)
    python  ccv.py devices     # listar dispositivos DirectShow
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths, frozen detection, subprocess flags
# --------------------------------------------------------------------------- #
IS_FROZEN = bool(getattr(sys, "frozen", False))
if IS_FROZEN:
    SCRIPT_DIR = Path(sys.executable).resolve().parent
else:
    SCRIPT_DIR = Path(__file__).resolve().parent

# Lugares donde puede estar bin/: (1) junto al script/.exe y (2) dentro del
# bundle de PyInstaller (sys._MEIPASS) cuando se uso --add-binary.
_BIN_CANDIDATES: list[Path] = [SCRIPT_DIR / "bin"]
if IS_FROZEN:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        _BIN_CANDIDATES.append(Path(meipass) / "bin")

LOCAL_BIN: Path | None = None
for _cand in _BIN_CANDIDATES:
    if _cand.exists():
        LOCAL_BIN = _cand
        os.environ["PATH"] = str(_cand) + os.pathsep + os.environ.get("PATH", "")
        break
if LOCAL_BIN is None:
    LOCAL_BIN = SCRIPT_DIR / "bin"   # placeholder para mensajes de error

APP_NAME = "Capture Card Viewer"
APP_NAME_SHORT = "CCV"
APP_ID = "ccv"   # exe name, config filename, AppUserModelID suffix
APP_VERSION = "0.6.0"
APP_AUMID = f"com.ccv.captureCardViewer"  # taskbar grouping en Windows
APP_REPO_URL = "https://github.com/manucruzleiva/ccv"
APP_CHANGELOG_URL = f"{APP_REPO_URL}/blob/main/CHANGELOG.md"

CONFIG_PATH = Path.home() / f".{APP_ID}.json"
# Compatibilidad: si existe el cfg viejo y no el nuevo, lo migramos.
_LEGACY_CONFIG = Path.home() / ".switch_capture.json"
if _LEGACY_CONFIG.exists() and not CONFIG_PATH.exists():
    try: _LEGACY_CONFIG.replace(CONFIG_PATH)
    except Exception: pass

# Iconos: buscar en (1) assets/ junto al script o (2) _MEIPASS/assets en frozen.
def _resolve_asset(rel: str) -> Path | None:
    candidates = [SCRIPT_DIR / "assets" / rel]
    if IS_FROZEN:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass: candidates.append(Path(meipass) / "assets" / rel)
    for c in candidates:
        if c.exists(): return c
    return None

ICON_ICO = _resolve_asset("icon.ico")
ICON_PNG = _resolve_asset("icon.png")


# --------------------------------------------------------------------------- #
# i18n - traducciones (ISO 639-1: es, en, ...)
# --------------------------------------------------------------------------- #
LANG_NAMES = {
    "es": "Espanol",
    "en": "English",
    "pt": "Portugues",
    "fr": "Francais",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "es": {
        # top bar
        "tt.close":      "Cerrar la aplicacion.",
        "tt.minimize":   "Minimizar a la barra de tareas.\nAtajo: F12.",
        "tt.maximize":   "Maximizar / restaurar la ventana al tamano del area de trabajo.",
        "tt.fullscreen": "Pantalla completa (cubre todo el escritorio).\nClick de nuevo para salir. Atajo: F11.",
        "tt.theme":      "Cambiar tema claro / oscuro.",
        "tt.lang":       "Cambiar idioma. Click para alternar entre los disponibles.",
        "tt.side_toggle":"Cambiar el lado del sidepanel (izquierda / derecha).",
        "tt.mute":       "Mute / unmute del audio de la vista previa.\nTambien: click rueda del mouse sobre el video.",
        "tt.popup":      "Modo focus: oculta los menus, el video llena la ventana.\nDoble-click sobre el video o Esc para volver.",
        "tt.preview":    "Iniciar / cerrar la vista previa con audio.\nMientras esta activa puedes capturar y grabar sin cerrarla.",
        "tt.screenshot": "Capturar el frame actual.\nToma del buffer del preview (instantaneo).\n\nAtajo: PrintScreen.\nCtrl+Click: abrir la carpeta de capturas.",
        "tt.record":     "Iniciar / detener grabacion de video + audio.\nLa preview no se interrumpe (el master ffmpeg sigue corriendo).\n\nCtrl+Click: abrir la carpeta de grabaciones.",
        # secciones
        "sec.devices":       "Dispositivos",
        "sec.quality":       "Calidad",
        "sec.preview_audio": "Vista previa y audio",
        "sec.capture":       "Captura de pantalla",
        "sec.recording":     "Grabacion",
        "sec.folders":       "Carpetas de salida",
        "sec.system":        "Sistema",
        # sistema
        "sys.state":         "Estado:",
        "sys.diagnostics":   "Diagnostico:",
        "sys.version":       "Version:",
        "sys.history":       "Ver historial de cambios",
        # labels (form fields)
        "lbl.video":         "Video",
        "lbl.audio":         "Audio",
        "lbl.always_on_top": "Siempre encima",
        "lbl.volume":        "Volumen",
        "lbl.audio_buffer":  "Buffer audio (ms)",
        "lbl.codec_video":   "Codec video",
        "lbl.preset":        "Preset",
        "lbl.crf":           "CRF (0-51)",
        "lbl.codec_audio":   "Codec audio",
        "lbl.bitrate":       "Bitrate audio",
        "lbl.container":     "Contenedor",
        "lbl.folder":        "Carpeta",
        "lbl.shots_dir":     "Capturas",
        "lbl.videos_dir":    "Videos",
        "lbl.clipboard":     "Copiar al portapapeles",
        "lbl.png":           "Guardar archivo PNG",
        "lbl.fmt_active":    "Activo: {res} @ {fps}fps",
        "lbl.fmt_hardware":  "Hardware: {dev}",
        "lbl.fmt_loading":   "Consultando formatos...",
        "lbl.fmt_no_device": "(elige un dispositivo de video)",
        "lbl.fmt_unsupported": "(no soportado)",
        "lbl.fmt_picker_tip": "Elige resolucion + FPS soportado por tu capturadora.\nLa lista se filtra al hardware detectado.",
        "lbl.video_placeholder": "(Inicia la vista previa para ver el video aqui)",
        # status
        "st.ready":             "Listo",
        "st.preview_active":    "Vista previa activa",
        "st.preview_starting":  "Iniciando vista previa...",
        "st.start_preview_first": "Inicia la vista previa primero",
        "st.capturing":         "Capturando...",
        "st.recording_to":      "Grabando → {name}",
        "st.recording_saving":  "Deteniendo grabacion (finalizando archivo)...",
        "st.recording_saved":   "Grabacion guardada · {msg}",
        # toasts
        "toast.shot_file":      "📷 Captura guardada · {name}",
        "toast.shot_clip":      "📷 Captura al portapapeles",
        "toast.rec_started":    "⏺ Grabacion iniciada · {name}",
        "toast.rec_finalizing": "⏹ Finalizando grabacion...",
        "toast.rec_saved":      "✓ Grabacion guardada · {msg}",
        "toast.rec_no_file":    "⚠ Grabacion sin archivo",
    },
    "en": {
        "tt.close":      "Close the application.",
        "tt.minimize":   "Minimize to taskbar.\nShortcut: F12.",
        "tt.maximize":   "Maximize / restore window to work-area size.",
        "tt.fullscreen": "Fullscreen (covers the whole desktop).\nClick again to exit. Shortcut: F11.",
        "tt.theme":      "Toggle light / dark theme.",
        "tt.lang":       "Change language. Click to cycle through available ones.",
        "tt.side_toggle":"Switch sidepanel side (left / right).",
        "tt.mute":       "Mute / unmute the preview audio.\nAlso: middle-click on the video.",
        "tt.popup":      "Focus mode: hides menus, video fills the window.\nDouble-click on video or Esc to return.",
        "tt.preview":    "Start / close preview with audio.\nWhile active you can capture and record without closing it.",
        "tt.screenshot": "Capture the current frame.\nTaken from the preview buffer (instant).\n\nShortcut: PrintScreen.\nCtrl+Click: open captures folder.",
        "tt.record":     "Start / stop video + audio recording.\nThe preview is never interrupted (master ffmpeg keeps running).\n\nCtrl+Click: open recordings folder.",
        "sec.devices":       "Devices",
        "sec.quality":       "Quality",
        "sec.preview_audio": "Preview & audio",
        "sec.capture":       "Screen capture",
        "sec.recording":     "Recording",
        "sec.folders":       "Output folders",
        "sec.system":        "System",
        "sys.state":         "State:",
        "sys.diagnostics":   "Diagnostics:",
        "sys.version":       "Version:",
        "sys.history":       "View changelog",
        "lbl.video":         "Video",
        "lbl.audio":         "Audio",
        "lbl.always_on_top": "Always on top",
        "lbl.volume":        "Volume",
        "lbl.audio_buffer":  "Audio buffer (ms)",
        "lbl.codec_video":   "Video codec",
        "lbl.preset":        "Preset",
        "lbl.crf":           "CRF (0-51)",
        "lbl.codec_audio":   "Audio codec",
        "lbl.bitrate":       "Audio bitrate",
        "lbl.container":     "Container",
        "lbl.folder":        "Folder",
        "lbl.shots_dir":     "Screenshots",
        "lbl.videos_dir":    "Videos",
        "lbl.clipboard":     "Copy to clipboard",
        "lbl.png":           "Save PNG file",
        "lbl.fmt_active":    "Active: {res} @ {fps}fps",
        "lbl.fmt_hardware":  "Hardware: {dev}",
        "lbl.fmt_loading":   "Querying formats...",
        "lbl.fmt_no_device": "(choose a video device)",
        "lbl.fmt_unsupported": "(unsupported)",
        "lbl.fmt_picker_tip": "Pick a resolution + FPS supported by your capture card.\nThe list is filtered to the detected hardware.",
        "lbl.video_placeholder": "(Start the preview to see video here)",
        "st.ready":             "Ready",
        "st.preview_active":    "Preview active",
        "st.preview_starting":  "Starting preview...",
        "st.start_preview_first": "Start the preview first",
        "st.capturing":         "Capturing...",
        "st.recording_to":      "Recording → {name}",
        "st.recording_saving":  "Stopping recording (finalizing file)...",
        "st.recording_saved":   "Recording saved · {msg}",
        "toast.shot_file":      "📷 Screenshot saved · {name}",
        "toast.shot_clip":      "📷 Screenshot to clipboard",
        "toast.rec_started":    "⏺ Recording started · {name}",
        "toast.rec_finalizing": "⏹ Finalizing recording...",
        "toast.rec_saved":      "✓ Recording saved · {msg}",
        "toast.rec_no_file":    "⚠ Recording produced no file",
    },
}


def t(key: str, lang: str = "es", **fmt) -> str:
    """Look up translation. Falls back to es, then to the key itself."""
    s = TRANSLATIONS.get(lang, {}).get(key)
    if s is None:
        s = TRANSLATIONS.get("es", {}).get(key, key)
    if fmt:
        try: return s.format(**fmt)
        except Exception: return s
    return s

_IS_WIN = platform.system() == "Windows"

# --------------------------------------------------------------------------- #
# Win32: embed ffplay window inside our Tk frame
# --------------------------------------------------------------------------- #
if _IS_WIN:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32

    _GWL_STYLE = -16
    _WS_OVERLAPPED = 0x00000000
    _WS_OVERLAPPEDWINDOW = 0x00CF0000
    _WS_POPUP = 0x80000000
    _WS_CHILD = 0x40000000
    _WS_VISIBLE = 0x10000000
    _WS_CAPTION = 0x00C00000
    _WS_BORDER = 0x00800000
    _WS_DLGFRAME = 0x00400000
    _WS_SYSMENU = 0x00080000
    _WS_THICKFRAME = 0x00040000
    _WS_MINIMIZEBOX = 0x00020000
    _WS_MAXIMIZEBOX = 0x00010000
    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_FRAMECHANGED = 0x0020
    _SWP_SHOWWINDOW = 0x0040
    _SWP_NOREDRAW = 0x0008
    _SWP_NOSENDCHANGING = 0x0400
    _SWP_NOCOPYBITS = 0x0100
    _SWP_DEFERERASE = 0x2000

    _EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    # ---- argtypes/restype: critico en Python 64-bit. Sin esto, los HWND
    # se truncan a 32 bits y SetParent/SetWindowLongPtr fallan en silencio.
    _user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
    _user32.SetParent.restype = wintypes.HWND
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    _user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    _user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.ClientToScreen.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.SystemParametersInfoW.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    _user32.SendMessageW.argtypes = [
        wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _user32.SendMessageW.restype = ctypes.c_void_p
    _user32.PostMessageW.argtypes = [
        wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.MoveWindow.argtypes = [
        wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.BOOL]
    _user32.MoveWindow.restype = wintypes.BOOL
    _user32.EnableWindow.argtypes = [wintypes.HWND, wintypes.BOOL]
    _user32.EnableWindow.restype = wintypes.BOOL


    def find_hwnd_by_pid_and_title(pid: int, title_substr: str):
        """Encuentra el primer HWND top-level de un proceso cuyo titulo contiene substr."""
        if not pid: return None
        found = [None]

        def cb(hwnd, _lparam):
            wp = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
            if wp.value != pid:
                return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if not length:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_substr in buf.value:
                found[0] = hwnd
                return False
            return True

        _user32.EnumWindows(_EnumWindowsProc(cb), 0)
        return found[0]


    def find_main_hwnd_for_pid(pid: int):
        """Encuentra la ventana visible mas grande de un proceso (sin requerir titulo).
        ffplay actualiza su titulo durante la reproduccion, asi que buscar por
        PID y tamano es mas confiable.
        """
        if not pid: return None
        candidates: list[tuple[int, int]] = []

        def cb(hwnd, _lparam):
            wp = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
            if wp.value != pid:
                return True
            if not _user32.IsWindowVisible(hwnd):
                return True
            parent = _user32.GetParent(hwnd)
            if parent:  # ya es hija de algo
                return True
            rect = wintypes.RECT()
            if _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                area = (rect.right - rect.left) * (rect.bottom - rect.top)
                if area > 200:
                    candidates.append((area, hwnd))
            return True

        _user32.EnumWindows(_EnumWindowsProc(cb), 0)
        if not candidates:
            return None
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]


    def embed_hwnd_at(child_hwnd, parent_hwnd, x: int, y: int, w: int, h: int) -> bool:
        """Reparenta child_hwnd como hijo de parent_hwnd en (x,y) y tamano (w,h).
        Verifica que SetParent haya tomado efecto leyendo GetParent."""
        if not child_hwnd or not parent_hwnd: return False
        try:
            style = _user32.GetWindowLongPtrW(child_hwnd, _GWL_STYLE) or 0
            style &= ~(_WS_OVERLAPPED | _WS_OVERLAPPEDWINDOW | _WS_POPUP |
                       _WS_CAPTION | _WS_BORDER | _WS_DLGFRAME | _WS_SYSMENU |
                       _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX)
            style |= _WS_CHILD | _WS_VISIBLE
            _user32.SetWindowLongPtrW(child_hwnd, _GWL_STYLE, style)
            _user32.SetParent(child_hwnd, parent_hwnd)
            ok = _user32.SetWindowPos(
                child_hwnd, 0, x, y, max(1, w), max(1, h),
                _SWP_NOZORDER | _SWP_FRAMECHANGED | _SWP_SHOWWINDOW)
            new_parent = _user32.GetParent(child_hwnd)
            return bool(ok) and (new_parent == parent_hwnd)
        except Exception:
            return False


    def resize_hwnd_at(hwnd, x: int, y: int, w: int, h: int,
                          *, fast: bool = False) -> bool:
        """Mueve/redimensiona hwnd. Si fast=True usa SetWindowPos sin
        repaint/sin WM_SIZE para frames intermedios de animaciones — el
        callsite debe hacer una llamada final con fast=False para que
        ffplay/SDL pinte la imagen al tamano correcto."""
        if not hwnd: return False
        try:
            w = max(1, w); h = max(1, h)
            if fast:
                # Frames intermedios: solo mover, sin redraw ni WM_SIZE.
                # ffplay queda con su ultimo frame escalado por el window
                # manager — bastante mas suave que provocar repintado
                # en cada step.
                return bool(_user32.SetWindowPos(
                    hwnd, 0, x, y, w, h,
                    _SWP_NOZORDER | _SWP_NOACTIVATE
                    | _SWP_NOREDRAW | _SWP_NOSENDCHANGING
                    | _SWP_DEFERERASE))
            # Final: MoveWindow con repaint=True + WM_SIZE para que SDL
            # rebobine el render al tamano nuevo.
            ok = bool(_user32.MoveWindow(hwnd, x, y, w, h, True))
            if not ok:
                ok = bool(_user32.SetWindowPos(
                    hwnd, 0, x, y, w, h,
                    _SWP_NOZORDER | _SWP_NOACTIVATE))
            WM_SIZE = 0x0005
            SIZE_RESTORED = 0
            lparam = ((h & 0xFFFF) << 16) | (w & 0xFFFF)
            try:
                _user32.SendMessageW(hwnd, WM_SIZE, SIZE_RESTORED, lparam)
            except Exception: pass
            return ok
        except Exception:
            return False


    def get_client_offset(hwnd) -> tuple[int, int]:
        """Coordenadas en pantalla del (0,0) del area cliente del HWND."""
        pt = wintypes.POINT(0, 0)
        try: _user32.ClientToScreen(hwnd, ctypes.byref(pt))
        except Exception: return 0, 0
        return pt.x, pt.y


    def post_keypress(hwnd, vk: int) -> bool:
        """Postea WM_KEYDOWN+WM_KEYUP a hwnd. Util para enviar shortcuts a
        ffplay (9/0 para volumen, m para mute)."""
        if not hwnd: return False
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        try:
            _user32.PostMessageW(hwnd, WM_KEYDOWN, vk, 0)
            _user32.PostMessageW(hwnd, WM_KEYUP, vk, 0)
            return True
        except Exception:
            return False
else:
    def find_hwnd_by_pid_and_title(pid, title_substr): return None
    def find_main_hwnd_for_pid(pid): return None
    def embed_hwnd_at(*_a, **_kw): return False
    def resize_hwnd_at(*_a, **_kw): return False  # type: ignore[misc]
    def get_client_offset(_h): return 0, 0
    def post_keypress(*_a, **_kw): return False


SUBPROC_FLAGS = 0
if platform.system() == "Windows":
    # Evita que cada subprocess abra ventanas de cmd cuando corremos con pythonw
    # o desde un .exe windowed.
    SUBPROC_FLAGS = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]

# pythonw.exe / --windowed builds tienen sys.stdout = None. Redirigir para que
# print() no explote en modulos ajenos (urllib, pip, etc.).
for _stream in ("stdout", "stderr"):
    if getattr(sys, _stream) is None:
        try:
            setattr(sys, _stream, open(os.devnull, "w"))
        except OSError:
            pass


HELP_TRANSLATIONS: dict[str, dict[str, tuple[str, str]]] = {
    "es": {
        "resolution": (
            "Resolucion de captura",
            "Tamano de imagen que captura ffmpeg. Debe ser un modo SOPORTADO\n"
            "por tu capturadora.\n\n"
            "  1920x1080 — Switch en dock, mejor calidad\n"
            "  1280x720  — Switch portable, o si la capturadora no soporta\n"
            "              1080p al fps deseado\n"
            "  3840x2160 — solo capturadoras 4K\n\n"
            "Si la combinacion resolucion+fps no es soportada, ffplay falla\n"
            "con 'Could not set video options'."
        ),
        "framerate": (
            "Cuadros por segundo (FPS)",
            "Velocidad de captura. Switch sale a 30 o 60 fps segun el juego.\n\n"
            "  60 — recomendado, movimiento fluido\n"
            "  30 — fallback si 60 no es soportado a esa resolucion"
        ),
        "always_on_top": (
            "Siempre visible (always on top)",
            "La ventana de vista previa se mantiene encima de las demas.\n"
            "Util para jugar con la preview como overlay en una esquina."
        ),
        "volume": (
            "Volumen de reproduccion",
            "Nivel del audio (0..100) durante la vista previa.\n"
            "Se aplica en vivo via la sesion de audio de Windows."
        ),
        "audio_buffer_size_ms": (
            "Buffer audio DirectShow (ms)",
            "Buffer interno que usa ffmpeg para leer el audio de la captura.\n\n"
            "    0 — default del driver\n"
            "   40 — minima latencia, arriesga dropouts\n"
            "   80 — balance bueno (recomendado)\n"
            "  120 — sin dropouts pero mas latencia\n"
            "  200 — solo si sigues con dropouts"
        ),
        "screenshot_dir": (
            "Carpeta de capturas",
            "Donde se guardan los PNG.\nDefault: ~/Pictures/SwitchCaps"
        ),
        "video_dir": (
            "Carpeta de grabaciones",
            "Donde se guardan los videos grabados.\nDefault: ~/Videos/SwitchCaps"
        ),
        "video_codec": (
            "Codec de video",
            "Como se comprime el video al grabar.\n\n"
            "  libx264    — H.264 software (CPU). Compatibilidad total.\n"
            "  libx265    — H.265 software. ~30% mas chico, ~2x CPU.\n"
            "  h264_nvenc — H.264 GPU NVIDIA. Casi 0% CPU.\n"
            "  hevc_nvenc — H.265 GPU NVIDIA. Mejor compresion.\n\n"
            "Si eliges nvenc y no tienes GPU NVIDIA, ffmpeg falla."
        ),
        "video_preset": (
            "Preset de codificacion",
            "Trade-off velocidad vs tamano de archivo.\n\n"
            "  ultrafast — maxima velocidad, archivos grandes\n"
            "  veryfast  — balance bueno (recomendado)\n"
            "  fast      — mejor compresion, mas CPU\n"
            "  medium    — referencia x264"
        ),
        "video_crf": (
            "CRF (Constant Rate Factor)",
            "Calidad visual; controla el tamano del archivo.\n\n"
            "   0  — sin perdida (~10x mas grande)\n"
            "  18  — visualmente sin perdida\n"
            "  20  — calidad excelente (recomendado)\n"
            "  23  — default x264\n"
            "  28+ — comprimido, perdida perceptible\n\n"
            "Cada +6 = ~mitad del bitrate."
        ),
        "audio_codec": (
            "Codec de audio",
            "  aac        — maxima compatibilidad (recomendado)\n"
            "  libopus    — mejor calidad/bitrate\n"
            "  libmp3lame — MP3 legacy\n\n"
            "Si tu contenedor es mp4, usa aac."
        ),
        "audio_bitrate": (
            "Bitrate de audio",
            "  128k — aceptable\n"
            "  192k — bueno (recomendado)\n"
            "  256k — excelente\n"
            "  320k — maximo"
        ),
        "container": (
            "Contenedor del archivo",
            "  mkv — maxima flexibilidad, soporta cualquier codec.\n"
            "         Resistente a crashes. Recomendado.\n"
            "  mp4 — maxima compatibilidad con players/redes sociales,\n"
            "         pero algunos codecs no son aceptados."
        ),
        "screenshot_to_clipboard": (
            "Captura → Portapapeles",
            "Copia la imagen al portapapeles ademas de guardar el PNG.\n"
            "Asi puedes pegarla con Ctrl+V en Discord, WhatsApp, etc."
        ),
        "screenshot_to_file": (
            "Captura → Archivo PNG",
            "Guarda un PNG en la carpeta configurada.\n"
            "Si lo desactivas, las capturas solo van al portapapeles."
        ),
    },
    "en": {
        "resolution": (
            "Capture resolution",
            "Image size ffmpeg captures. Must be a mode SUPPORTED by your\n"
            "capture card.\n\n"
            "  1920x1080 — Switch docked, best quality\n"
            "  1280x720  — Switch handheld, or if the card doesn't support\n"
            "              1080p at the desired fps\n"
            "  3840x2160 — only 4K capture cards\n\n"
            "If the resolution+fps combo isn't supported, ffplay fails with\n"
            "'Could not set video options'."
        ),
        "framerate": (
            "Frames per second (FPS)",
            "Capture rate. Switch outputs at 30 or 60 fps depending on game.\n\n"
            "  60 — recommended, smooth motion\n"
            "  30 — fallback if 60 isn't supported at that resolution"
        ),
        "always_on_top": (
            "Always on top",
            "Keeps the preview window above other windows.\n"
            "Handy when you want the preview as a corner overlay."
        ),
        "volume": (
            "Playback volume",
            "Audio level (0..100) during preview.\n"
            "Applied live via the Windows audio session."
        ),
        "audio_buffer_size_ms": (
            "DirectShow audio buffer (ms)",
            "Internal buffer ffmpeg uses to read audio from the capture card.\n\n"
            "    0 — driver default\n"
            "   40 — lowest latency, may drop\n"
            "   80 — sweet spot (recommended)\n"
            "  120 — no dropouts but more latency\n"
            "  200 — only if you still get dropouts"
        ),
        "screenshot_dir": (
            "Screenshots folder",
            "Where PNGs are saved.\nDefault: ~/Pictures/SwitchCaps"
        ),
        "video_dir": (
            "Recordings folder",
            "Where recorded videos are saved.\nDefault: ~/Videos/SwitchCaps"
        ),
        "video_codec": (
            "Video codec",
            "How the recording is compressed.\n\n"
            "  libx264    — H.264 software (CPU). Maximum compatibility.\n"
            "  libx265    — H.265 software. ~30% smaller, ~2x CPU.\n"
            "  h264_nvenc — H.264 NVIDIA GPU. Near zero CPU.\n"
            "  hevc_nvenc — H.265 NVIDIA GPU. Better compression.\n\n"
            "If you pick nvenc without an NVIDIA GPU, ffmpeg will fail."
        ),
        "video_preset": (
            "Encoding preset",
            "Speed vs file-size trade-off.\n\n"
            "  ultrafast — fastest, big files\n"
            "  veryfast  — good balance (recommended)\n"
            "  fast      — better compression, more CPU\n"
            "  medium    — x264 reference"
        ),
        "video_crf": (
            "CRF (Constant Rate Factor)",
            "Visual quality; controls file size.\n\n"
            "   0  — lossless (~10x larger)\n"
            "  18  — visually lossless\n"
            "  20  — excellent (recommended)\n"
            "  23  — x264 default\n"
            "  28+ — compressed, perceptible loss\n\n"
            "Every +6 ≈ half the bitrate."
        ),
        "audio_codec": (
            "Audio codec",
            "  aac        — maximum compatibility (recommended)\n"
            "  libopus    — best quality/bitrate\n"
            "  libmp3lame — legacy MP3\n\n"
            "If your container is mp4, use aac."
        ),
        "audio_bitrate": (
            "Audio bitrate",
            "  128k — acceptable\n"
            "  192k — good (recommended)\n"
            "  256k — excellent\n"
            "  320k — maximum"
        ),
        "container": (
            "File container",
            "  mkv — maximum flexibility, any codec supported.\n"
            "         Crash-resistant. Recommended.\n"
            "  mp4 — maximum player/social-network compatibility,\n"
            "         but some codecs aren't accepted."
        ),
        "screenshot_to_clipboard": (
            "Screenshot → Clipboard",
            "Copies the image to clipboard in addition to saving the PNG.\n"
            "Paste with Ctrl+V into Discord, WhatsApp, etc."
        ),
        "screenshot_to_file": (
            "Screenshot → PNG file",
            "Saves a PNG in the configured folder.\n"
            "If disabled, screenshots only go to the clipboard."
        ),
    },
}


DEFAULTS: dict = {
    "video_device": None,
    "audio_device": None,
    "resolution": "1920x1080",
    "framerate": 60,
    "window_mode": "windowed",            # windowed | fullscreen | borderless
    "always_on_top": False,
    "volume": 80,                          # 0..100 (-volume de ffplay)
    "audio_buffer_size_ms": 80,            # buffer DirectShow del audio (ms)
    "screenshot_dir": str(Path.home() / "Pictures" / "SwitchCaps"),
    "video_dir": str(Path.home() / "Videos" / "SwitchCaps"),
    "screenshot_to_clipboard": True,
    "screenshot_to_file": True,
    "video_codec": "libx264",
    "video_preset": "veryfast",
    "video_crf": 20,
    "audio_codec": "aac",
    "audio_bitrate": "192k",
    "container": "mkv",
    "show_preview_while_recording": True,
    "audio_passthrough_during_record": True,
    "shortcut_offered": False,            # ya preguntamos por crear acceso directo
    "theme": "light",                     # light | dark
    "muted": False,
    "language": "es",                     # ISO 639-1: es | en | ...
    "sidebar_side": "right",              # right | left
    # Layout persistente: el user puede reordenar los menus con ↑/↓ y
    # colapsarlos con ▼/▶. Guardamos su preferencia para que no tenga
    # que reconfigurar el layout cada vez que abre la app.
    "panel_order": [],                    # ej. ["sec.devices", "sec.quality", ...]
    "panel_collapsed": {},                # ej. {"sec.system": True}
    "window_geometry": "",                # "WxH+X+Y" del Tk root
}


def load_config() -> dict:
    cfg = DEFAULTS.copy()
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Tools / devices
# --------------------------------------------------------------------------- #
def check_tools(quiet: bool = False) -> bool:
    missing = [t for t in ("ffmpeg", "ffplay") if not shutil.which(t)]
    if missing and not quiet:
        print(f"[!] No se encontraron en PATH: {', '.join(missing)}")
    return not missing


def check_clipboard_deps() -> bool:
    try:
        import PIL  # noqa: F401
        import win32clipboard  # noqa: F401
        return True
    except ImportError:
        return False


def list_dshow_devices() -> tuple[list[str], list[str]]:
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=SUBPROC_FLAGS,
    )
    out = (p.stderr or "") + (p.stdout or "")
    video: list[str] = []
    audio: list[str] = []
    for line in out.splitlines():
        m = re.search(r'"([^"]+)"\s*\((video|audio)\)', line)
        if m:
            (video if m.group(2) == "video" else audio).append(m.group(1))
    if not video and not audio:
        kind = None
        for line in out.splitlines():
            if "DirectShow video devices" in line: kind = "video"; continue
            if "DirectShow audio devices" in line: kind = "audio"; continue
            m = re.search(r'"([^"]+)"', line)
            if m and kind:
                (video if kind == "video" else audio).append(m.group(1))

    def uniq(xs: list[str]) -> list[str]:
        seen: set[str] = set(); res: list[str] = []
        for x in xs:
            if x not in seen: seen.add(x); res.append(x)
        return res
    return uniq(video), uniq(audio)


def query_supported_formats(device_name: str) -> dict[str, float]:
    """Consulta los formatos soportados por un dispositivo de video DirectShow.

    Retorna {resolucion: fps_max}, p.ej. {'1920x1080': 30.0, '1280x720': 60.0}.
    """
    if not shutil.which("ffmpeg") or not device_name:
        return {}
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-f", "dshow",
             "-list_options", "true", "-i", f"video={device_name}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=SUBPROC_FLAGS, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    out = (p.stderr or "") + (p.stdout or "")
    formats: dict[str, float] = {}
    for line in out.splitlines():
        m = re.search(r'max\s+s=(\d+x\d+)\s+fps=([\d.]+)', line)
        if m:
            res = m.group(1)
            try:
                fps = float(m.group(2))
            except ValueError:
                continue
            if res not in formats or formats[res] < fps:
                formats[res] = fps
    return formats


def detect_gpu_vendor() -> str:
    """Detecta vendor de GPU. Retorna 'nvidia', 'amd', 'intel', o 'unknown'."""
    # nvidia-smi es la forma mas rapida y confiable si esta NVIDIA
    try:
        r = subprocess.run(["nvidia-smi", "-L"],
                           capture_output=True, timeout=2,
                           creationflags=SUBPROC_FLAGS)
        if r.returncode == 0 and b"GPU" in r.stdout:
            return "nvidia"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    # Fallback: WMIC
    try:
        r = subprocess.run(
            ["wmic", "path", "Win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=5,
            creationflags=SUBPROC_FLAGS,
        )
        out = (r.stdout or "").lower()
        if any(s in out for s in ("nvidia", "geforce", "rtx", "gtx", "quadro")):
            return "nvidia"
        if any(s in out for s in ("amd", "radeon")):
            return "amd"
        if "intel" in out:
            return "intel"
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


def compute_diagnostics(cfg: dict, formats: dict[str, float] | None,
                        gpu: str) -> list[dict]:
    """Calcula warnings/errors segun config + hardware.

    Cada item es:
      {"severity": "error|warn|ok|info",
       "message":  "texto",
       "fixes":    [{"label": "Boton", "changes": {key: value, ...}}, ...]  (opcional)}
    """
    out: list[dict] = []

    def add(sev: str, msg: str, *fixes: dict) -> None:
        item: dict = {"severity": sev, "message": msg}
        if fixes:
            item["fixes"] = list(fixes)
        out.append(item)

    # ---- ffmpeg / device ----
    if not check_tools(quiet=True):
        add("error", f"Faltan ffmpeg.exe/ffplay.exe en {LOCAL_BIN}.")
    if not cfg.get("video_device"):
        add("error", "No has elegido un dispositivo de video.")

    # ---- Resolucion + FPS vs formatos soportados ----
    res = cfg.get("resolution", "")
    fps = float(cfg.get("framerate", 60))
    if formats and res:
        max_fps_here = formats.get(res)
        if max_fps_here is None:
            try:
                cur_w, cur_h = res.split("x")
                cur_area = int(cur_w) * int(cur_h)
            except Exception:
                cur_area = 0

            def _area(r: str) -> int:
                try: w, h = r.split("x"); return int(w) * int(h)
                except Exception: return 0

            best_res = min(formats.keys(),
                            key=lambda r: abs(_area(r) - cur_area), default=None)
            fixes: list[dict] = []
            if best_res:
                best_fps = formats[best_res]
                pick = 60 if best_fps + 0.5 >= 60 else int(best_fps)
                fixes.append({
                    "label": f"Cambiar a {best_res} @ {pick}fps",
                    "changes": {"resolution": best_res, "framerate": pick},
                })
            sug = " · ".join(sorted(formats.keys())[:3])
            add("error",
                f"Tu capturadora NO soporta {res}. Disponibles: {sug}",
                *fixes)
        elif max_fps_here + 0.5 < fps:
            target_fps = int(max_fps_here)
            fixes = [{"label": f"Bajar a {target_fps} fps",
                      "changes": {"framerate": target_fps}}]
            cap = sorted(
                ((r, f) for r, f in formats.items() if f + 0.5 >= fps),
                key=lambda x: -(int(x[0].split("x")[0]) * int(x[0].split("x")[1])),
            )
            if cap:
                alt_res = cap[0][0]
                fixes.append({
                    "label": f"Cambiar a {alt_res} @ {int(fps)}fps",
                    "changes": {"resolution": alt_res,
                                 "framerate": int(fps)},
                })
            add("error",
                f"{res} solo soporta hasta {target_fps}fps, "
                f"pero pediste {int(fps)}fps.",
                *fixes)

    # ---- Codec NVENC sin GPU NVIDIA ----
    codec = cfg.get("video_codec", "")
    if "nvenc" in codec and gpu != "nvidia":
        replacement = "libx265" if codec == "hevc_nvenc" else "libx264"
        add("error",
            f"Codec '{codec}' requiere GPU NVIDIA, "
            f"pero tu sistema reporta '{gpu}'.",
            {"label": f"Cambiar a {replacement}",
             "changes": {"video_codec": replacement}})

    # ---- libx265 + preset pesado ----
    if codec == "libx265":
        preset = cfg.get("video_preset", "")
        if preset in ("medium", "slow", "slower", "veryslow"):
            fixes = [{"label": "Bajar preset a veryfast",
                      "changes": {"video_preset": "veryfast"}}]
            if gpu == "nvidia":
                fixes.append({"label": "Usar hevc_nvenc (GPU)",
                              "changes": {"video_codec": "hevc_nvenc"}})
            add("warn",
                f"libx265 + preset '{preset}' es muy pesado; puede causar "
                f"drops al grabar 1080p60.",
                *fixes)

    # ---- libx264 a 1080p120 con preset pesado ----
    if codec == "libx264" and fps >= 100 and "1920" in res:
        preset = cfg.get("video_preset", "")
        if preset not in ("ultrafast", "superfast"):
            fixes = [{"label": "Bajar preset a ultrafast",
                      "changes": {"video_preset": "ultrafast"}}]
            if gpu == "nvidia":
                fixes.append({"label": "Usar h264_nvenc (GPU)",
                              "changes": {"video_codec": "h264_nvenc"}})
            add("warn",
                f"libx264 a 1080p{int(fps)} con preset '{preset}' satura CPU.",
                *fixes)

    # ---- Audio buffer bajo ----
    buf = int(cfg.get("audio_buffer_size_ms", 80) or 0)
    if 0 < buf < 60:
        add("warn",
            f"Buffer audio = {buf} ms es bajo; el audio puede oirse choppy.",
            {"label": "Subir a 80 ms",
             "changes": {"audio_buffer_size_ms": 80}})

    # ---- mp4 + opus ----
    if cfg.get("container") == "mp4" and cfg.get("audio_codec") == "libopus":
        add("warn",
            "MP4 con libopus puede no reproducirse en algunos players.",
            {"label": "Cambiar audio a aac",
             "changes": {"audio_codec": "aac"}},
            {"label": "Cambiar contenedor a mkv",
             "changes": {"container": "mkv"}})

    # ---- pillow + pywin32 ----
    if not check_clipboard_deps() and not IS_FROZEN:
        if cfg.get("screenshot_to_clipboard"):
            add("warn",
                "Captura → portapapeles activo, pero faltan pillow+pywin32. "
                "Solo se guardara PNG.",
                {"label": "Desactivar clipboard",
                 "changes": {"screenshot_to_clipboard": False}})

    if not out:
        add("ok", "Todo OK · listo para iniciar la vista previa.")
    return out


# --------------------------------------------------------------------------- #
# Installer (verificacion de binarios locales + python deps)
#
# El paquete viene con ffmpeg.exe / ffplay.exe en ./bin/. NO se descarga nada
# desde internet. Si los binarios faltan, el "instalador" reporta donde
# colocarlos manualmente.
# --------------------------------------------------------------------------- #
def install_python_deps(progress=print) -> bool:
    if IS_FROZEN:
        progress("[i] El .exe ya empaca pillow/pywin32.")
        return True
    if check_clipboard_deps():
        progress("pillow + pywin32 ya estan instalados.")
        return True
    req = SCRIPT_DIR / "requirements.txt"
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if req.exists():
        cmd += ["-r", str(req)]
    else:
        cmd += ["pillow", "pywin32"]
    progress(">>> " + " ".join(cmd))
    try:
        return subprocess.run(cmd, creationflags=SUBPROC_FLAGS).returncode == 0
    except Exception as e:
        progress(f"[!] Error pip: {e}")
        return False


def install_ffmpeg(force: bool = False, progress=print) -> bool:
    """Verifica que ffmpeg/ffplay esten disponibles. NO descarga nada.

    Busca en este orden:
      1. PATH del sistema
      2. {SCRIPT_DIR}/bin/ (binarios bundleados con el paquete)
    Si faltan, indica al usuario donde colocarlos.
    """
    # 1) PATH del sistema
    sys_ff = shutil.which("ffmpeg")
    sys_fp = shutil.which("ffplay")
    if sys_ff and sys_fp:
        progress(f"ffmpeg en PATH: {sys_ff}")
        progress(f"ffplay en PATH: {sys_fp}")
        return True

    # 2) Binarios locales bundleados
    local_ff = LOCAL_BIN / "ffmpeg.exe"
    local_fp = LOCAL_BIN / "ffplay.exe"
    if local_ff.exists() and local_fp.exists():
        os.environ["PATH"] = str(LOCAL_BIN) + os.pathsep + os.environ.get("PATH", "")
        progress(f"ffmpeg local: {local_ff}")
        progress(f"ffplay local: {local_fp}")
        return True

    # No estan
    progress("[!] No se encontraron ffmpeg.exe / ffplay.exe.")
    progress(f"    Coloca los binarios en: {LOCAL_BIN}")
    progress("    (o agrega ffmpeg al PATH del sistema).")
    return False


# --------------------------------------------------------------------------- #
# Backend primitives (no-bloqueantes para la GUI)
# --------------------------------------------------------------------------- #
def _common_input_args(cfg: dict, want_audio: bool = True) -> list[str]:
    args = ["-f", "dshow", "-rtbufsize", "256M",
            "-video_size", cfg["resolution"],
            "-framerate", str(cfg["framerate"])]
    vd = cfg["video_device"]
    ad = cfg.get("audio_device") if want_audio else None
    if ad:
        args += ["-i", f"video={vd}:audio={ad}"]
    else:
        args += ["-i", f"video={vd}"]
    return args


def _open_log(name: str):
    """Abre un archivo de log para capturar stderr de un subproceso."""
    path = SCRIPT_DIR / f".last_{name}.log"
    return path, open(path, "wb")


def read_proc_log(proc: subprocess.Popen) -> str:
    """Lee el log capturado del subproceso (stderr); cierra el handle."""
    h = getattr(proc, "_log_handle", None)
    if h:
        try: h.flush(); h.close()
        except Exception: pass
        proc._log_handle = None  # type: ignore[attr-defined]
    path = getattr(proc, "_log_path", None)
    if path and Path(path).exists():
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def extract_ffmpeg_error(log: str) -> str:
    """Extrae las lineas relevantes de error de un log de ffmpeg/ffplay.

    Ignora 'broken pipe' / error code -32 que son normales al cerrar ffplay.
    """
    if not log: return ""
    benign = ("broken pipe", "error code: -32", "task finished with error code: -32")
    keys = ("could not", "i/o error", "no such", "failed", "invalid",
            "unsupported", "error", "permission")
    matches = []
    for ln in log.splitlines():
        s = ln.strip()
        if not s: continue
        low = s.lower()
        if any(b in low for b in benign): continue
        if any(k in low for k in keys):
            matches.append(s)
    if matches:
        seen, out = set(), []
        for m in matches:
            if m not in seen: seen.add(m); out.append(m)
        return "\n".join(out[-6:])
    return ""


LATEST_FRAME = SCRIPT_DIR / ".latest_frame.png"


class _StreamTee:
    """Lee de una source pipe y replica los chunks a multiples consumers
    en paralelo. Detectamos donde termina el header matroska (justo antes
    del primer Cluster, EBML ID 0x1F43B675) y guardamos solo eso como
    'init segment'. Asi un consumer mid-stream recibe header limpio +
    datos live, sin mezclar frames viejos.
    """
    HEADER_MAX_SCAN = 256 * 1024
    CLUSTER_ID = b'\x1f\x43\xb6\x75'  # matroska Cluster element ID

    def __init__(self, source):
        self.source = source
        self._lock = threading.Lock()
        self._consumers: dict[str, dict] = {}
        self._scan_buf = b""
        self._init_segment: bytes | None = None
        self._reader_stop = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self) -> None:
        try:
            while not self._reader_stop:
                chunk = self.source.read(65536)
                if not chunk: break
                with self._lock:
                    # Aun no detectamos donde termina el header? Acumular y buscar
                    if self._init_segment is None:
                        self._scan_buf += chunk
                        pos = self._scan_buf.find(self.CLUSTER_ID)
                        if pos >= 0:
                            self._init_segment = self._scan_buf[:pos]
                            self._scan_buf = b""  # ya no necesitamos
                        elif len(self._scan_buf) >= self.HEADER_MAX_SCAN:
                            # Fallback: usamos los primeros 8KB
                            self._init_segment = self._scan_buf[:8192]
                            self._scan_buf = b""
                    for name, c in list(self._consumers.items()):
                        try:
                            c["q"].put(chunk, timeout=2.0)
                        except queue.Full:
                            self._remove_locked(name)
        except Exception:
            pass

    def _writer_loop(self, c: dict) -> None:
        q, dst = c["q"], c["dst"]
        while True:
            chunk = q.get()
            if chunk is None: break
            try:
                dst.write(chunk)
            except Exception:
                break
        try: dst.close()
        except Exception: pass

    def add(self, name: str, dst, queue_max: int = 512,
            replay_header: bool = True) -> None:
        """Agrega un consumer (pipe-like con write/close).
        Si replay_header=True y ya tenemos init segment, se lo enviamos
        antes de los chunks live (necesario para mid-stream pickup)."""
        c = {"q": queue.Queue(maxsize=queue_max), "dst": dst}
        c["thread"] = threading.Thread(
            target=self._writer_loop, args=(c,), daemon=True)
        with self._lock:
            if replay_header and self._init_segment:
                try: c["q"].put(self._init_segment, timeout=0.5)
                except queue.Full: pass
            self._consumers[name] = c
        c["thread"].start()

    def remove(self, name: str) -> None:
        with self._lock:
            self._remove_locked(name)

    def _remove_locked(self, name: str) -> None:
        c = self._consumers.pop(name, None)
        if c:
            try: c["q"].put(None, timeout=0.1)
            except Exception: pass

    def stop(self) -> None:
        self._reader_stop = True
        with self._lock:
            for name in list(self._consumers.keys()):
                self._remove_locked(name)


def _master_args(cfg: dict, recording_path: Path | None = None) -> list[str]:
    """Master ffmpeg: dshow input, stream copy a stdout en formato 'nut'
    (apto para mid-stream pickup) + latest_frame.png a 5fps.

    El parametro recording_path se mantiene por compatibilidad pero ya
    NO se usa: la grabacion vive en un proceso aparte (ver _recorder_args).
    """
    has_audio = bool(cfg.get("audio_device"))

    args = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]

    args += ["-f", "dshow",
             "-rtbufsize", "100M",
             "-thread_queue_size", "512",
             "-video_size", cfg["resolution"],
             "-framerate", str(cfg["framerate"])]
    if has_audio and cfg.get("audio_buffer_size_ms"):
        args += ["-audio_buffer_size", str(cfg["audio_buffer_size_ms"])]
    vd = cfg["video_device"]
    if has_audio:
        args += ["-i", f"video={vd}:audio={cfg['audio_device']}"]
    else:
        args += ["-i", f"video={vd}"]

    # Output 1: matroska a stdout (soporta MJPEG sin re-encode).
    # El tee guarda los primeros 64KB para replicarlos a consumers que se
    # conectan mid-stream (ej. recorder iniciado a mitad del preview).
    args += ["-map", "0:v:0"]
    if has_audio:
        args += ["-map", "0:a:0"]
    args += ["-c:v", "copy"]
    if has_audio:
        args += ["-c:a", "pcm_s16le"]
    args += ["-flush_packets", "1",
             "-cluster_time_limit", "100",   # 100ms clusters: data fluye al pipe rapido
             "-cluster_size_limit", "200000",
             "-f", "matroska", "pipe:1"]

    # Output 2: latest_frame.png a 5fps
    args += ["-map", "0:v:0", "-an",
             "-vf", "fps=5",
             "-update", "1", "-y",
             "-pix_fmt", "rgb24",
             "-compression_level", "1",
             str(LATEST_FRAME)]
    return args


def _recorder_args(cfg: dict, out_file: Path) -> list[str]:
    """Args del recorder: lee matroska de stdin (lo que tee'a el master) y
    re-encodea con el codec/preset elegidos por el user.

    Sin -map (auto-pick: ffmpeg toma 1 video + 1 audio segun probe).
    """
    has_audio = bool(cfg.get("audio_device"))
    args = ["ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-fflags", "+genpts+igndts+discardcorrupt",
            "-err_detect", "ignore_err",
            "-f", "matroska", "-i", "pipe:0"]
    args += ["-c:v", cfg["video_codec"],
             "-preset", cfg["video_preset"],
             "-crf", str(cfg["video_crf"]),
             "-pix_fmt", "yuv420p",
             # Tag explicito BT.709 TV-range para que players (VLC, mpv,
             # browsers) interpreten igual que el preview de ffplay y no
             # apliquen un color-stretch que blanquea los brillos.
             "-color_range", "tv",
             "-colorspace", "bt709",
             "-color_primaries", "bt709",
             "-color_trc", "bt709"]
    if has_audio:
        args += ["-c:a", cfg["audio_codec"],
                 "-b:a", cfg["audio_bitrate"]]
    args += ["-y", str(out_file)]
    return args


def start_master(cfg: dict, recording: bool = False,
                 window_title: str | None = None,
                 for_embed: bool = False) -> dict:
    """Lanza master ffmpeg + ffplay con un Python tee en medio.
    Si recording=True, tambien arranca el recorder y lo conecta al tee.
    El recorder se puede agregar/quitar despues sin reiniciar nada
    (ver add_recorder / remove_recorder).
    """
    args = _master_args(cfg)
    log_path, log_h = _open_log("master")

    # Master ffmpeg: stdout es donde sale el stream nut
    ffmpeg_p = subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=log_h, creationflags=SUBPROC_FLAGS,
    )
    ffmpeg_p._log_path = str(log_path)    # type: ignore[attr-defined]
    ffmpeg_p._log_handle = log_h           # type: ignore[attr-defined]

    # Tee: lee de master.stdout, replica a los consumers (ffplay, recorder)
    tee = _StreamTee(ffmpeg_p.stdout)

    # ffplay: visor (ventana + audio). Lee del tee, no directo del master.
    vol = max(0, min(100, int(cfg.get("volume", 80))))
    title = window_title or f"{APP_NAME} - Preview"
    ffplay_args = [
        "ffplay", "-hide_banner", "-loglevel", "warning",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-sync", "ext",
        "-volume", str(vol),
        "-window_title", title,
        "-framedrop",
    ]
    if not for_embed:
        if cfg.get("window_mode") == "fullscreen":
            ffplay_args.append("-fs")
        elif cfg.get("window_mode") == "borderless":
            ffplay_args.append("-noborder")
        if cfg.get("always_on_top"):
            ffplay_args.append("-alwaysontop")
    ffplay_args.append("-")

    ffplay_p = subprocess.Popen(
        ffplay_args, stdin=subprocess.PIPE,
        stderr=subprocess.DEVNULL, creationflags=SUBPROC_FLAGS,
    )
    tee.add("ffplay", ffplay_p.stdin)

    session = {
        "ffmpeg": ffmpeg_p,
        "ffplay": ffplay_p,
        "tee": tee,
        "recorder": None,
        "out_file": None,
        "recording": False,
        "start_time": None,
        "window_title": title,
    }

    if recording:
        try: add_recorder(session, cfg)
        except Exception: pass

    return session


def add_recorder(session: dict, cfg: dict) -> Path | None:
    """Conecta un proceso recorder al tee del master sin reiniciar nada.
    Devuelve el path del archivo de grabacion."""
    if session.get("recorder") is not None:
        return session.get("out_file")
    Path(cfg["video_dir"]).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = Path(cfg["video_dir"]) / f"switch_{ts}.{cfg['container']}"

    args = _recorder_args(cfg, out_file)
    log_path, log_h = _open_log("recorder")
    rec = subprocess.Popen(
        args, stdin=subprocess.PIPE, stderr=log_h,
        creationflags=SUBPROC_FLAGS,
    )
    rec._log_path = str(log_path)        # type: ignore[attr-defined]
    rec._log_handle = log_h               # type: ignore[attr-defined]
    session["tee"].add("recorder", rec.stdin)
    session["recorder"] = rec
    session["out_file"] = out_file
    session["recording"] = True
    session["start_time"] = time.time()
    return out_file


def remove_recorder(session: dict) -> tuple[Path | None, str]:
    """Desconecta el recorder del tee, le manda EOF inmediato y lo deja
    flush'ear el archivo. Si tarda mas de 3s, escalamos a terminate/kill.
    """
    rec = session.get("recorder")
    out = session.get("out_file")
    if rec is None:
        session["recording"] = False
        session["start_time"] = None
        return None, ""
    # 1) Sacar del tee para que no le manden mas chunks. La cola interna
    #    todavia podria tener bytes encolados (hasta ~32MB), pero ya no le
    #    pasamos data nueva.
    try: session["tee"].remove("recorder")
    except Exception: pass
    # 2) Cerrar stdin del recorder DIRECTAMENTE -> EOF inmediato.
    #    No esperamos a que el writer thread del tee drene su cola.
    try: rec.stdin.close()
    except Exception: pass
    # 3) Esperar finalizacion. ffmpeg deberia flush'ear y salir en <2s.
    try: rec.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try: rec.terminate()
        except Exception: pass
        try: rec.wait(timeout=2)
        except Exception:
            try: rec.kill()
            except Exception: pass
    read_proc_log(rec)
    session["recorder"] = None
    session["out_file"] = None
    session["recording"] = False
    session["start_time"] = None
    if out and out.exists():
        sz = out.stat().st_size / (1024 * 1024)
        return out, f"{out.name} ({sz:.1f} MB)"
    return None, ""


def stop_master(session: dict) -> tuple[Path | None, str]:
    """Detiene master + ffplay + recorder (si activo) limpiamente."""
    rec_msg = ""
    rec_out: Path | None = None
    if session.get("recorder") is not None:
        rec_out, rec_msg = remove_recorder(session)
    # Stop tee
    try: session["tee"].stop()
    except Exception: pass
    # Stop master ffmpeg
    p = session["ffmpeg"]
    try:
        if p.stdin:
            try:
                p.stdin.write(b"q\n"); p.stdin.flush()
            except (BrokenPipeError, OSError): pass
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired: p.kill()
    # Stop ffplay
    ff = session.get("ffplay")
    if ff is not None:
        try:
            if ff.stdin: ff.stdin.close()
        except Exception: pass
        try: ff.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try: ff.terminate()
            except Exception: pass
    read_proc_log(p)
    if rec_out:
        return rec_out, rec_msg
    return None, ""


# Compatibilidad: start_preview/start_record/stop_record llaman al master.
def start_preview(cfg: dict) -> subprocess.Popen:
    """Wrapper compat para CLI. Usa start_master internamente."""
    s = start_master(cfg, recording=False)
    p = s["ffmpeg"]
    p._session = s  # type: ignore[attr-defined]
    return p


def copy_image_to_clipboard(path: Path) -> bool:
    try:
        from PIL import Image
        import win32clipboard  # type: ignore
    except ImportError:
        return False
    try:
        img = Image.open(path).convert("RGB")
        buf = BytesIO()
        img.save(buf, "BMP")
        data = buf.getvalue()[14:]
        buf.close()
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        return False


def take_screenshot(cfg: dict, to_clipboard: bool | None = None,
                    to_file: bool | None = None,
                    master_running: bool = False) -> tuple[Path | None, str]:
    """Captura.

    Si el master esta corriendo, copia LATEST_FRAME (sin tocar el device).
    Si no, abre el device por un solo frame (modo CLI puro).
    """
    to_clipboard = cfg["screenshot_to_clipboard"] if to_clipboard is None else to_clipboard
    to_file = cfg["screenshot_to_file"] if to_file is None else to_file
    Path(cfg["screenshot_dir"]).mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    out = Path(cfg["screenshot_dir"]) / f"switch_{ts}.png"

    if master_running and LATEST_FRAME.exists():
        # Camino rapido: copia el frame mas reciente del buffer.
        try:
            shutil.copy2(LATEST_FRAME, out)
        except Exception as e:
            return None, f"Error copiando frame: {e}"
        parts = [f"Guardado: {out.name} (del buffer)"]
        if to_clipboard and copy_image_to_clipboard(out):
            parts.append("portapapeles OK")
        if not to_file:
            try: out.unlink()
            except OSError: pass
            return None, " · ".join(parts)
        return out, " · ".join(parts)

    # Modo CLI / device libre: capturar un frame directo
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "dshow",
            "-video_size", cfg["resolution"],
            "-framerate", str(cfg["framerate"]),
            "-i", f"video={cfg['video_device']}",
            "-frames:v", "1", "-pix_fmt", "rgb24",
            "-compression_level", "1", str(out)]
    r = subprocess.run(args, creationflags=SUBPROC_FLAGS,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not out.exists():
        return None, "Error: dispositivo ocupado o config invalida."
    parts = [f"Guardado: {out.name}"]
    if to_clipboard and copy_image_to_clipboard(out):
        parts.append("portapapeles OK")
    if not to_file:
        try: out.unlink()
        except OSError: pass
        return None, " · ".join(parts)
    return out, " · ".join(parts)


def start_record(cfg: dict, with_preview: bool | None = None,
                 audio_passthrough: bool | None = None) -> dict:
    """Wrapper compat para CLI. Usa el master con recording=True."""
    return start_master(cfg, recording=True)


def stop_record(session: dict) -> tuple[Path | None, str]:
    return stop_master(session)


# --------------------------------------------------------------------------- #
# Shortcut + build
# --------------------------------------------------------------------------- #
def _find_pythonw() -> str:
    """Localiza pythonw.exe (sin consola) cerca del python.exe actual."""
    if IS_FROZEN:
        return sys.executable
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")
    return str(pyw if pyw.exists() else py)


def _desktop_dir() -> Path | None:
    for d in (Path.home() / "Desktop",
              Path.home() / "OneDrive" / "Desktop"):
        if d.exists():
            return d
    return None


def make_shortcut(name: str = APP_NAME) -> tuple[bool, str]:
    """Crea un .lnk en el Escritorio que arranca la GUI sin ventana de consola."""
    desktop = _desktop_dir()
    if not desktop:
        return False, "No se encontro la carpeta Escritorio."
    lnk = desktop / f"{name}.lnk"

    exe_path = SCRIPT_DIR / f"{APP_ID}.exe"
    if exe_path.exists():
        target, args = str(exe_path), ""
        icon = str(ICON_ICO) if ICON_ICO else str(exe_path)
    else:
        target = _find_pythonw()
        # Conserva el nombre del script real (no asumimos ccv.py).
        args = f'"{SCRIPT_DIR / Path(__file__).name}"'
        icon = str(ICON_ICO) if ICON_ICO else target
    workdir = str(SCRIPT_DIR)

    ps = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{lnk}'); "
        f"$sc.TargetPath = '{target}'; "
        f"$sc.Arguments = '{args}'; "
        f"$sc.WorkingDirectory = '{workdir}'; "
        f"$sc.IconLocation = '{icon},0'; "
        f"$sc.Save()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       capture_output=True, text=True, creationflags=SUBPROC_FLAGS)
    if r.returncode != 0:
        return False, f"Error: {r.stderr.strip() or r.stdout.strip()}"
    return True, str(lnk)


def build_exe(onedir: bool = False) -> int:
    """Compila ccv.exe via PyInstaller.

    onedir=False (default): --onefile, .exe portable pero con startup lento
                            (~1-2s extra para extraer a tmp).
    onedir=True:            --onedir, output es una carpeta `ccv/` con
                            ccv.exe + libs adyacentes; startup ~instant.
    """
    if IS_FROZEN:
        print("[!] Ya estas corriendo dentro del .exe.")
        return 1
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Instalando PyInstaller...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"],
                           creationflags=SUBPROC_FLAGS)
        if r.returncode != 0:
            print("[!] Falla al instalar PyInstaller.")
            return r.returncode

    work = SCRIPT_DIR / "_pyinstaller"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_ID,
        ("--onedir" if onedir else "--onefile"),
        "--windowed",
        "--noconfirm",
        "--clean",
        "--distpath", str(SCRIPT_DIR),
        "--workpath", str(work / "build"),
        "--specpath", str(work),
        # Modulos detectados mal por PyInstaller (los importamos lazy o
        # via __import__).
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "win32clipboard",
        "--hidden-import", "pycaw",
        "--hidden-import", "pycaw.pycaw",
        "--hidden-import", "comtypes",
        "--hidden-import", "comtypes.client",
    ]
    # Icono del .exe (usado por Windows Explorer + barra de tareas).
    if ICON_ICO is not None:
        cmd += ["--icon", str(ICON_ICO)]
        print(f"[i] Using icon: {ICON_ICO}")
    # Assets: bundlear PNG + ICO dentro del exe.
    assets_dir = SCRIPT_DIR / "assets"
    if assets_dir.exists():
        for f in assets_dir.iterdir():
            if f.suffix.lower() in (".png", ".ico"):
                cmd += ["--add-data", f"{f}{os.pathsep}assets"]
    # Bundle bin/ con ffmpeg.exe + ffplay.exe si existe localmente:
    # asi el .exe no depende de que el user tenga ffmpeg en PATH.
    bin_dir = SCRIPT_DIR / "bin"
    if bin_dir.exists() and any(bin_dir.iterdir()):
        cmd += ["--add-binary", f"{bin_dir}{os.pathsep}bin"]
        print(f"[i] Bundling {bin_dir} -> bin/")
    cmd.append(str(SCRIPT_DIR / Path(__file__).name))
    print(">>> " + " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        print("[!] Build fallo.")
        return r.returncode
    shutil.rmtree(work, ignore_errors=True)
    exe = SCRIPT_DIR / f"{APP_ID}.exe"
    if onedir:
        exe = SCRIPT_DIR / APP_ID / f"{APP_ID}.exe"
    if exe.exists():
        size = exe.stat().st_size / (1024 * 1024)
        print(f"\n[OK] {exe}  ({size:.1f} MB)")
        if onedir:
            print(f"[i] Distribuye la carpeta completa: {exe.parent}")
    return 0


# --------------------------------------------------------------------------- #
# Console TUI (subcomando 'console')
# --------------------------------------------------------------------------- #
def _toggle(cfg: dict, key: str) -> None:
    cfg[key] = not cfg[key]


def pick_devices_console(cfg: dict) -> dict:
    v, a = list_dshow_devices()
    if not v:
        print("[!] Sin dispositivos de video.")
        sys.exit(1)
    print("\nVideo:")
    for i, n in enumerate(v): print(f"  [{i}] {n}")
    sel = input("Elige [0]: ").strip() or "0"
    cfg["video_device"] = v[int(sel)]
    print("\nAudio:")
    print("  [-] (sin audio)")
    for i, n in enumerate(a): print(f"  [{i}] {n}")
    sel = input("Elige [0 / -]: ").strip() or "0"
    cfg["audio_device"] = None if sel == "-" or not a else a[int(sel)]
    save_config(cfg)
    return cfg


def settings_console(cfg: dict) -> dict:
    while True:
        print(f"\n  [1] resolucion={cfg['resolution']}")
        print(f"  [2] fps={cfg['framerate']}")
        print(f"  [3] modo={cfg['window_mode']}")
        print(f"  [4] caps={cfg['screenshot_dir']}")
        print(f"  [5] vids={cfg['video_dir']}")
        print(f"  [6] {cfg['video_codec']} preset={cfg['video_preset']} crf={cfg['video_crf']}")
        print(f"  [7] {cfg['audio_codec']}@{cfg['audio_bitrate']}  [8] container={cfg['container']}")
        print(f"  [9] re-elegir dispositivos    [v] volver")
        ch = input("> ").strip().lower()
        if ch == "v": break
        elif ch == "1": cfg["resolution"] = input(f"[{cfg['resolution']}]: ").strip() or cfg["resolution"]
        elif ch == "2":
            x = input(f"[{cfg['framerate']}]: ").strip()
            if x: cfg["framerate"] = int(x)
        elif ch == "3":
            x = input("(windowed/fullscreen/borderless): ").strip().lower()
            if x in ("windowed", "fullscreen", "borderless"): cfg["window_mode"] = x
        elif ch == "4":
            x = input(f"[{cfg['screenshot_dir']}]: ").strip()
            if x: cfg["screenshot_dir"] = x
        elif ch == "5":
            x = input(f"[{cfg['video_dir']}]: ").strip()
            if x: cfg["video_dir"] = x
        elif ch == "6":
            cfg["video_codec"] = input(f"codec [{cfg['video_codec']}]: ").strip() or cfg["video_codec"]
            cfg["video_preset"] = input(f"preset [{cfg['video_preset']}]: ").strip() or cfg["video_preset"]
            x = input(f"crf [{cfg['video_crf']}]: ").strip()
            if x: cfg["video_crf"] = int(x)
        elif ch == "7":
            cfg["audio_codec"] = input(f"codec [{cfg['audio_codec']}]: ").strip() or cfg["audio_codec"]
            cfg["audio_bitrate"] = input(f"bitrate [{cfg['audio_bitrate']}]: ").strip() or cfg["audio_bitrate"]
        elif ch == "8":
            x = input(f"(mkv/mp4) [{cfg['container']}]: ").strip().lower()
            if x in ("mkv", "mp4"): cfg["container"] = x
        elif ch == "9":
            cfg = pick_devices_console(cfg)
        save_config(cfg)
    return cfg


def install_console(interactive: bool = True) -> int:
    py_ok = check_clipboard_deps() or IS_FROZEN
    ff_ok = check_tools(quiet=True)
    print("\n--- Instalador ---")
    print(f"  pillow + pywin32 .. {'OK' if py_ok else 'FALTA'}")
    print(f"  ffmpeg + ffplay ... {'OK' if ff_ok else 'FALTA'}")
    if not interactive:
        ok = True
        if not py_ok: ok = install_python_deps() and ok
        if not ff_ok: ok = install_ffmpeg() and ok
        return 0 if ok else 1
    print("\n  [1] Todo  [2] Solo Python  [3] Solo ffmpeg  [v] volver")
    ch = input("> ").strip().lower()
    if ch == "1": install_python_deps(); install_ffmpeg()
    elif ch == "2": install_python_deps()
    elif ch == "3": install_ffmpeg()
    return 0


def console_menu(cfg: dict) -> None:
    while True:
        print(f"\n=== {APP_NAME} ===")
        print(f"  Video: {cfg['video_device']}")
        print(f"  Audio: {cfg.get('audio_device') or '(ninguno)'}")
        print(f"  {cfg['resolution']} @ {cfg['framerate']}fps  ({cfg['window_mode']})")
        print()
        print("  [1] Preview   [2] Captura   [3] Grabar")
        print("  [s] Config    [i] Install   [q] Salir")
        ch = input("> ").strip().lower()
        if ch == "1":
            print("Preview activo. Cierra la ventana para volver.")
            p = start_preview(cfg); p.wait()
        elif ch == "2":
            path, msg = take_screenshot(cfg)
            print(msg)
        elif ch == "3":
            print("Grabando. ENTER para detener.")
            s = start_record(cfg)
            try: input()
            except (EOFError, KeyboardInterrupt): pass
            _, msg = stop_record(s)
            print(f"Detenido: {msg}")
        elif ch == "s": cfg = settings_console(cfg)
        elif ch == "i": install_console(True)
        elif ch == "q": return


# --------------------------------------------------------------------------- #
# GUI (tkinter)
# --------------------------------------------------------------------------- #
def run_gui(cfg: dict) -> None:
    """Ejecuta la GUI. El cambio de tema y otros ajustes son en vivo."""
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    # ----- Paletas modernas (Tailwind / slate + accent) -----
    LIGHT_PALETTE = {
        "BG":          "#f8fafc", "BG_DEEP":     "#f1f5f9",
        "CARD":        "#ffffff", "BORDER":      "#e2e8f0",
        "BORDER_HARD": "#cbd5e1", "TEXT":        "#0f172a",
        "SUB":         "#475569", "MUTED":       "#94a3b8",
        "ACCENT":      "#2563eb", "ACCENT_HOV":  "#1d4ed8",
        "ACCENT_BG":   "#eff6ff",
        "OK_BG":       "#ecfdf5", "OK_FG":       "#047857",
        "WARN_BG":     "#fffbeb", "WARN_FG":     "#b45309",
        "ERR_BG":      "#fef2f2", "ERR_FG":      "#b91c1c",
        "SEL_BG":      "#2563eb", "SEL_FG":      "#ffffff",
        "HOVER_BG":    "#f1f5f9",
        "VIDEO_BG":    "#000000",
        "HEADER_BG":   "#eef2f7", "HEADER_BORDER": "#cbd5e1",
    }
    DARK_PALETTE = {
        "BG":          "#0f172a", "BG_DEEP":     "#020617",
        "CARD":        "#1e293b", "BORDER":      "#334155",
        "BORDER_HARD": "#475569", "TEXT":        "#f1f5f9",
        "SUB":         "#94a3b8", "MUTED":       "#64748b",
        "ACCENT":      "#3b82f6", "ACCENT_HOV":  "#60a5fa",
        "ACCENT_BG":   "#1e3a8a",
        "OK_BG":       "#064e3b", "OK_FG":       "#6ee7b7",
        "WARN_BG":     "#78350f", "WARN_FG":     "#fcd34d",
        "ERR_BG":      "#7f1d1d", "ERR_FG":      "#fca5a5",
        "SEL_BG":      "#3b82f6", "SEL_FG":      "#ffffff",
        "HOVER_BG":    "#334155",
        "VIDEO_BG":    "#000000",
        "HEADER_BG":   "#1e293b", "HEADER_BORDER": "#334155",
    }
    THEME_NAME = (cfg.get("theme") or "light").lower()
    if THEME_NAME not in ("light", "dark"): THEME_NAME = "light"
    P = DARK_PALETTE if THEME_NAME == "dark" else LIGHT_PALETTE
    BG          = P["BG"]
    BG_DEEP     = P["BG_DEEP"]
    CARD        = P["CARD"]
    BORDER      = P["BORDER"]
    BORDER_HARD = P["BORDER_HARD"]
    TEXT        = P["TEXT"]
    SUB         = P["SUB"]
    MUTED       = P["MUTED"]
    ACCENT      = P["ACCENT"]
    ACCENT_HOV  = P["ACCENT_HOV"]
    ACCENT_BG   = P["ACCENT_BG"]
    OK_BG       = P["OK_BG"]
    OK_FG       = P["OK_FG"]
    WARN_BG     = P["WARN_BG"]
    WARN_FG     = P["WARN_FG"]
    ERR_BG      = P["ERR_BG"]
    ERR_FG      = P["ERR_FG"]
    SEL_BG      = P["SEL_BG"]
    SEL_FG      = P["SEL_FG"]
    HOVER_BG    = P["HOVER_BG"]
    HEADER_BG     = P["HEADER_BG"]
    HEADER_BORDER = P["HEADER_BORDER"]

    # Tipografia (Segoe UI Variable Display cae a Segoe UI en Win10)
    FONT_TITLE   = ("Segoe UI Variable Display", 18, "bold")
    FONT_SECTION = ("Segoe UI Variable", 10, "bold")
    FONT_BODY    = ("Segoe UI Variable", 10)
    FONT_SUB     = ("Segoe UI Variable", 9)
    FONT_TINY    = ("Segoe UI Variable", 8)
    FONT_MONO    = ("Cascadia Mono", 9)
    FONT_EMOJI   = ("Segoe UI Emoji", 16)

    def _sev_colors() -> dict[str, tuple[str, str]]:
        return {
            "error": (ERR_BG, ERR_FG),
            "warn":  (WARN_BG, WARN_FG),
            "ok":    (OK_BG, OK_FG),
            "info":  (CARD, SUB),
        }
    SEV_GLYPH = {"error": "●", "warn": "●", "ok": "●", "info": "●"}

    class ToolTip:
        """Tooltip on hover para cualquier widget.

        `text` puede ser un string fijo o un callable () -> str. Si es
        callable, se invoca cada vez que se muestra el tooltip — eso
        permite que el contenido reaccione al idioma actual sin tener
        que actualizar la referencia."""
        def __init__(self, widget, text, delay: int = 350,
                      *, wrap: int = 320):
            self.widget = widget
            self.text = text
            self.delay = delay
            self.wrap = wrap
            self.tipwin: tk.Toplevel | None = None
            self.after_id = None
            widget.bind("<Enter>", self._on_enter)
            widget.bind("<Leave>", self._on_leave)
            widget.bind("<ButtonPress>", self._on_leave)

        def set_text(self, text) -> None:
            self.text = text

        def _resolve(self) -> str:
            t = self.text
            if callable(t):
                try: return t() or ""
                except Exception: return ""
            return t or ""

        def _on_enter(self, _e):
            self._unschedule()
            self.after_id = self.widget.after(self.delay, self._show)

        def _on_leave(self, _e):
            self._unschedule()
            self._hide()

        def _unschedule(self):
            if self.after_id:
                try: self.widget.after_cancel(self.after_id)
                except Exception: pass
                self.after_id = None

        def _show(self):
            if self.tipwin: return
            text = self._resolve()
            if not text: return
            try:
                x = self.widget.winfo_rootx() + 18
                y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
            except Exception:
                return
            tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            try: tw.attributes("-topmost", True)
            except Exception: pass
            tk.Label(
                tw, text=text, justify="left",
                bg="#202020", fg="#f5f5f5",
                relief="solid", borderwidth=1,
                font=("Segoe UI", 9), padx=8, pady=5,
                wraplength=self.wrap,
            ).pack()
            self.tipwin = tw

        def _hide(self):
            if self.tipwin:
                try: self.tipwin.destroy()
                except Exception: pass
                self.tipwin = None

    class CollapsiblePanel:
        """Seccion de menu colapsable + reordenable. Look moderno (sin barras grises).

        Header limpio con border-bottom + accent text + arrows on hover.
        Si reorderable=False, no muestra los botones de mover orden.
        """
        def __init__(self, parent, title: str, app, *, reorderable: bool = True,
                       on_toggle=None):
            self.app = app
            self.title = title
            self.expanded = True
            self.section_key: str | None = None
            self.on_toggle = on_toggle

            hbg = P["HEADER_BG"]; hbd = P["HEADER_BORDER"]
            self.outer = tk.Frame(parent, bg=P["BG"], highlightthickness=0)

            # Header tipo "card top" con borde inferior sutil
            self.hdr_outer = tk.Frame(self.outer, bg=hbg,
                                       highlightthickness=0)
            self.hdr_outer.pack(fill="x")
            self.hdr = tk.Frame(self.hdr_outer, bg=hbg, padx=4, pady=2)
            self.hdr.pack(fill="x")
            self.sep = tk.Frame(self.hdr_outer, bg=hbd, height=1)
            self.sep.pack(fill="x")

            def _click_toggle(_e):
                self.toggle()
                return "break"   # impide que el bind_all drag se dispare

            self.toggle_lbl = tk.Label(
                self.hdr, text="▼", bg=hbg, fg=P["SUB"],
                font=FONT_BODY, cursor="hand2",
                padx=6, pady=4)
            self.toggle_lbl.pack(side="left")
            self.toggle_lbl.bind("<Button-1>", _click_toggle)

            self.title_lbl = tk.Label(
                self.hdr, text=title.upper(), bg=hbg, fg=P["ACCENT"],
                font=FONT_SECTION, cursor="hand2", anchor="w")
            self.title_lbl.pack(side="left", fill="x", expand=True, padx=4)
            self.title_lbl.bind("<Button-1>", _click_toggle)

            self.arrow_labels: list[tk.Label] = []
            if reorderable:
                for arrow, dir_ in (("↓", 1), ("↑", -1)):
                    lab = tk.Label(
                        self.hdr, text=arrow, bg=hbg, fg=P["MUTED"],
                        font=FONT_BODY, cursor="hand2",
                        padx=8, pady=4)
                    lab.pack(side="right")
                    def _click_move(_e, d=dir_):
                        self.app._move_panel(self, d)
                        return "break"
                    lab.bind("<Button-1>", _click_move)
                    lab.bind("<Enter>",
                              lambda e, l=lab: l.configure(fg=P["ACCENT"]))
                    lab.bind("<Leave>",
                              lambda e, l=lab: l.configure(fg=P["MUTED"]))
                    self.arrow_labels.append(lab)

            # Body
            self.body = ttk.Frame(self.outer, padding=(12, 10, 12, 12))
            self.body.pack(fill="x")

        def apply_palette(self) -> None:
            """Re-aplica los colores actuales de la paleta a los widgets tk.
            Lee de P (rebinded por _apply_theme) en vez de los nombres
            individuales para evitar cualquier ambiguedad de closure."""
            hbg = P["HEADER_BG"]; hbd = P["HEADER_BORDER"]
            self.outer.configure(bg=P["BG"])
            self.hdr_outer.configure(bg=hbg)
            self.hdr.configure(bg=hbg)
            self.sep.configure(bg=hbd)
            self.toggle_lbl.configure(bg=hbg, fg=P["SUB"])
            self.title_lbl.configure(bg=hbg, fg=P["ACCENT"])
            for lab in self.arrow_labels:
                lab.configure(bg=hbg, fg=P["MUTED"])

        def set_title(self, title: str) -> None:
            try: self.title_lbl.configure(text=title.upper())
            except Exception: pass

        def toggle(self) -> None:
            if self.expanded:
                self.body.pack_forget()
                self.toggle_lbl.configure(text="▶")
            else:
                self.body.pack(fill="x")
                self.toggle_lbl.configure(text="▼")
            self.expanded = not self.expanded
            if self.on_toggle:
                try: self.on_toggle(self.expanded)
                except Exception: pass

        def set_collapsed(self, collapsed: bool) -> None:
            """Aplica un estado colapsado sin disparar on_toggle (uso en
            restauracion al inicio)."""
            if collapsed and self.expanded:
                self.body.pack_forget()
                self.toggle_lbl.configure(text="▶")
                self.expanded = False
            elif not collapsed and not self.expanded:
                self.body.pack(fill="x")
                self.toggle_lbl.configure(text="▼")
                self.expanded = True

        def pack(self, **kw):
            self.outer.pack(**kw)

        def pack_forget(self):
            self.outer.pack_forget()


    class App(tk.Tk):
        def __init__(self, cfg: dict):
            super().__init__()
            # Esconder la ventana INMEDIATAMENTE para que Windows no muestre
            # primero la chrome nativa del SO y luego la quite (eso es el
            # flash que ve el user). La revelamos despues del build.
            self.withdraw()

            self.cfg = cfg
            self.master_session: dict | None = None
            self._restarting = False
            self._formats: dict[str, float] = {}
            self._gpu = "unknown"
            self._panels: list[CollapsiblePanel] = []

            self.title(APP_NAME)
            self.minsize(220, 130)   # permite ventanas muy chicas en focus mode
            # Restaurar geometria de la sesion anterior si la guardamos.
            # Validamos que cabe en algun monitor (no fuera de pantalla).
            self.geometry(self._restore_geometry() or "1200x720")
            self.configure(bg=BG)

            # Icono de la ventana + agrupacion en la barra de tareas.
            self._set_app_icon()

            # Quitar chrome ANTES de mostrar la ventana
            try: self.overrideredirect(True)
            except Exception: pass

            self._init_styles()
            self._build()
            self.protocol("WM_DELETE_WINDOW", self._on_close)
            self.bind("<F12>", lambda e: self._hide())
            self.bind("<F11>", lambda e: self._toggle_fullscreen())
            def _on_escape(_e):
                if self._popup_mode:
                    self._exit_popup_mode()
                elif self._fullscreen:
                    self._toggle_fullscreen()
            self.bind("<Escape>", _on_escape)
            # PrintScreen → screenshot. No-op si la preview no esta activa
            # (_screenshot ya valida is_running).
            self.bind("<Print>", lambda e: self._screenshot())

            # Mostrar ahora que esta todo construido + setear taskbar icon
            self.after_idle(self._show_initial)
            self.after(80, self._bootstrap)
            self.after(500, self._poll)

        def _show_initial(self) -> None:
            """Revela la ventana ya construida (sin flash de chrome nativa)."""
            self.deiconify()
            try: self._set_appwindow()
            except Exception: pass
            # Re-aplicar taskbar bit por si Windows lo perdio durante withdraw
            for delay in (100, 400):
                self.after(delay, self._set_appwindow)

        # ---------- Icono ----------
        def _set_app_icon(self) -> None:
            """Aplica el icono de la app al Tk root + AppUserModelID en
            Windows para que la barra de tareas agrupe el proceso bajo el
            icono correcto (sino, Windows usa el icono de python/pyinstaller).

            Busca, en orden:
              assets/icon.ico  (preferido en Windows)
              assets/icon.png  (fallback multiplataforma)
            """
            # AppUserModelID: agrupacion del taskbar + icono propio
            if _IS_WIN:
                try:
                    shell32 = ctypes.windll.shell32
                    shell32.SetCurrentProcessExplicitAppUserModelID(
                        ctypes.c_wchar_p(APP_AUMID))
                except Exception: pass
            if ICON_ICO is not None and _IS_WIN:
                try: self.iconbitmap(default=str(ICON_ICO))
                except Exception: pass
            if ICON_PNG is not None:
                try:
                    self._app_icon_img = tk.PhotoImage(file=str(ICON_PNG))
                    self.iconphoto(True, self._app_icon_img)
                except Exception: pass

        # ---------- Persistencia de la ventana ----------
        _GEOM_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")

        def _restore_geometry(self) -> str | None:
            """Devuelve la geometria guardada si esta dentro del area de
            pantalla, sino None (cae al default)."""
            saved = self.cfg.get("window_geometry") or ""
            m = self._GEOM_RE.match(saved.strip())
            if not m: return None
            w, h, x, y = (int(m.group(1)), int(m.group(2)),
                            int(m.group(3)), int(m.group(4)))
            if w < 220 or h < 130: return None
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            # Verificar que al menos una esquina visible cae en pantalla
            if x + w < 50 or y + h < 50: return None
            if x > sw - 50 or y > sh - 50: return None
            return f"{w}x{h}{m.group(3)}{m.group(4)}"

        def _save_geometry(self) -> None:
            """Persiste la geometria actual del Tk root. No guarda durante
            fullscreen / maximize: usamos _saved_geometry como referencia."""
            try:
                if self._fullscreen or self._maximized:
                    geom = self._saved_geometry or self.geometry()
                else:
                    geom = self.geometry()
            except Exception:
                return
            if geom and geom != self.cfg.get("window_geometry"):
                self.cfg["window_geometry"] = geom
                try: save_config(self.cfg)
                except Exception: pass

        # ---------- styles ----------
        def _init_styles(self) -> None:
            s = ttk.Style(self)
            # 'clam' admite mejor customizacion de colores que vista/winnative
            for theme in ("clam", "vista", "winnative"):
                try: s.theme_use(theme); break
                except tk.TclError: pass

            # Defaults
            s.configure(".", background=BG, foreground=TEXT, font=FONT_BODY,
                        bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                        focuscolor=ACCENT)
            s.configure("TFrame", background=BG)
            s.configure("TLabel", background=BG, foreground=TEXT, font=FONT_BODY)
            s.configure("Title.TLabel", background=BG, foreground=TEXT,
                        font=FONT_TITLE)
            s.configure("Section.TLabel", background=BG, foreground=ACCENT,
                        font=FONT_SECTION)
            s.configure("Sub.TLabel", background=BG, foreground=SUB,
                        font=FONT_SUB)
            s.configure("Mono.TLabel", background=BG, foreground=SUB,
                        font=FONT_MONO)
            s.configure("Rec.TLabel", background=BG, foreground=ERR_FG,
                        font=("Segoe UI", 10, "bold"))

            # LabelFrame (lo usa el panel "Acciones")
            s.configure("TLabelframe", background=BG, borderwidth=0,
                        relief="flat")
            s.configure("TLabelframe.Label", background=BG, foreground=SUB,
                        font=FONT_SECTION)

            # Botones: estilo moderno flat con hover sutil
            s.configure("TButton", padding=(12, 7), font=FONT_BODY,
                        background=CARD, foreground=TEXT,
                        bordercolor=BORDER, focusthickness=2,
                        relief="flat", borderwidth=1)
            s.map("TButton",
                   background=[("active", HOVER_BG), ("pressed", BORDER)],
                   bordercolor=[("active", BORDER_HARD)])

            s.configure("Primary.TButton", padding=(14, 8), font=FONT_SECTION,
                        background=ACCENT, foreground="#ffffff",
                        bordercolor=ACCENT, relief="flat", borderwidth=0)
            s.map("Primary.TButton",
                   background=[("active", ACCENT_HOV), ("pressed", ACCENT_HOV)],
                   foreground=[("active", "#ffffff")])

            # Action.TButton: mismas dimensiones que Icon.TButton para que
            # el top-bar luzca uniforme; cambia solo el accent en el border.
            s.configure("Action.TButton", padding=(8, 6),
                        font=("Segoe UI Emoji", 12),
                        background=ACCENT_BG, foreground=ACCENT,
                        bordercolor=ACCENT, relief="flat", borderwidth=1)
            s.map("Action.TButton",
                   background=[("active", HOVER_BG), ("pressed", BORDER)],
                   bordercolor=[("active", ACCENT_HOV)])

            s.configure("ActionRec.TButton", padding=(8, 6),
                        font=("Segoe UI Emoji", 12),
                        background=ERR_BG, foreground=ERR_FG,
                        bordercolor=ERR_FG, relief="flat", borderwidth=1)
            s.map("ActionRec.TButton",
                   background=[("active", ERR_BG), ("pressed", ERR_BG)])

            # Close button: rojo armonico con el tema
            s.configure("Close.TButton", padding=(8, 6),
                        font=("Segoe UI Emoji", 12),
                        background=CARD, foreground=ERR_FG,
                        bordercolor=BORDER, relief="flat", borderwidth=1)
            s.map("Close.TButton",
                   background=[("active", ERR_BG), ("pressed", ERR_BG)],
                   foreground=[("active", ERR_FG)],
                   bordercolor=[("active", ERR_FG)])

            # Botones de iconos uniformes (toolbar buttons)
            s.configure("Icon.TButton", padding=(8, 6),
                        font=("Segoe UI Emoji", 12),
                        background=CARD, foreground=TEXT,
                        bordercolor=BORDER, relief="flat", borderwidth=1)
            s.map("Icon.TButton",
                   background=[("active", HOVER_BG), ("pressed", BORDER)],
                   bordercolor=[("active", ACCENT)])

            s.configure("Ghost.TButton", padding=(10, 6), font=FONT_BODY,
                        background=BG, foreground=SUB,
                        bordercolor=BG, relief="flat", borderwidth=0)
            s.map("Ghost.TButton",
                   background=[("active", HOVER_BG), ("pressed", BORDER)],
                   foreground=[("active", TEXT)])

            # Combobox y Entry
            s.configure("TCombobox", padding=(8, 5), font=FONT_BODY,
                        fieldbackground=CARD, background=CARD,
                        foreground=TEXT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER,
                        arrowcolor=SUB, selectbackground=ACCENT_BG,
                        selectforeground=TEXT)
            s.map("TCombobox",
                   bordercolor=[("focus", ACCENT), ("active", BORDER_HARD)],
                   fieldbackground=[("readonly", CARD)])
            s.configure("TEntry", padding=(8, 5), font=FONT_BODY,
                        fieldbackground=CARD, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, insertcolor=TEXT)
            s.map("TEntry",
                   bordercolor=[("focus", ACCENT), ("active", BORDER_HARD)])

            # Check
            s.configure("TCheckbutton", background=BG, foreground=TEXT,
                        font=FONT_BODY, focuscolor=ACCENT,
                        indicatorbackground=CARD,
                        indicatorforeground=ACCENT)
            s.map("TCheckbutton",
                   indicatorbackground=[("active", HOVER_BG)],
                   foreground=[("active", TEXT)])

            # Scale (slider de volumen)
            s.configure("Horizontal.TScale", background=BG,
                        troughcolor=BORDER, bordercolor=BORDER,
                        sliderthickness=16,
                        sliderrelief="flat",
                        slidercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT)

            # Scrollbar
            s.configure("Vertical.TScrollbar", background=BG_DEEP,
                        troughcolor=BG, bordercolor=BG,
                        arrowcolor=SUB, relief="flat",
                        gripcount=0, borderwidth=0)
            s.map("Vertical.TScrollbar",
                   background=[("active", BORDER_HARD)])

            # Separator
            s.configure("TSeparator", background=BORDER)

        # ---------- visibility / drag (ventana borderless) ----------
        def _toplevel_hwnd(self):
            """Devuelve el HWND real del top-level OS (Tk puede envolver en
            una toolwindow wrapper)."""
            if not _IS_WIN: return None
            try:
                my = self.winfo_id()
                parent = _user32.GetParent(my)
                return parent if parent else my
            except Exception: return None

        def _set_appwindow(self) -> None:
            """Hace que la ventana overrideredirect aparezca en la barra de tareas
            con su entrada propia. Lo llamamos varias veces porque a veces Tk
            re-aplica WS_EX_TOOLWINDOW despues."""
            if not _IS_WIN: return
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            try:
                hwnd = self._toplevel_hwnd()
                if not hwnd: return
                style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) or 0
                new_style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
                if new_style != style:
                    _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new_style)
                    _user32.SetWindowPos(
                        hwnd, 0, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
                    # Forzar a Windows a refrescar la entrada de taskbar
                    self.wm_withdraw()
                    self.update_idletasks()
                    self.after(20, self.wm_deiconify)
            except Exception: pass

        def _hide(self) -> None:
            if _IS_WIN:
                try:
                    hwnd = self._toplevel_hwnd()
                    if hwnd:
                        _user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                        return
                except Exception: pass
            self.iconify()

        def _close_app(self) -> None:
            # Fast close: persistimos geometria, ocultamos la ventana y
            # matamos procesos sin esperar shutdown gracioso. Total < 50ms.
            try: self._save_geometry()
            except Exception: pass
            try: self.withdraw()
            except Exception: pass
            s = self.master_session
            self.master_session = None
            if s:
                try: s["tee"].stop()
                except Exception: pass
                for k in ("recorder", "ffplay", "ffmpeg"):
                    p = s.get(k)
                    if p is not None:
                        try: p.kill()
                        except Exception: pass
            self.destroy()

        def _get_work_area(self) -> tuple[int, int, int, int]:
            """Devuelve (x, y, w, h) del area de trabajo (sin barra de tareas)."""
            try:
                if _IS_WIN:
                    SPI_GETWORKAREA = 0x0030
                    rect = wintypes.RECT()
                    _user32.SystemParametersInfoW(
                        SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
                    return (rect.left, rect.top,
                            rect.right - rect.left,
                            rect.bottom - rect.top)
            except Exception: pass
            return (0, 0, self.winfo_screenwidth(),
                    self.winfo_screenheight() - 40)

        def _schedule_resync(self) -> None:
            """Programa varios _sync_embed_size para asegurar que el embed
            siga al video_holder durante reflows asincronos."""
            for delay in (30, 80, 200, 400, 800):
                self.after(delay, self._sync_embed_size)

        def _toggle_maximize(self) -> None:
            if self._fullscreen:
                self._toggle_fullscreen()
            if self._maximized:
                if self._saved_geometry:
                    self.geometry(self._saved_geometry)
                self._maximized = False
                self.btn_max.configure(text="🗖")
            else:
                self._saved_geometry = self.geometry()
                x, y, w, h = self._get_work_area()
                self.geometry(f"{w}x{h}+{x}+{y}")
                self._maximized = True
                self.btn_max.configure(text="🗗")
            self._schedule_resync()

        def _toggle_fullscreen(self) -> None:
            if self._fullscreen:
                if self._saved_geometry:
                    self.geometry(self._saved_geometry)
                self._fullscreen = False
                self.btn_full.configure(text="⛶")
            else:
                if not self._maximized:
                    self._saved_geometry = self.geometry()
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                self.geometry(f"{sw}x{sh}+0+0")
                self._fullscreen = True
                self.btn_full.configure(text="⛶")
            self._schedule_resync()

        # Clases de widgets desde las que NO arrastramos la ventana.
        _DRAG_BLOCK_CLASSES = {
            "TButton", "Button", "TCombobox", "TEntry", "Entry",
            "TCheckbutton", "Checkbutton", "TScale", "Scale",
            "Canvas", "TScrollbar", "Scrollbar",
            "Text", "Listbox", "TSpinbox", "Spinbox",
        }

        # ---------- volumen via scroll wheel + overlay ----------
        def _set_ffplay_volume_live(self, volume_pct: int) -> bool:
            """Cambia el volumen de la sesion de audio de ffplay en vivo
            via pycaw (Windows audio session API)."""
            if not _IS_WIN: return False
            session = self.master_session
            ffplay = session.get("ffplay") if session else None
            if not ffplay or ffplay.poll() is not None:
                self._ffplay_volume_ctl = None
                return False
            level = max(0.0, min(1.0, volume_pct / 100.0))
            # Reusar control cacheado
            if self._ffplay_volume_ctl is not None:
                try:
                    self._ffplay_volume_ctl.SetMasterVolume(level, None)
                    return True
                except Exception as e:
                    self._set_status(f"vol cache fail: {e}")
                    self._ffplay_volume_ctl = None
            # Init COM por si pythonw no lo hizo
            try:
                import comtypes
                try: comtypes.CoInitialize()
                except OSError: pass  # ya inicializado
            except ImportError:
                pass
            try:
                from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
            except ImportError as e:
                self._set_status(f"vol: pycaw no disponible: {e}")
                return False
            try:
                target_pid = ffplay.pid
                all_sessions = AudioUtilities.GetAllSessions()
                # Buscar por PID exacto
                for s in all_sessions:
                    try:
                        if s.Process and s.Process.pid == target_pid:
                            ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                            ctl.SetMasterVolume(level, None)
                            self._ffplay_volume_ctl = ctl
                            return True
                    except Exception: continue
                # Fallback: por nombre del proceso
                for s in all_sessions:
                    try:
                        name = (s.Process.name() if s.Process else "") or ""
                        if "ffplay" in name.lower():
                            ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                            ctl.SetMasterVolume(level, None)
                            self._ffplay_volume_ctl = ctl
                            return True
                    except Exception: continue
                self._set_status(
                    f"vol: ffplay session no encontrada (pid {target_pid}, "
                    f"{len(all_sessions)} sessions)")
            except Exception as e:
                self._set_status(f"vol error: {type(e).__name__}: {e}")
            return False

        def _on_video_wheel(self, event) -> None:
            """Scroll wheel sobre el video → ajusta volumen +/- 5% por paso."""
            steps = int(event.delta / 120) or (1 if event.delta > 0 else -1)
            cur = int(self.cfg.get("volume", 80))
            new_vol = max(0, min(100, cur + steps * 5))
            if new_vol != cur:
                self.cfg["volume"] = new_vol
                self._save_cfg()
                if "volume" in self._vars:
                    try: self._vars["volume"].set(new_vol)
                    except Exception: pass
                # Aplicar en vivo a ffplay (controla la sesion de audio Windows)
                self._set_ffplay_volume_live(new_vol)
                # Si scrolleas el volumen mientras esta muteado, lo desmuteamos
                if self.cfg.get("muted"):
                    self.cfg["muted"] = False
                    self._set_ffplay_mute_live(False)
                    self._update_mute_button()
            self._show_volume_overlay(new_vol)

        def _set_ffplay_mute_live(self, mute: bool) -> bool:
            """Aplica mute al ffplay en vivo via pycaw."""
            if not _IS_WIN: return False
            session = self.master_session
            ffplay = session.get("ffplay") if session else None
            if not ffplay or ffplay.poll() is not None:
                self._ffplay_volume_ctl = None
                return False
            # Asegurar que tenemos el control cacheado
            if self._ffplay_volume_ctl is None:
                self._set_ffplay_volume_live(int(self.cfg.get("volume", 80)))
            if self._ffplay_volume_ctl is None:
                return False
            try:
                self._ffplay_volume_ctl.SetMute(1 if mute else 0, None)
                return True
            except Exception:
                self._ffplay_volume_ctl = None
                return False

        def _toggle_mute(self) -> None:
            new = not bool(self.cfg.get("muted", False))
            self.cfg["muted"] = new
            self._save_cfg()
            self._set_ffplay_mute_live(new)
            self._update_mute_button()
            # Visual feedback en el overlay
            cur_vol = int(self.cfg.get("volume", 80))
            self._show_volume_overlay(0 if new else cur_vol, muted=new)

        def _update_mute_button(self) -> None:
            if hasattr(self, "btn_mute"):
                muted = bool(self.cfg.get("muted", False))
                self.btn_mute.configure(text="🔇" if muted else "🔊")

        # ---------- Popup mode (focus: oculta chrome) ----------
        def _toggle_popup(self) -> None:
            if not self.is_running() or not self._embedded_hwnd:
                self._set_status("Inicia la vista previa primero")
                return
            if self._popup_mode:
                self._exit_popup_mode()
            else:
                self._enter_popup_mode()

        SIDEBAR_FULL_W = 420
        ANIM_DURATION_MS = 220
        ANIM_FRAME_MS = 8     # ~120fps target — Tk best-effort

        def _animate_sidebar(self, target_w: int,
                                on_done=None) -> None:
            """Interpola sidebar_container.width hasta target_w con ease-out
            cubico. Para que sea SUAVE en presencia del HWND embebido de
            ffplay:
              - Cancela el debounce de _sync_embed_size (que normalmente
                espera 20ms) y mueve el HWND con SWP_NOREDRAW cada frame.
              - Step se programa con `after_idle` despues del primer frame
                para que Tk procese el redimensionado inmediatamente.
              - Llamada final con fast=False para que SDL/ffplay rebobine
                al tamano destino con una sola repintada.
            """
            try:
                start_w = self.sidebar_container.winfo_width()
            except Exception:
                start_w = self.SIDEBAR_FULL_W
            if start_w == target_w:
                if on_done: on_done()
                return
            prev = getattr(self, "_anim_after", None)
            if prev is not None:
                try: self.after_cancel(prev)
                except Exception: pass
                self._anim_after = None
            # Cancelar el debounce pendiente del sync_embed: durante la
            # animacion lo manejamos nosotros directamente.
            pending_sync = getattr(self, "_sync_embed_after", None)
            if pending_sync is not None:
                try: self.after_cancel(pending_sync)
                except Exception: pass
                self._sync_embed_after = None

            t0 = time.time()
            duration = self.ANIM_DURATION_MS / 1000.0
            self._anim_in_progress = True

            def step():
                t = (time.time() - t0) / duration
                if t >= 1.0:
                    self.sidebar_container.configure(width=target_w)
                    self.update_idletasks()
                    self._anim_after = None
                    self._anim_in_progress = False
                    # Repinta final del HWND con WM_SIZE para que SDL
                    # restaure la imagen nitida al tamano correcto.
                    self._do_sync_embed(fast=False)
                    if on_done: on_done()
                    return
                # ease-out cubico (rapido al inicio, suave al final)
                eased = 1 - (1 - t) ** 3
                w = int(start_w + (target_w - start_w) * eased)
                self.sidebar_container.configure(width=max(0, w))
                # Forzar layout del Tk en este frame antes de mover el HWND.
                self.update_idletasks()
                # Mover el HWND embebido sin repaint -> sin tearing/jitter.
                self._do_sync_embed(fast=True)
                self._anim_after = self.after(self.ANIM_FRAME_MS, step)

            self._anim_after = self.after(0, step)

        def _enter_popup_mode(self) -> None:
            if self._popup_mode: return
            self._popup_mode = True
            self._popup_saved_sidebar = self.sidebar_visible
            if hasattr(self, "btn_popup"):
                self.btn_popup.configure(text="⧈")
            self._set_status("Modo focus · doble-click en el video o Esc para volver")

            def _hide():
                # Una vez animado a 0, hacemos pack_forget para liberar espacio
                # y restauramos width=420 para la proxima entrada.
                try: self.sidebar_container.pack_forget()
                except Exception: pass
                self.sidebar_container.configure(width=self.SIDEBAR_FULL_W)
                self.sidebar_visible = False
                self._schedule_resync()
            self._animate_sidebar(0, on_done=_hide)

        def _exit_popup_mode(self) -> None:
            if not self._popup_mode: return
            self._popup_mode = False
            self.sidebar_visible = self._popup_saved_sidebar
            if hasattr(self, "btn_popup"):
                self.btn_popup.configure(text="⧉")
            self._set_status("Listo")
            if not self.sidebar_visible:
                # El user habia escondido la sidebar antes; nada que animar
                self._layout_main()
                self._schedule_resync()
                return
            # Re-pack la sidebar con width=0 y animarla hasta SIDEBAR_FULL_W.
            self.sidebar_container.configure(width=0)
            self._layout_main()
            self.update_idletasks()
            self._animate_sidebar(self.SIDEBAR_FULL_W,
                                    on_done=self._schedule_resync)

        def _on_video_double_click(self, event) -> str:
            self._toggle_popup()
            return "break"

        # Tamano fijo del overlay (los valores adentro cambian, el bloque no)
        VOL_OVERLAY_W = 420
        VOL_OVERLAY_H = 60

        # ---------- Toast genérico (captura, grabar, etc.) ----------
        def _show_toast(self, text: str, kind: str = "info",
                         duration_ms: int = 1600) -> None:
            """Toast flotante sobre el video (top-center). NO se graba: es un
            Toplevel del OS, compuesto encima de ffplay; el recorder lee el
            stream del master, antes del compositing."""
            if (not hasattr(self, "_toast_ov") or self._toast_ov is None
                    or not self._toast_ov.winfo_exists()):
                ov = tk.Toplevel(self)
                ov.overrideredirect(True)
                try: ov.attributes("-topmost", True)
                except Exception: pass
                try: ov.attributes("-alpha", 0.92)
                except Exception: pass
                ov.configure(bg="#000000")
                self._toast_ov = ov
                self._toast_lbl = tk.Label(
                    ov, font=("Segoe UI", 12, "bold"),
                    fg="#ffffff", bg="#000000",
                    padx=20, pady=10, anchor="center")
                self._toast_lbl.pack(fill="both", expand=True)

            ov = self._toast_ov
            colors = {
                "info":    "#ffffff",
                "success": "#86efac",   # emerald-300
                "warning": "#fcd34d",   # amber-300
                "error":   "#fca5a5",   # red-300
                "rec":     "#fca5a5",   # red para grabacion
            }
            self._toast_lbl.configure(
                text=text, fg=colors.get(kind, "#ffffff"))

            # Posicion: centrado en la parte superior del video
            ov.update_idletasks()
            ow = max(220, ov.winfo_reqwidth())
            oh = ov.winfo_reqheight()
            try:
                hx = self.video_holder.winfo_rootx()
                hy = self.video_holder.winfo_rooty()
                hw = self.video_holder.winfo_width()
                x = hx + (hw - ow) // 2
                y = hy + 24
            except Exception:
                x, y = 100, 100
            ov.geometry(f"+{x}+{y}")
            ov.deiconify()
            try: ov.lift()
            except Exception: pass

            if getattr(self, "_toast_after", None):
                try: self.after_cancel(self._toast_after)
                except Exception: pass
            self._toast_after = self.after(duration_ms, self._hide_toast)

        def _hide_toast(self) -> None:
            self._toast_after = None
            ov = getattr(self, "_toast_ov", None)
            if ov:
                try: ov.withdraw()
                except Exception: pass

        def _show_volume_overlay(self, volume: int, muted: bool = False) -> None:
            """Muestra una barra de volumen flotante sobre el video por 1.2s."""
            if not hasattr(self, "_vol_overlay") or self._vol_overlay is None \
                    or not self._vol_overlay.winfo_exists():
                ov = tk.Toplevel(self)
                ov.overrideredirect(True)
                try: ov.attributes("-topmost", True)
                except Exception: pass
                try: ov.attributes("-alpha", 0.92)
                except Exception: pass
                ov.configure(bg="#000000")
                self._vol_overlay = ov
                # Label fill: el toplevel tiene geometry fija; label se centra
                self._vol_overlay_lbl = tk.Label(
                    ov, font=("Consolas", 14, "bold"),
                    fg="#ffffff", bg="#000000",
                    anchor="center")
                self._vol_overlay_lbl.pack(fill="both", expand=True)

            ov = self._vol_overlay
            is_muted = muted or bool(self.cfg.get("muted", False))
            if is_muted:
                self._vol_overlay_lbl.configure(
                    text="🔇  MUTED            ", fg="#ff5050")
            else:
                filled = volume // 5
                bar = "█" * filled + "·" * (20 - filled)
                self._vol_overlay_lbl.configure(
                    text=f"🔊  {bar}  {volume:3d}%", fg="#ffffff")

            try:
                hx = self.video_holder.winfo_rootx()
                hy = self.video_holder.winfo_rooty()
                hw = self.video_holder.winfo_width()
                hh = self.video_holder.winfo_height()
                ow, oh = self.VOL_OVERLAY_W, self.VOL_OVERLAY_H
                x = hx + (hw - ow) // 2
                y = hy + hh - oh - 30
            except Exception:
                x, y = 100, 100
            ov.geometry(f"{self.VOL_OVERLAY_W}x{self.VOL_OVERLAY_H}+{x}+{y}")
            ov.deiconify()
            try: ov.lift()
            except Exception: pass

            if getattr(self, "_vol_overlay_after", None):
                try: self.after_cancel(self._vol_overlay_after)
                except Exception: pass
            self._vol_overlay_after = self.after(
                1200, self._hide_volume_overlay)

        def _hide_volume_overlay(self) -> None:
            self._vol_overlay_after = None
            ov = getattr(self, "_vol_overlay", None)
            if ov:
                try: ov.withdraw()
                except Exception: pass

        # ---------- Always on top ----------
        def _apply_always_on_top(self) -> None:
            on = bool(self.cfg.get("always_on_top", False))
            try: self.attributes("-topmost", on)
            except Exception: pass

        # ---------- Resize de la ventana por bordes/esquinas ----------
        def _window_edge_at(self, rx: int, ry: int):
            """Si (rx,ry) esta cerca de un borde de la ventana, devuelve
            (near_l, near_t, near_r, near_b). Si no, None."""
            if self._fullscreen or self._maximized: return None
            edge = 8
            try:
                wx = self.winfo_x(); wy = self.winfo_y()
                ww = self.winfo_width(); wh = self.winfo_height()
            except Exception: return None
            near_l = wx <= rx <= wx + edge
            near_t = wy <= ry <= wy + edge
            near_r = wx + ww - edge <= rx <= wx + ww
            near_b = wy + wh - edge <= ry <= wy + wh
            if not (near_l or near_t or near_r or near_b):
                return None
            return (near_l, near_t, near_r, near_b)

        def _cursor_for_edges(self, edges) -> str:
            l, t, r, b = edges
            if (l and t) or (r and b): return "size_nw_se"
            if (l and b) or (r and t): return "size_ne_sw"
            if l or r: return "size_we"
            return "size_ns"

        def _on_motion_anywhere(self, event) -> None:
            """Cambia el cursor al pasar cerca de un borde de la ventana."""
            if self._drag_active or self._resize_active: return
            edges = self._window_edge_at(event.x_root, event.y_root)
            if edges:
                cur = self._cursor_for_edges(edges)
                try: event.widget.configure(cursor=cur)
                except Exception: pass
                self._near_edge = edges
            elif self._near_edge is not None:
                try: event.widget.configure(cursor="")
                except Exception: pass
                self._near_edge = None

        def _start_drag(self, event) -> None:
            # 1) Si esta cerca de un borde -> resize
            edges = self._window_edge_at(event.x_root, event.y_root)
            if edges:
                self._resize_active = True
                self._resize_edges = edges
                self._resize_start_geom = (
                    self.winfo_x(), self.winfo_y(),
                    self.winfo_width(), self.winfo_height())
                self._resize_start_mouse = (event.x_root, event.y_root)
                self._drag_active = False
                return
            # 2) Si no, drag normal con clase-filter
            try:
                cls = event.widget.winfo_class()
            except Exception:
                cls = ""
            if cls in self._DRAG_BLOCK_CLASSES:
                self._drag_active = False
                return
            self._drag_active = True
            self._drag_committed = False
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            self._drag_dx = event.x_root - self.winfo_x()
            self._drag_dy = event.y_root - self.winfo_y()

        def _do_drag(self, event) -> None:
            if self._resize_active:
                ox, oy, ow, oh = self._resize_start_geom
                sx, sy = self._resize_start_mouse
                l, t, r, b = self._resize_edges
                dx = event.x_root - sx
                dy = event.y_root - sy
                nx, ny = ox, oy
                nw, nh = ow, oh
                if r: nw = max(400, ow + dx)
                if b: nh = max(220, oh + dy)
                if l:
                    nw = max(400, ow - dx); nx = ox + (ow - nw)
                if t:
                    nh = max(220, oh - dy); ny = oy + (oh - nh)
                self.geometry(f"{nw}x{nh}+{nx}+{ny}")
                return
            if not getattr(self, "_drag_active", False): return
            # Threshold anti-jitter
            if not getattr(self, "_drag_committed", False):
                dx = event.x_root - getattr(self, "_drag_start_x", 0)
                dy = event.y_root - getattr(self, "_drag_start_y", 0)
                if abs(dx) < 5 and abs(dy) < 5:
                    return
                self._drag_committed = True
            nx = event.x_root - getattr(self, "_drag_dx", 0)
            ny = event.y_root - getattr(self, "_drag_dy", 0)
            self.geometry(f"+{nx}+{ny}")

        def _end_drag(self, event) -> None:
            self._drag_active = False
            self._drag_committed = False
            self._resize_active = False

        # ---------- state queries ----------
        def is_running(self) -> bool:
            s = self.master_session
            return bool(s) and s["ffmpeg"].poll() is None  # type: ignore[index]

        def is_recording(self) -> bool:
            return self.is_running() and bool(self.master_session.get("recording"))  # type: ignore[union-attr]

        # ---------- UI build ----------
        def _build(self) -> None:
            self._vars: dict[str, tk.Variable] = {}
            self.sidebar_visible = True
            self._maximized = False
            self._fullscreen = False
            self._saved_geometry: str | None = None
            self._vol_overlay = None
            self._vol_overlay_after = None
            self._toast_ov = None
            self._toast_after = None
            self._ffplay_volume_ctl = None  # cached pycaw control para ffplay
            # i18n: lang actual + lista de tooltips a refrescar al cambiarlo
            self.lang = self.cfg.get("language", "es")
            self._tt_keyed: list[tuple] = []  # [(tooltip, key), ...]
            # Debouncing: coalesce eventos rapidos en una sola operacion
            self._diag_after = None
            self._sync_embed_after = None
            self._save_cfg_after = None
            # Modo popup (focus): oculta top bar + sidebar; video llena la ventana
            self._popup_mode = False
            self._popup_saved_sidebar = True
            # Resize de la ventana por bordes/esquinas
            self._resize_active = False
            self._resize_edges = (False, False, False, False)
            self._resize_start_geom = (0, 0, 0, 0)
            self._resize_start_mouse = (0, 0)
            self._near_edge = None
            # Variables de status (mostradas en el panel Sistema)
            self.var_status = tk.StringVar(value="Listo")
            self.var_timer = tk.StringVar(value="")

            # ===== Layout horizontal =====
            main = ttk.Frame(self)
            main.pack(fill="both", expand=True)
            self._main_frame = main
            self._titlebar = main  # compat alias

            # Sidebar container (panel completo, siempre 420px)
            self.sidebar_container = ttk.Frame(main, width=420)
            self.sidebar_container.pack_propagate(False)

            # Video area: referencia permanente en self._video_pane.
            # self._target es dinamico (cambia a sidebar_inner para construir
            # las secciones), pero _video_pane se queda apuntando aqui.
            self._video_pane = ttk.Frame(main, padding=(0, 0))
            self._target = self._video_pane
            self._build_video()

            # Aplicar el layout (pack en el orden correcto segun sidebar_side)
            self._layout_main()

            # Drag desde casi cualquier zona de la ventana. Filtro por clase
            # de widget evita que se dispare en botones/combos/etc.
            # Y resize al acercarse a los bordes (cualquier modo).
            self.bind_all("<Motion>", self._on_motion_anywhere, add="+")
            self.bind_all("<ButtonPress-1>", self._start_drag, add="+")
            self.bind_all("<B1-Motion>", self._do_drag, add="+")
            self.bind_all("<ButtonRelease-1>", self._end_drag, add="+")

            # Sync del embed cuando la ventana cambia de tamano (siempre activo,
            # no solo despues del embed). Tambien lo hace _poll cada 500ms.
            self.bind("<Configure>", self._on_window_configure, add="+")

            # Sidebar: scrolleable
            self._sidebar_canvas = tk.Canvas(
                self.sidebar_container, bg=BG,
                highlightthickness=0, width=400)
            self._sidebar_canvas.pack(side="left", fill="both", expand=True)
            scrollbar = ttk.Scrollbar(
                self.sidebar_container, orient="vertical",
                command=self._sidebar_canvas.yview)
            scrollbar.pack(side="right", fill="y")
            self._sidebar_canvas.configure(yscrollcommand=scrollbar.set)

            sidebar_inner = ttk.Frame(self._sidebar_canvas)
            self._sidebar_inner_id = self._sidebar_canvas.create_window(
                (0, 0), window=sidebar_inner, anchor="nw")

            def _on_inner(_e):
                self._sidebar_canvas.configure(
                    scrollregion=self._sidebar_canvas.bbox("all"))
            sidebar_inner.bind("<Configure>", _on_inner)

            def _on_canvas(event):
                self._sidebar_canvas.itemconfig(
                    self._sidebar_inner_id, width=event.width)
            self._sidebar_canvas.bind("<Configure>", _on_canvas)

            def _on_wheel(event):
                # Dispatch: si el cursor esta sobre video_holder -> volumen,
                # si no -> scroll de sidebar.
                try:
                    rx, ry = event.x_root, event.y_root
                    hx = self.video_holder.winfo_rootx()
                    hy = self.video_holder.winfo_rooty()
                    hw = self.video_holder.winfo_width()
                    hh = self.video_holder.winfo_height()
                    if hx <= rx <= hx + hw and hy <= ry <= hy + hh:
                        self._on_video_wheel(event)
                        return "break"
                except Exception: pass
                if self.sidebar_visible:
                    self._sidebar_canvas.yview_scroll(
                        int(-event.delta / 120), "units")
            self.bind_all("<MouseWheel>", _on_wheel)

            # Construir contenido de la sidebar
            self._target = sidebar_inner
            self._build_sidebar_header()  # logo + quick controls + acciones
            self._build_devices()
            self._build_format_matrix()
            self._build_preview_audio()
            self._build_capture()
            self._build_recording()
            self._build_folders()  # destinos de salida (capturas + videos)
            self._build_system()  # status + diagnostico + sistema integrados
            # Restaurar target para evitar bugs
            self._target = self

            # Restaurar layout persistido (orden + colapso de paneles)
            self._apply_persisted_layout()

            # Aplicar always-on-top al inicio segun cfg
            self._apply_always_on_top()
            # Y bindear el var del checkbox para que se aplique al cambiarlo
            if "always_on_top" in self._vars:
                try:
                    self._vars["always_on_top"].trace_add(
                        "write", lambda *_: self._apply_always_on_top())
                except Exception: pass

        def _toggle_theme(self) -> None:
            self._apply_theme("dark" if THEME_NAME == "light" else "light")

        def _apply_theme(self, name: str) -> None:
            """Cambia la paleta en vivo, sin cerrar la ventana."""
            nonlocal THEME_NAME, P
            nonlocal BG, BG_DEEP, CARD, BORDER, BORDER_HARD
            nonlocal TEXT, SUB, MUTED
            nonlocal ACCENT, ACCENT_HOV, ACCENT_BG
            nonlocal OK_BG, OK_FG, WARN_BG, WARN_FG, ERR_BG, ERR_FG
            nonlocal SEL_BG, SEL_FG, HOVER_BG
            nonlocal HEADER_BG, HEADER_BORDER

            THEME_NAME = name
            P = DARK_PALETTE if name == "dark" else LIGHT_PALETTE
            BG, BG_DEEP, CARD = P["BG"], P["BG_DEEP"], P["CARD"]
            BORDER, BORDER_HARD = P["BORDER"], P["BORDER_HARD"]
            TEXT, SUB, MUTED = P["TEXT"], P["SUB"], P["MUTED"]
            ACCENT, ACCENT_HOV = P["ACCENT"], P["ACCENT_HOV"]
            ACCENT_BG = P["ACCENT_BG"]
            OK_BG, OK_FG = P["OK_BG"], P["OK_FG"]
            WARN_BG, WARN_FG = P["WARN_BG"], P["WARN_FG"]
            ERR_BG, ERR_FG = P["ERR_BG"], P["ERR_FG"]
            SEL_BG, SEL_FG = P["SEL_BG"], P["SEL_FG"]
            HOVER_BG = P["HOVER_BG"]
            HEADER_BG, HEADER_BORDER = P["HEADER_BG"], P["HEADER_BORDER"]

            # Re-aplicar estilos ttk (todos los ttk widgets se actualizan solos)
            self._init_styles()

            # Reconfigurar widgets tk custom
            self.configure(bg=BG)
            if hasattr(self, "_sidebar_canvas"):
                self._sidebar_canvas.configure(bg=BG)
            if hasattr(self, "video_holder"):
                self.video_holder.configure(bg=P["VIDEO_BG"])
            if hasattr(self, "video_placeholder"):
                self.video_placeholder.configure(bg=P["VIDEO_BG"], fg=MUTED)
            if hasattr(self, "_titlebar"):
                self._titlebar.configure(bg=BG)
                self._title_label.configure(bg=BG, fg=TEXT)

            # Cada panel re-colorea su header
            for panel in self._panels:
                try: panel.apply_palette()
                except Exception: pass
            if hasattr(self, "_action_panel"):
                try: self._action_panel.apply_palette()
                except Exception: pass
            # Re-colorear el label de version (tk.Label custom)
            if hasattr(self, "ver_label"):
                try: self.ver_label.configure(bg=BG, fg=ACCENT)
                except Exception: pass

            # Re-render contenido dinamico
            self._refresh_diagnostics()
            self._render_format_matrix()

            if hasattr(self, "btn_theme"):
                self.btn_theme.configure(text="🌙" if name == "light" else "☀")

            self.cfg["theme"] = name
            save_config(self.cfg)

        def _sync_embed_size(self) -> None:
            """Debounced: coalesce multiples Configure rapidos."""
            if not self._embedded_hwnd: return
            # Durante una animacion explicita, ese loop sincroniza el HWND
            # frame-a-frame con SWP_NOREDRAW. Evitamos que un Configure
            # debounce-eado interfiera con un sync repintado.
            if getattr(self, "_anim_in_progress", False): return
            if self._sync_embed_after is not None: return
            self._sync_embed_after = self.after(20, self._do_sync_embed)

        def _do_sync_embed(self, fast: bool = False) -> None:
            self._sync_embed_after = None
            if not self._embedded_hwnd: return
            x, y, w, h = self._video_target_rect()
            if w < 50 or h < 50: return
            new_rect = (x, y, w, h)
            if new_rect == self._last_embed_rect: return
            resize_hwnd_at(self._embedded_hwnd, x, y, w, h, fast=fast)
            self._last_embed_rect = new_rect

        def _make_section(self, title: str, key: str | None = None):
            """Crea una seccion colapsable. Si se pasa key i18n, registra el
            panel para que cambie de titulo al cambiar el idioma."""
            actual_title = self._t(key) if key else title
            cb = (lambda exp, k=key: self._on_panel_toggle(k, exp)) if key else None
            panel = CollapsiblePanel(self._target, actual_title, self,
                                       on_toggle=cb)
            panel.section_key = key
            panel.pack(fill="x", padx=8, pady=(0, 6))
            self._panels.append(panel)
            if key:
                if not hasattr(self, "_panel_keys"):
                    self._panel_keys = []
                self._panel_keys.append((panel, key))
            return panel.body

        def _on_panel_toggle(self, key: str, expanded: bool) -> None:
            """Persiste el estado colapsado/expandido de cada panel."""
            if not key: return
            coll = dict(self.cfg.get("panel_collapsed") or {})
            if expanded:
                coll.pop(key, None)
            else:
                coll[key] = True
            self.cfg["panel_collapsed"] = coll
            self._save_cfg()

        def _save_panel_order(self) -> None:
            """Guarda el orden actual de los paneles en cfg."""
            order = [getattr(p, "section_key", None)
                      for p in self._panels
                      if getattr(p, "section_key", None)]
            if order != self.cfg.get("panel_order"):
                self.cfg["panel_order"] = order
                self._save_cfg()

        def _move_panel(self, panel, direction: int) -> None:
            if panel not in self._panels: return
            i = self._panels.index(panel)
            j = i + direction
            if not (0 <= j < len(self._panels)): return
            self._panels[i], self._panels[j] = self._panels[j], self._panels[i]
            for p in self._panels: p.pack_forget()
            for p in self._panels: p.pack(fill="x", padx=8, pady=(0, 6))
            self._save_panel_order()
            # Refrescar scrollregion
            self.after(50, lambda: self._sidebar_canvas.configure(
                scrollregion=self._sidebar_canvas.bbox("all")))

        def _apply_persisted_layout(self) -> None:
            """Aplica orden + estados colapsados guardados en cfg al sidebar.
            Se llama UNA vez, despues de que todos los paneles estan creados.
            Es robusta a paneles renombrados / nuevos: los desconocidos van
            al final y los stale en cfg se ignoran."""
            saved_order = self.cfg.get("panel_order") or []
            by_key = {p.section_key: p for p in self._panels
                       if getattr(p, "section_key", None)}
            ordered: list = []
            seen: set = set()
            for k in saved_order:
                p = by_key.get(k)
                if p is not None and id(p) not in seen:
                    ordered.append(p); seen.add(id(p))
            for p in self._panels:
                if id(p) not in seen:
                    ordered.append(p); seen.add(id(p))
            if ordered != self._panels:
                self._panels = ordered
                for p in self._panels: p.pack_forget()
                for p in self._panels: p.pack(fill="x", padx=8, pady=(0, 6))
            # Estado colapsado
            coll = self.cfg.get("panel_collapsed") or {}
            for p in self._panels:
                k = getattr(p, "section_key", None)
                if k and coll.get(k):
                    try: p.set_collapsed(True)
                    except Exception: pass

        def _open_video_dir(self) -> None:
            path = self.cfg.get("video_dir", "")
            if not path: return
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
                os.startfile(path)
                self._set_status(f"Abierto: {path}")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

        def _open_screenshot_dir(self) -> None:
            path = self.cfg.get("screenshot_dir", "")
            if not path: return
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
                os.startfile(path)
                self._set_status(f"Abierto: {path}")
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

        # ===== Acciones =====
        # ===== i18n helpers =====
        def _t(self, key: str, **fmt) -> str:
            return t(key, lang=self.lang, **fmt)

        def _tt_track(self, widget, key: str) -> "ToolTip":
            """Crea un ToolTip con la traduccion actual y lo registra para
            actualizar al cambiar idioma."""
            tt = ToolTip(widget, self._t(key))
            self._tt_keyed.append((tt, key))
            return tt

        def _cycle_language(self) -> None:
            """Avanza al siguiente idioma disponible y aplica en vivo."""
            avail = list(TRANSLATIONS.keys())
            cur = self.lang
            idx = avail.index(cur) if cur in avail else 0
            new = avail[(idx + 1) % len(avail)]
            self.lang = new
            self.cfg["language"] = new
            self._save_cfg()
            # Tooltips
            for tt, key in self._tt_keyed:
                try: tt.set_text(self._t(key))
                except Exception: pass
            # Section titles (CollapsiblePanel)
            for panel, key in getattr(self, "_panel_keys", []):
                try: panel.set_title(self._t(key))
                except Exception: pass
            # Sistema labels (Estado: / Diagnostico: / Version:)
            for lbl, key in getattr(self, "_label_keys", []):
                try: lbl.configure(text=self._t(key))
                except Exception: pass
            # Version label (texto compuesto: vX.Y.Z + traduccion)
            if hasattr(self, "ver_label"):
                try:
                    self.ver_label.configure(
                        text=f"v{APP_VERSION}  ▸  {self._t('sys.history')}")
                except Exception: pass
            # Status: actualizar al "Listo" del idioma nuevo solo si es generico
            generic_status = {"Listo", "Ready"}
            if self.var_status.get() in generic_status:
                self._set_status(self._t("st.ready"))
            # Format-matrix labels y placeholder de video
            try: self._render_format_matrix()
            except Exception: pass
            if hasattr(self, "video_placeholder") and not self._embedded_hwnd:
                try:
                    self.video_placeholder.configure(
                        text=self._t("lbl.video_placeholder"))
                except Exception: pass

        # ===== Layout helper =====
        def _layout_main(self) -> None:
            """Re-pack video + sidebar segun cfg sidebar_side. La sidebar se
            esconde solo en focus mode (toggle por doble-click sobre el video
            o boton ⤢)."""
            side = self.cfg.get("sidebar_side", "right")
            # IMPORTANTE: usar self._video_pane, no self._target. _target se
            # reasigna durante _build a la sidebar_inner.
            for w in (self._video_pane, self.sidebar_container):
                try: w.pack_forget()
                except Exception: pass
            if self.sidebar_visible:
                self.sidebar_container.pack(side=side, fill="y")
            self._video_pane.pack(side="left", fill="both", expand=True)

        def _toggle_sidebar_side(self) -> None:
            cur = self.cfg.get("sidebar_side", "right")
            self.cfg["sidebar_side"] = "left" if cur == "right" else "right"
            self._save_cfg()
            self._layout_main()
            self._schedule_resync()

        # ===== Video embebido =====
        def _build_video(self) -> None:
            self._embedded_hwnd = None
            self._embed_attempts = 0
            self._last_embed_rect: tuple[int, int, int, int] | None = None
            self.video_holder = tk.Frame(self._target, bg="#000000",
                                          width=720, height=405)
            self.video_holder.pack(fill="both", expand=True)
            self.video_placeholder = tk.Label(
                self.video_holder, bg="#000000", fg="#888",
                text=self._t("lbl.video_placeholder"),
                font=("Segoe UI", 10),
            )
            self.video_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            self.video_holder.bind("<Configure>", self._on_video_resize)
            # Scroll wheel sobre el holder -> volumen
            self.video_holder.bind("<MouseWheel>", self._on_video_wheel)
            self.video_placeholder.bind("<MouseWheel>", self._on_video_wheel)
            # Click rueda (middle button) -> toggle mute
            def _mute_click(_e):
                self._toggle_mute()
                return "break"
            self.video_holder.bind("<Button-2>", _mute_click)
            self.video_placeholder.bind("<Button-2>", _mute_click)
            # Doble-click -> toggle popup (focus mode)
            self.video_holder.bind("<Double-Button-1>",
                                    self._on_video_double_click)
            self.video_placeholder.bind("<Double-Button-1>",
                                         self._on_video_double_click)

        def _video_target_rect(self) -> tuple[int, int, int, int]:
            """Devuelve (x, y, w, h) del area de video, relativos al area cliente
            del HWND parent del embed (el wrapper top-level Win32)."""
            self.update_idletasks()
            parent_hwnd = self._toplevel_hwnd()
            if parent_hwnd:
                cli_x, cli_y = get_client_offset(parent_hwnd)
            else:
                # fallback: usar el winfo_rootx del toplevel
                cli_x = self.winfo_rootx()
                cli_y = self.winfo_rooty()
            hx = self.video_holder.winfo_rootx()
            hy = self.video_holder.winfo_rooty()
            return (hx - cli_x, hy - cli_y,
                    self.video_holder.winfo_width(),
                    self.video_holder.winfo_height())

        def _on_video_resize(self, event=None) -> None:
            self._sync_embed_size()

        def _on_window_configure(self, event=None) -> None:
            # Tk dispara <Configure> en muchos widgets; solo actuamos cuando
            # el evento es del toplevel (self).
            if event is not None and event.widget is not self:
                return
            self._sync_embed_size()

        def _try_embed(self) -> None:
            """Reintenta encontrar la ventana de ffplay y reparentarla en el toplevel."""
            if not self.is_running() or self._embedded_hwnd:
                return
            self._embed_attempts += 1
            s = self.master_session
            ffplay = s.get("ffplay") if s else None
            title = s.get("window_title") if s else None
            if not ffplay:
                return
            hwnd = find_main_hwnd_for_pid(ffplay.pid)
            if not hwnd and title:
                hwnd = find_hwnd_by_pid_and_title(ffplay.pid, title)
            if not hwnd:
                if self._embed_attempts < 40:
                    self.after(500, self._try_embed)
                else:
                    self._set_status("No pude encontrar la ventana de ffplay (timeout).")
                return

            self.update_idletasks()
            x, y, w, h = self._video_target_rect()
            if w < 50 or h < 50:
                if self._embed_attempts < 40:
                    self.after(300, self._try_embed)
                return

            # Embeber en el HWND wrapper del toplevel (no en winfo_id).
            # Asi las coordenadas son relativas al mismo HWND que usamos
            # para calcular el rect en _video_target_rect.
            parent_hwnd = self._toplevel_hwnd() or self.winfo_id()
            if embed_hwnd_at(hwnd, parent_hwnd, x, y, w, h):
                self._embedded_hwnd = hwnd
                self._embedded_parent_hwnd = parent_hwnd
                self._last_embed_rect = (x, y, w, h)
                try: self.video_placeholder.place_forget()
                except Exception: pass
                # Deshabilitar input en ffplay: los clicks/scroll caen al
                # parent Tk y nuestros bindings los reciben. ffplay sigue
                # renderizando normal y PostMessage para teclas funciona igual.
                try:
                    if _IS_WIN: _user32.EnableWindow(hwnd, False)
                except Exception: pass
                # Aplicar estado de mute persistido (cfg) al nuevo ffplay
                if self.cfg.get("muted"):
                    # delay para dar tiempo a pycaw a ver la sesion
                    self.after(300, lambda: self._set_ffplay_mute_live(True))
                self._set_status(
                    f"Vista previa embebida ({w}x{h})")
            else:
                if self._embed_attempts < 40:
                    self.after(500, self._try_embed)
                else:
                    self._set_status(
                        f"Embed fallo (hwnd={hwnd:x} parent={parent_hwnd:x})")

        def _release_embed(self) -> None:
            # Si estabamos en popup mode, salir (el ffplay va a morir)
            if self._popup_mode:
                try: self._exit_popup_mode()
                except Exception: pass
            self._embedded_hwnd = None
            self._embed_attempts = 0
            self._last_embed_rect = None
            self._ffplay_volume_ctl = None
            try:
                self.video_placeholder.configure(
                    text=self._t("lbl.video_placeholder"))
                self.video_placeholder.place(relx=0.5, rely=0.5, anchor="center")
            except Exception: pass

        # ===== Acciones =====
        # ===== Sidebar header: logo + quick controls + acciones =====
        def _build_sidebar_header(self) -> None:
            f = ttk.Frame(self._target, padding=(10, 10, 10, 6))
            f.pack(fill="x")

            # Logo / titulo
            ttk.Label(f, text=APP_NAME,
                       style="Title.TLabel").pack(anchor="w", pady=(0, 8))

            # ----- Fila 1: SETTINGS (izq) + WINDOW CONTROLS (der) -----
            # Todos los botones de esta fila usan el mismo style/tamano para
            # consistencia visual. Grupos separados con un Separator.
            row1 = ttk.Frame(f); row1.pack(fill="x")
            ICON = "Icon.TButton"
            BTN_W = 3

            def add_icon(parent, text: str, cmd, tt_key: str, *,
                          side: str = "left", attr: str | None = None,
                          style: str = ICON) -> ttk.Button:
                btn = ttk.Button(parent, text=text, width=BTN_W,
                                  style=style, command=cmd)
                pad = (0, 2) if side == "left" else (2, 0)
                btn.pack(side=side, padx=pad)
                self._tt_track(btn, tt_key)
                if attr: setattr(self, attr, btn)
                return btn

            # Grupo izquierdo: ajustes (side / lang / theme)
            add_icon(row1, "⇆", self._toggle_sidebar_side, "tt.side_toggle")
            add_icon(row1, "🌐", self._cycle_language, "tt.lang", attr="btn_lang")
            theme_glyph = "🌙" if THEME_NAME == "light" else "☀"
            add_icon(row1, theme_glyph, self._toggle_theme, "tt.theme",
                      attr="btn_theme")

            # Grupo derecho (orden visual: min · full · max · close)
            add_icon(row1, "✕", self._close_app, "tt.close",
                      side="right", style="Close.TButton")
            add_icon(row1, "🗖", self._toggle_maximize, "tt.maximize",
                      side="right", attr="btn_max")
            add_icon(row1, "⛶", self._toggle_fullscreen, "tt.fullscreen",
                      side="right", attr="btn_full")
            add_icon(row1, "🗕", self._hide, "tt.minimize", side="right")

            # ----- Fila 2: ACCIONES PRIMARIAS -----
            # Una sola fila uniforme: mute · popup · preview · screenshot · record
            # Mismo BTN_W y mismo Action.TButton — solo el style cambia para los
            # primarios (acentuado).
            row2 = ttk.Frame(f); row2.pack(fill="x", pady=(8, 0))

            # Toggles secundarios (audio + focus)
            add_icon(row2, "🔊" if not self.cfg.get("muted") else "🔇",
                      self._toggle_mute, "tt.mute", attr="btn_mute")
            add_icon(row2, "⤢", self._toggle_popup, "tt.popup",
                      attr="btn_popup")

            # Pequeno separador visual antes de las acciones primarias
            ttk.Frame(row2, width=8).pack(side="left")

            # Acciones primarias — Action.TButton (acento) pero MISMO BTN_W
            add_icon(row2, "▶", self._toggle_preview, "tt.preview",
                      attr="btn_preview", style="Action.TButton")
            add_icon(row2, "📷", self._screenshot, "tt.screenshot",
                      attr="btn_screenshot", style="Action.TButton")
            self.btn_screenshot.configure(state="disabled")
            self.btn_screenshot.bind(
                "<Control-Button-1>",
                lambda e: self._open_screenshot_dir())
            add_icon(row2, "⏺", self._toggle_record, "tt.record",
                      attr="btn_record", style="Action.TButton")
            self.btn_record.configure(state="disabled")
            self.btn_record.bind(
                "<Control-Button-1>",
                lambda e: self._open_video_dir())

            # ----- Fila 3: status + REC timer -----
            row3 = ttk.Frame(f); row3.pack(fill="x", pady=(8, 0))
            ttk.Label(row3, textvariable=self.var_status,
                       style="Sub.TLabel").pack(side="left")
            ttk.Label(row3, textvariable=self.var_timer,
                       style="Rec.TLabel"
                       ).pack(side="right")

            self._title_label = f  # compat: drag handle

        # _build_actions removido: ahora vive como header de la sidebar.

        # ===== Diagnostico (ya no es panel propio; vive en Sistema) =====
        def _build_diagnostics(self) -> None:  # legacy, no usado
            pass

        def _render_diagnostics(self, items: list[dict]) -> None:
            for w in self.diag_inner.winfo_children():
                w.destroy()
            # Calcular wraplength dinamico segun ancho del panel
            try:
                self.diag_inner.update_idletasks()
                avail = max(220, self.diag_inner.winfo_width() - 60)
            except Exception:
                avail = 320
            for item in items:
                sev = item.get("severity", "info")
                msg = item.get("message", "")
                fixes = item.get("fixes", [])
                bg, fg = _sev_colors().get(sev, (CARD, TEXT))
                # Card de la diagnostico
                card = tk.Frame(self.diag_inner, bg=bg, bd=0, padx=10, pady=8)
                card.pack(fill="x", pady=2)
                # Fila 1: glyph + mensaje (full width)
                row = tk.Frame(card, bg=bg)
                row.pack(fill="x")
                glyph = SEV_GLYPH.get(sev, "·")
                tk.Label(row, text=glyph, bg=bg, fg=fg,
                          font=("Segoe UI", 11, "bold"), width=2
                          ).pack(side="left", anchor="n")
                tk.Label(row, text=msg, bg=bg, fg=fg,
                          font=("Segoe UI", 9), anchor="w",
                          wraplength=avail, justify="left"
                          ).pack(side="left", fill="x", expand=True)
                # Fila 2: botones de fix (debajo, alineados a la derecha)
                if fixes:
                    btn_row = tk.Frame(card, bg=bg)
                    btn_row.pack(fill="x", pady=(6, 0))
                    for fx in fixes:
                        label = fx.get("label", "Aplicar")
                        changes = fx.get("changes", {})
                        btn = tk.Button(
                            btn_row, text=label, bg=CARD, fg=fg,
                            activebackground=HOVER_BG, activeforeground=fg,
                            relief="solid", borderwidth=1,
                            font=("Segoe UI", 9, "bold"),
                            cursor="hand2", padx=10, pady=3,
                            command=lambda c=changes: self._apply_fix(c),
                        )
                        btn.pack(side="right", padx=(4, 0))

        def _apply_fix(self, changes: dict) -> None:
            """Aplica los cambios al cfg, propaga a las vars de los widgets,
            guarda y refresca todo (incluida la matriz)."""
            for key, value in changes.items():
                var = self._vars.get(key) if hasattr(self, "_vars") else None
                if var is not None:
                    try:
                        if isinstance(var, tk.IntVar):
                            var.set(int(value))
                        elif isinstance(var, tk.BooleanVar):
                            var.set(bool(value))
                        else:
                            var.set(str(value))
                        # var.trace_add ya actualiza cfg via on_change
                        continue
                    except Exception:
                        pass
                # Sin var registrada (ej. resolution/framerate controlados por la matriz)
                self.cfg[key] = value
            save_config(self.cfg)
            self._render_format_matrix()
            self._refresh_diagnostics()
            self._set_status("Fix aplicado")

        # ===== Dispositivos =====
        def _build_devices(self) -> None:
            f = self._make_section("Dispositivos", key="sec.devices")
            # No bloqueamos el build con la enumeracion DirectShow (~1-2s).
            # Pre-poblamos los combos solo con el valor actual del cfg para
            # que se pinten al instante; un thread llena la lista completa
            # apenas termine el spawn de ffmpeg -list_devices.
            cur_v = self.cfg.get("video_device") or ""
            cur_a = self.cfg.get("audio_device") or "(sin audio)"
            r = 0
            self._add_combo(f, r, "Video", "video_device", [cur_v] if cur_v else [],
                             label_key="lbl.video",
                             help_key=None, on_change_extra=self._on_video_changed); r += 1
            self._add_combo(f, r, "Audio", "audio_device",
                             ["(sin audio)", cur_a] if cur_a != "(sin audio)" else ["(sin audio)"],
                             special_none="(sin audio)",
                             label_key="lbl.audio",
                             help_key=None, on_change_extra=self._refresh_diagnostics); r += 1
            f.grid_columnconfigure(1, weight=1)
            # Cargar la lista real en background
            def _load():
                try: v, a = list_dshow_devices()
                except Exception: v, a = [], []
                self.after(0, lambda: self._on_devices_loaded(v, a))
            threading.Thread(target=_load, daemon=True).start()

        def _on_devices_loaded(self, video: list[str], audio: list[str]) -> None:
            """Refresca los combos de dispositivos una vez que la enumeracion
            DirectShow termino (corre en thread aparte para no bloquear el build)."""
            try:
                if "video_device" in self._combos:
                    self._combos["video_device"].configure(values=video)
                if "audio_device" in self._combos:
                    self._combos["audio_device"].configure(
                        values=["(sin audio)"] + audio)
            except Exception: pass

        # ===== Calidad (resolucion + FPS compacto) =====
        def _build_format_matrix(self) -> None:
            self.fmt_frame = self._make_section("Calidad", key="sec.quality")
            self.fmt_status = ttk.Label(self.fmt_frame, text="",
                                         style="Sub.TLabel",
                                         wraplength=320, justify="left")
            self.fmt_status.pack(anchor="w", pady=(0, 6))

            # Combobox compacto con todas las combinaciones soportadas
            self.fmt_combo_var = tk.StringVar()
            self.fmt_combo = ttk.Combobox(
                self.fmt_frame, textvariable=self.fmt_combo_var,
                state="readonly", width=24)
            self.fmt_combo.pack(fill="x")
            self.fmt_combo.bind(
                "<<ComboboxSelected>>", self._on_format_combo)
            self._tt_track(self.fmt_combo, "lbl.fmt_picker_tip")
            self._render_format_matrix()

        def _render_format_matrix(self) -> None:
            cur_res = self.cfg.get("resolution", "")
            cur_fps = int(self.cfg.get("framerate", 60))
            device = self.cfg.get("video_device") or "—"
            self.fmt_status.config(
                text=(self._t("lbl.fmt_active", res=cur_res, fps=cur_fps)
                      + "\n"
                      + self._t("lbl.fmt_hardware", dev=device))
            )
            options: list[str] = []
            if self._formats:
                def area(r: str) -> int:
                    try: w, h = r.split("x"); return int(w) * int(h)
                    except Exception: return 0
                all_res = sorted(self._formats.keys(),
                                  key=lambda r: -area(r))
                for res in all_res:
                    max_fps = self._formats.get(res, 0.0)
                    for fps in (120, 60, 30):
                        if max_fps + 0.5 >= fps:
                            options.append(f"{res} @ {fps}fps")
            if not options:
                options = [self._t("lbl.fmt_no_device")]
            cur_str = f"{cur_res} @ {cur_fps}fps"
            self.fmt_combo.configure(values=options)
            if cur_str in options:
                self.fmt_combo_var.set(cur_str)
            else:
                marked = f"{cur_str}  {self._t('lbl.fmt_unsupported')}"
                vals = list(options)
                if marked not in vals: vals = [marked] + vals
                self.fmt_combo.configure(values=vals)
                self.fmt_combo_var.set(marked)

        def _on_format_combo(self, event=None) -> None:
            val = self.fmt_combo_var.get()
            import re as _re
            m = _re.match(r"(\d+x\d+)\s*@\s*(\d+)\s*fps", val)
            if not m: return
            res = m.group(1)
            fps = int(m.group(2))
            if (res == self.cfg.get("resolution")
                    and fps == int(self.cfg.get("framerate", 0))):
                return
            self.cfg["resolution"] = res
            self.cfg["framerate"] = fps
            self._save_cfg()
            self._render_format_matrix()
            self._refresh_diagnostics()

        def _on_video_changed(self) -> None:
            # Re-consultar formatos en hilo aparte
            device = self.cfg.get("video_device")
            self.fmt_status.config(text=self._t("lbl.fmt_loading"))
            self._formats = {}
            self._render_format_matrix()
            self._refresh_diagnostics()
            if not device: return
            def worker():
                fmts = query_supported_formats(device)
                self.after(0, lambda: self._on_formats_loaded(fmts))
            threading.Thread(target=worker, daemon=True).start()

        def _on_formats_loaded(self, fmts: dict[str, float]) -> None:
            self._formats = fmts
            self._render_format_matrix()
            self._refresh_diagnostics()

        # ===== Preview & audio =====
        def _build_preview_audio(self) -> None:
            f = self._make_section("Vista previa y audio", key="sec.preview_audio")
            r = 0
            self._add_check(f, r, "Always on top",
                             "always_on_top",
                             label_key="lbl.always_on_top"); r += 1
            self._add_volume(f, r); r += 1
            self._add_combo(f, r, "Buffer audio (ms)", "audio_buffer_size_ms",
                             ["0", "40", "60", "80", "120", "200"],
                             label_key="lbl.audio_buffer",
                             cast_int=True); r += 1
            f.grid_columnconfigure(1, weight=1)

        # ===== Captura =====
        def _build_capture(self) -> None:
            f = self._make_section("Captura de pantalla", key="sec.capture")
            r = 0
            self._add_check(f, r, "Copiar al portapapeles",
                             "screenshot_to_clipboard",
                             label_key="lbl.clipboard"); r += 1
            self._add_check(f, r, "Guardar archivo PNG",
                             "screenshot_to_file",
                             label_key="lbl.png"); r += 1
            f.grid_columnconfigure(1, weight=1)

        # ===== Carpetas de salida =====
        def _build_folders(self) -> None:
            f = self._make_section("Carpetas de salida", key="sec.folders")
            r = 0
            self._add_path(f, r, "Capturas", "screenshot_dir",
                            label_key="lbl.shots_dir"); r += 1
            self._add_path(f, r, "Videos", "video_dir",
                            label_key="lbl.videos_dir"); r += 1
            f.grid_columnconfigure(1, weight=1)

        # ===== Grabacion =====
        def _build_recording(self) -> None:
            f = self._make_section("Grabacion", key="sec.recording")
            r = 0
            self._add_combo(f, r, "Codec video", "video_codec",
                             ["libx264", "libx265", "h264_nvenc", "hevc_nvenc"],
                             label_key="lbl.codec_video"); r += 1
            # Advisor de GPU
            self.codec_adv = ttk.Label(f, text="", style="Sub.TLabel")
            self.codec_adv.grid(row=r, column=0, columnspan=3, sticky="w",
                                 padx=4, pady=(0, 4))
            r += 1
            self._add_combo(f, r, "Preset", "video_preset",
                             ["ultrafast", "superfast", "veryfast",
                              "faster", "fast", "medium"],
                             label_key="lbl.preset"); r += 1
            self._add_entry(f, r, "CRF (0-51)", "video_crf",
                             cast_int=True, w=10,
                             label_key="lbl.crf"); r += 1
            self._add_combo(f, r, "Codec audio", "audio_codec",
                             ["aac", "libopus", "libmp3lame"],
                             label_key="lbl.codec_audio"); r += 1
            self._add_combo(f, r, "Bitrate audio", "audio_bitrate",
                             ["96k", "128k", "192k", "256k", "320k"],
                             label_key="lbl.bitrate"); r += 1
            self._add_combo(f, r, "Contenedor", "container",
                             ["mkv", "mp4"],
                             label_key="lbl.container"); r += 1
            f.grid_columnconfigure(1, weight=1)

        # ===== Sistema (status + diagnostico + version) =====
        def _build_system(self) -> None:
            f = self._make_section("Sistema", key="sec.system")
            if not hasattr(self, "_label_keys"):
                self._label_keys = []

            lbl_state = ttk.Label(f, text=self._t("sys.state"),
                                    style="Sub.TLabel")
            lbl_state.pack(anchor="w")
            self._label_keys.append((lbl_state, "sys.state"))
            ttk.Label(f, textvariable=self.var_status,
                      ).pack(anchor="w", pady=(0, 10))

            lbl_diag = ttk.Label(f, text=self._t("sys.diagnostics"),
                                   style="Sub.TLabel")
            lbl_diag.pack(anchor="w")
            self._label_keys.append((lbl_diag, "sys.diagnostics"))
            self.diag_frame = f
            self.diag_inner = ttk.Frame(f)
            self.diag_inner.pack(fill="x", pady=(0, 10))
            self._render_diagnostics(
                [{"severity": "info", "message": "Cargando..."}])

            lbl_ver = ttk.Label(f, text=self._t("sys.version"),
                                  style="Sub.TLabel")
            lbl_ver.pack(anchor="w")
            self._label_keys.append((lbl_ver, "sys.version"))
            self.ver_label = tk.Label(
                f, text=f"v{APP_VERSION}  ▸  {self._t('sys.history')}",
                bg=BG, fg=ACCENT, cursor="hand2",
                font=FONT_BODY, anchor="w")
            self.ver_label.pack(anchor="w")
            def _click_version(_e):
                self._show_changelog()
                return "break"
            self.ver_label.bind("<Button-1>", _click_version)
            self.ver_label.bind(
                "<Enter>",
                lambda e: self.ver_label.configure(font=(FONT_BODY[0], FONT_BODY[1], "underline")))
            self.ver_label.bind(
                "<Leave>",
                lambda e: self.ver_label.configure(font=FONT_BODY))
            ToolTip(self.ver_label,
                    "Ver el historial de versiones con features y bugs corregidos en cada release.")

        # ---------- builders ----------
        def _help_for(self, key: str) -> str:
            """Devuelve el texto de ayuda en el idioma actual.
            Cae a 'es' si el idioma activo no tiene la entrada."""
            if not key: return ""
            entry = HELP_TRANSLATIONS.get(self.lang, {}).get(key)
            if entry is None:
                entry = HELP_TRANSLATIONS.get("es", {}).get(key)
            if entry is None:
                return ""
            title, body = entry
            return f"{title}\n\n{body}"

        def _add_help_button(self, parent, r: int, key: str | None) -> None:
            """Renderiza el `?` de ayuda como un Label con tooltip on hover.
            Antes era un Button que abria un messagebox — ahora la
            informacion se ofrece sin interrumpir el flujo del user."""
            if not key: return
            if key not in HELP_TRANSLATIONS.get(self.lang, {}) \
                    and key not in HELP_TRANSLATIONS.get("es", {}):
                return
            lbl = tk.Label(parent, text="?",
                            bg=P["CARD"], fg=P["SUB"],
                            font=("Segoe UI", 9, "bold"),
                            cursor="question_arrow",
                            relief="solid", borderwidth=1,
                            padx=6, pady=0, width=2)
            lbl.grid(row=r, column=2, padx=(2, 4), pady=2)
            # Hover: cambio sutil de color
            def _enter(_e):
                try: lbl.configure(bg=P["HOVER_BG"], fg=P["ACCENT"])
                except Exception: pass
            def _leave(_e):
                try: lbl.configure(bg=P["CARD"], fg=P["SUB"])
                except Exception: pass
            lbl.bind("<Enter>", _enter)
            lbl.bind("<Leave>", _leave)
            # Tooltip lazy: re-resuelve el texto en cada hover -> i18n vivo
            ToolTip(lbl, lambda k=key: self._help_for(k),
                     delay=250, wrap=380)

        # ---------- Helper interno: registra label para i18n vivo ----------
        def _make_label(self, parent, label: str, label_key: str | None,
                          *, row: int = 0, **grid_kw) -> ttk.Label:
            text = self._t(label_key) if label_key else label
            lbl = ttk.Label(parent, text=text)
            grid_kw.setdefault("row", row)
            grid_kw.setdefault("column", 0)
            grid_kw.setdefault("sticky", "w")
            grid_kw.setdefault("padx", 4)
            grid_kw.setdefault("pady", 3)
            lbl.grid(**grid_kw)
            if label_key:
                if not hasattr(self, "_label_keys"): self._label_keys = []
                self._label_keys.append((lbl, label_key))
            return lbl

        def _add_combo(self, parent, r: int, label: str, key: str,
                        values: list[str], *, cast_int: bool = False,
                        special_none: str | None = None,
                        help_key: str | None = ...,
                        label_key: str | None = None,
                        on_change_extra=None) -> None:
            self._make_label(parent, label, label_key, row=r)
            current = self.cfg.get(key)
            if special_none is not None and current is None:
                current = special_none
            var = tk.StringVar(value=str(current) if current is not None else "")
            cb = ttk.Combobox(parent, textvariable=var, values=values, width=30)
            cb.grid(row=r, column=1, sticky="we", padx=4, pady=3)
            ToolTip(cb, f"variable: {key}")
            if not hasattr(self, "_combos"): self._combos = {}
            self._combos[key] = cb

            def on_change(*_):
                v = var.get()
                if special_none is not None and v == special_none:
                    self.cfg[key] = None
                else:
                    if cast_int:
                        try: v = int(v)
                        except (TypeError, ValueError): return
                    self.cfg[key] = v
                self._save_cfg()
                if on_change_extra:
                    try: on_change_extra()
                    except Exception: pass
                else:
                    self._refresh_diagnostics()
            var.trace_add("write", on_change)
            self._vars[key] = var

            hk = key if help_key is ... else help_key
            self._add_help_button(parent, r, hk)

        def _add_entry(self, parent, r: int, label: str, key: str, *,
                        cast_int: bool = False, w: int = 24,
                        label_key: str | None = None) -> None:
            self._make_label(parent, label, label_key, row=r)
            var = tk.StringVar(value=str(self.cfg[key]))
            ent = ttk.Entry(parent, textvariable=var, width=w)
            ent.grid(row=r, column=1, sticky="w", padx=4, pady=3)
            ToolTip(ent, f"variable: {key}")
            def on_change(*_):
                v = var.get()
                if cast_int:
                    try: v = int(v)
                    except (TypeError, ValueError): return
                self.cfg[key] = v
                self._save_cfg()
                self._refresh_diagnostics()
            var.trace_add("write", on_change)
            self._vars[key] = var
            self._add_help_button(parent, r, key)

        def _add_check(self, parent, r: int, label: str, key: str, *,
                        label_key: str | None = None) -> None:
            var = tk.BooleanVar(value=bool(self.cfg[key]))
            text = self._t(label_key) if label_key else label
            chk = ttk.Checkbutton(parent, text=text, variable=var)
            chk.grid(row=r, column=0, columnspan=2,
                      sticky="w", padx=4, pady=3)
            if label_key:
                if not hasattr(self, "_label_keys"): self._label_keys = []
                self._label_keys.append((chk, label_key))
            def on_change(*_):
                self.cfg[key] = bool(var.get())
                self._save_cfg()
                self._refresh_diagnostics()
            var.trace_add("write", on_change)
            self._vars[key] = var
            self._add_help_button(parent, r, key)

        def _add_path(self, parent, r: int, label: str, key: str, *,
                        label_key: str | None = None) -> None:
            self._make_label(parent, label, label_key, row=r)
            var = tk.StringVar(value=str(self.cfg[key]))
            sub = ttk.Frame(parent)
            sub.grid(row=r, column=1, sticky="we", padx=4, pady=3)
            ttk.Entry(sub, textvariable=var).pack(side="left",
                                                    fill="x", expand=True)
            def pick():
                d = filedialog.askdirectory(initialdir=var.get(), parent=self)
                if d: var.set(d)
            ttk.Button(sub, text="...", width=3,
                       command=pick).pack(side="left", padx=(4, 0))
            def on_change(*_):
                self.cfg[key] = var.get()
                self._save_cfg()
            var.trace_add("write", on_change)
            self._vars[key] = var
            self._add_help_button(parent, r, key)

        def _add_volume(self, parent, r: int) -> None:
            self._make_label(parent, "Volumen", "lbl.volume", row=r)
            sub = ttk.Frame(parent)
            sub.grid(row=r, column=1, sticky="we", padx=4, pady=3)
            self.var_vol = tk.IntVar(value=int(self.cfg.get("volume", 80)))
            self.var_vol_lbl = tk.StringVar(value=str(self.var_vol.get()))
            ttk.Scale(sub, from_=0, to=100, orient="horizontal",
                      variable=self.var_vol).pack(side="left",
                                                    fill="x", expand=True)
            ttk.Label(sub, textvariable=self.var_vol_lbl, width=4
                      ).pack(side="left", padx=(6, 0))
            def on_change(*_):
                v = int(self.var_vol.get())
                self.var_vol_lbl.set(str(v))
                self.cfg["volume"] = v
                self._save_cfg()
            self.var_vol.trace_add("write", on_change)
            self._vars["volume"] = self.var_vol
            self._add_help_button(parent, r, "volume")

        # ---------- helpers ----------
        def _bootstrap(self) -> None:
            if not check_tools(quiet=True):
                messagebox.showerror(
                    "Falta ffmpeg",
                    f"No se encontraron ffmpeg.exe / ffplay.exe.\n\n"
                    f"Coloca los binarios en:\n{LOCAL_BIN}",
                    parent=self,
                )
                self._set_status("Falta ffmpeg en ./bin/")
            # Detect GPU async (puede ser lento por wmic)
            def gworker():
                gpu = detect_gpu_vendor()
                self.after(0, lambda: self._on_gpu_detected(gpu))
            threading.Thread(target=gworker, daemon=True).start()
            # Cargar formatos si hay device
            if self.cfg.get("video_device"):
                self._on_video_changed()
            else:
                self._refresh_diagnostics()

        def _on_gpu_detected(self, gpu: str) -> None:
            self._gpu = gpu
            self._refresh_codec_advisor()
            self._refresh_diagnostics()

        def _refresh_codec_advisor(self) -> None:
            if not hasattr(self, "codec_adv"): return
            codec = self.cfg.get("video_codec", "")
            text = f"GPU detectada: {self._gpu}"
            color = SUB
            if "nvenc" in codec and self._gpu != "nvidia":
                text += f"  ·  AVISO: '{codec}' requiere NVIDIA, fallara al grabar."
                color = ERR_FG
            elif "nvenc" in codec and self._gpu == "nvidia":
                text += "  ·  OK: codec acelerado por GPU, casi cero CPU."
                color = OK_FG
            elif codec == "libx265":
                text += "  ·  libx265: archivos mas chicos pero ~2x CPU vs libx264."
            self.codec_adv.config(text=text, foreground=color)

        def _refresh_sys_status(self) -> None:
            # var_sys ya no existe (panel Sistema simplificado); no-op de
            # compatibilidad con llamadas legacy.
            pass

        def _save_cfg(self) -> None:
            """Debounced save al disco: coalesce escrituras rapidas."""
            if self._save_cfg_after is not None: return
            self._save_cfg_after = self.after(180, self._do_save_cfg)

        def _do_save_cfg(self) -> None:
            self._save_cfg_after = None
            try: save_config(self.cfg)
            except Exception: pass

        def _refresh_diagnostics(self) -> None:
            """Debounced: coalesce multiples cambios rapidos en un solo refresh."""
            if self._diag_after is not None:
                return  # ya hay uno programado
            self._diag_after = self.after(80, self._do_refresh_diagnostics)

        def _do_refresh_diagnostics(self) -> None:
            self._diag_after = None
            items = compute_diagnostics(self.cfg, self._formats, self._gpu)
            self._render_diagnostics(items)
            self._refresh_codec_advisor()
            self._refresh_sys_status()

        def _verify(self) -> None:
            self._refresh_diagnostics()
            self._set_status("Estado actualizado")

        def _shortcut(self) -> None:
            ok, info = make_shortcut()
            self._set_status(("Acceso directo: " if ok else "Error: ") + info)

        def _show_changelog(self) -> None:
            """Abre el CHANGELOG en GitHub en el browser default. Antes
            era una ventana emergente con la lista local; ahora la
            single source of truth es el archivo del repo."""
            import webbrowser
            try:
                webbrowser.open(APP_CHANGELOG_URL, new=2)
                self._set_status(f"Abierto: {APP_CHANGELOG_URL}")
            except Exception as e:
                self._set_status(f"No pude abrir el browser: {e}")

        def _set_status(self, msg: str) -> None:
            self.var_status.set(msg)

        def _update_buttons(self) -> None:
            running = self.is_running()
            recording = self.is_recording()
            self.btn_preview.configure(text="⏹" if running else "▶")
            self.btn_screenshot.configure(
                state="normal" if running else "disabled")
            if not running:
                self.btn_record.configure(
                    state="disabled", text="⏺",
                    style="Action.TButton")
            elif recording:
                self.btn_record.configure(
                    state="normal", text="⏹",
                    style="ActionRec.TButton")
            else:
                self.btn_record.configure(
                    state="normal", text="⏺",
                    style="Action.TButton")

        def _guard_ready(self) -> bool:
            if not check_tools(quiet=True):
                messagebox.showerror("Falta ffmpeg",
                                      f"Coloca los binarios en {LOCAL_BIN}",
                                      parent=self); return False
            if not self.cfg.get("video_device"):
                messagebox.showerror("Sin dispositivo",
                                      "Elige un dispositivo de video.",
                                      parent=self); return False
            return True

        # ---------- actions ----------
        def _unique_title(self) -> str:
            import uuid
            return f"SwitchCapture-{uuid.uuid4().hex[:8]}"

        def _toggle_preview(self) -> None:
            if self.is_running():
                stop_master(self.master_session)
                self.master_session = None
                self._release_embed()
                try: LATEST_FRAME.unlink(missing_ok=True)
                except Exception: pass
                self._set_status("Listo")
                self._update_buttons()
                return
            if not self._guard_ready(): return
            try:
                self.master_session = start_master(
                    self.cfg, recording=False,
                    window_title=self._unique_title(), for_embed=True)
                self._set_status("Iniciando vista previa...")
                self._update_buttons()
                self._embed_attempts = 0
                self.after(400, self._try_embed)
                self.after(1500, self._check_alive)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

        def _check_alive(self) -> None:
            s = self.master_session
            if not s: return
            if s["ffmpeg"].poll() is not None:
                log = read_proc_log(s["ffmpeg"])
                err = extract_ffmpeg_error(log) or \
                      f"ffmpeg termino (codigo {s['ffmpeg'].returncode})."
                self.master_session = None
                self._update_buttons()
                self._set_status("Error · revisa Diagnostico")
                messagebox.showerror(
                    "Vista previa fallo",
                    f"ffmpeg cerro inmediatamente.\n\n{err}\n\n"
                    f"Revisa el panel Diagnostico.",
                    parent=self,
                )
            else:
                if self.is_recording():
                    self._set_status(f"Grabando → {s['out_file'].name}")
                else:
                    self._set_status("Vista previa activa")

        def _screenshot(self) -> None:
            if not self.is_running():
                self._set_status("Inicia la vista previa primero")
                return
            self._set_status("Capturando...")
            self.update_idletasks()
            def worker():
                path, msg = take_screenshot(self.cfg, master_running=True)
                def done():
                    self._set_status(msg)
                    if path:
                        self._show_toast(
                            f"📷 Captura guardada · {path.name}",
                            kind="success")
                    else:
                        self._show_toast(
                            "📷 Captura al portapapeles",
                            kind="info")
                self.after(0, done)
            threading.Thread(target=worker, daemon=True).start()

        def _toggle_record(self) -> None:
            """Toggle de grabacion sin reiniciar master ni ffplay.
            La preview NUNCA se freezea: solo se conecta/desconecta un
            recorder al tee del master."""
            if not self.is_running() or self._restarting: return
            session = self.master_session
            if session is None: return
            new_recording = not self.is_recording()
            self._restarting = True
            self.update_idletasks()
            if new_recording:
                # Iniciar grabacion: agregar recorder al tee del master
                try:
                    out = add_recorder(session, self.cfg)
                except Exception as e:
                    self._restarting = False
                    messagebox.showerror("Error", str(e), parent=self)
                    return
                self._restarting = False
                self._update_buttons()
                if out:
                    self._set_status(f"Grabando → {out.name}")
                    self._show_toast(
                        f"⏺ Grabacion iniciada · {out.name}",
                        kind="rec", duration_ms=2000)
                else:
                    self._set_status("Grabando")
                    self._show_toast(
                        "⏺ Grabacion iniciada",
                        kind="rec", duration_ms=2000)
            else:
                # Detener grabacion: feedback inmediato + EOF al recorder.
                try: self.btn_record.configure(state="disabled")
                except Exception: pass
                self._set_status(self._t("st.recording_saving"))
                self._show_toast(
                    self._t("toast.rec_finalizing"), kind="info",
                    duration_ms=4000)
                self.update_idletasks()
                def worker():
                    out, msg = remove_recorder(session)
                    def done():
                        self._restarting = False
                        self._update_buttons()
                        if out:
                            self._set_status(
                                f"Grabacion guardada · {msg}")
                            self._show_toast(
                                f"✓ Grabacion guardada · {msg}",
                                kind="success", duration_ms=2500)
                        else:
                            self._set_status("Vista previa activa")
                            self._show_toast(
                                "⚠ Grabacion sin archivo",
                                kind="warning", duration_ms=2500)
                    self.after(0, done)
                threading.Thread(target=worker, daemon=True).start()

        # ---------- polling ----------
        def _poll(self) -> None:
            # Mantener el embed sincronizado con el frame del video.
            # No depende de eventos <Configure> que a veces no llegan.
            self._sync_embed_size()

            # Si el recorder murio solo (ej. error de codec), limpiar
            s = self.master_session
            if s and s.get("recorder") is not None and not self._restarting:
                rec = s["recorder"]
                if rec.poll() is not None:
                    out, msg = remove_recorder(s)
                    self._update_buttons()
                    self._set_status(
                        f"Grabacion termino · {msg}"
                        if msg else "Grabacion termino inesperadamente")

            s = self.master_session
            if s:
                if self.is_recording():
                    elapsed = time.time() - s["start_time"]
                    mm = int(elapsed // 60); ss = int(elapsed % 60)
                    self.var_timer.set(f"REC  {mm:02d}:{ss:02d}")
                else:
                    self.var_timer.set("")

                # Si el usuario cerro la ventana de ffplay, mandamos 'q' a ffmpeg
                # para que termine limpio (sin broken pipe ni archivos truncados).
                ffplay = s.get("ffplay")
                if (ffplay and ffplay.poll() is not None
                        and s["ffmpeg"].poll() is None
                        and not self._restarting):
                    try:
                        if s["ffmpeg"].stdin:
                            s["ffmpeg"].stdin.write(b"q\n")
                            s["ffmpeg"].stdin.flush()
                    except (BrokenPipeError, OSError): pass

                if (s["ffmpeg"].poll() is not None and not self._restarting):
                    _, msg = stop_master(s)
                    self.master_session = None
                    self._release_embed()
                    self.var_timer.set("")
                    self._update_buttons()
                    self._set_status(f"Cerrado · {msg}" if msg else "Cerrado")
            else:
                self.var_timer.set("")
            self.after(500, self._poll)

        def _on_close(self) -> None:
            try: self._save_geometry()
            except Exception: pass
            if self.master_session:
                try: stop_master(self.master_session)
                except Exception: pass
            self.destroy()

    App(cfg).mainloop()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Cliente para tarjeta capturadora. GUI por defecto.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("gui",        help="GUI (default).")
    sub.add_parser("console",    help="Menu de consola.")
    sub.add_parser("preview",    help="Vista previa con audio.")
    sp = sub.add_parser("screenshot", help="Captura unica.")
    sp.add_argument("--no-clipboard", action="store_true")
    sp.add_argument("--no-file", action="store_true")
    sr = sub.add_parser("record", help="Grabar video + audio.")
    sr.add_argument("--no-preview", action="store_true")
    sr.add_argument("--no-audio-live", action="store_true")
    sub.add_parser("setup",      help="Re-elegir dispositivos.")
    sub.add_parser("settings",   help="Editar configuracion (consola).")
    sub.add_parser("devices",    help="Listar dispositivos DirectShow.")
    si = sub.add_parser("install", help="Verificar binarios locales + libs Python.")
    si.add_argument("--auto", action="store_true")
    sub.add_parser("shortcut",   help="Crear acceso directo en Escritorio.")
    bp = sub.add_parser("build",  help=f"Generar {APP_ID}.exe via PyInstaller.")
    bp.add_argument("--onedir", action="store_true",
                     help="Build en modo carpeta (startup ~instant). Default: --onefile.")
    args = parser.parse_args(argv)

    # Comandos que no requieren ffmpeg disponible
    if args.cmd == "install":
        return install_console(interactive=not args.auto)
    if args.cmd == "shortcut":
        ok, info = make_shortcut()
        print(("Acceso directo creado: " if ok else "Error: ") + info)
        return 0 if ok else 1
    if args.cmd == "build":
        return build_exe(onedir=getattr(args, "onedir", False))

    # Para los demas: si no hay ffmpeg en CLI, ofrecer auto-instalar; en GUI lo hace el bootstrap
    if args.cmd in (None, "gui"):
        cfg = load_config()
        run_gui(cfg)
        return 0

    if not check_tools(quiet=True):
        # Intenta resolver via binarios locales (sin descarga)
        if not install_ffmpeg():
            return 2

    if args.cmd == "devices":
        v, a = list_dshow_devices()
        print("Video:");   [print(f"  - {n}") for n in v]
        print("Audio:");   [print(f"  - {n}") for n in a]
        return 0

    cfg = load_config()
    if not cfg.get("video_device") or args.cmd == "setup":
        cfg = pick_devices_console(cfg)

    if args.cmd == "console":
        console_menu(cfg);             return 0
    if args.cmd == "preview":
        p = start_preview(cfg); p.wait(); return 0
    if args.cmd == "screenshot":
        _, msg = take_screenshot(cfg,
                                  to_clipboard=not args.no_clipboard,
                                  to_file=not args.no_file)
        print(msg);                    return 0
    if args.cmd == "record":
        s = start_record(cfg,
                          with_preview=not args.no_preview,
                          audio_passthrough=not args.no_audio_live)
        print("Grabando. ENTER para detener.")
        try: input()
        except (EOFError, KeyboardInterrupt): pass
        _, msg = stop_record(s)
        print(f"Detenido: {msg}");     return 0
    if args.cmd == "settings":
        settings_console(cfg);         return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print()
        sys.exit(130)
