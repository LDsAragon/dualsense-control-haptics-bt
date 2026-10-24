#!/usr/bin/env python3
"""
dshaptics — háptica (motores de bobina) del DualSense por Bluetooth en Windows.

Basado en la investigación de SAxense (egormanga, https://apps.sdore.me/SAxense)
y en dualsense-bt-haptics (awalol).

Modos:
  list       lista joysticks DualSense y dispositivos de audio
  loopback   lo que suena en la PC  -> motores, en tiempo real
  file       reproduce un archivo de audio en los motores
  fx         efectos sintetizados (tono, pulsos, latido, barrido, rumble, ping-pong)
"""

import argparse
import os
import json
import ctypes
import sys
import threading
import time
import zlib
from collections import deque

import numpy as np

# ---------------------------------------------------------------------------
# Protocolo (ver SAxense.c)
# ---------------------------------------------------------------------------

__version__ = "0.0.1"

# ---------------------------------------------------------------------------
# Rutas: en desarrollo, todo vive en la carpeta del proyecto; empaquetado como
# DualSenseControl.exe, los recursos vienen adentro del exe (solo lectura) y los
# datos del usuario van a %LOCALAPPDATA%\DualSenseControl.
# ---------------------------------------------------------------------------
FROZEN = bool(getattr(sys, "frozen", False))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_dir():
    return getattr(sys, "_MEIPASS", REPO_ROOT)


def data_dir():
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "DualSenseControl")
    return REPO_ROOT


VID_SONY = 0x054C
PIDS = {0x0CE6: "DualSense", 0x0DF2: "DualSense Edge"}

REPORT_ID = 0x32
REPORT_LEN = 142           # 1 (ID) + 137 (payload) + 4 (CRC)
SAMPLE_RATE = 3000         # Hz, por canal
FRAMES = 32                # 32 frames estéreo = 64 bytes por reporte
PERIOD = FRAMES / SAMPLE_RATE   # ~10,667 ms

BT_HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"


def build_report(samples: bytes, seq: int, counter: int) -> bytes:
    """Arma un reporte 0x32 con 64 bytes de muestras s8 intercaladas (L,R,L,R...)."""
    assert len(samples) == FRAMES * 2
    r = bytearray(REPORT_LEN)
    r[0] = REPORT_ID
    r[1] = (seq & 0x0F) << 4                       # tag=0, seq en el nibble alto
    # Paquete 0x11 (control): cabecera = pid | sized<<7
    r[2] = 0x80 | 0x11
    r[3] = 7
    r[4:11] = bytes((0xFE, 0, 0, 0, 0, 0xFF, counter & 0xFF))
    # Paquete 0x12 (audio háptico)
    r[11] = 0x80 | 0x12
    r[12] = FRAMES * 2
    r[13:13 + FRAMES * 2] = samples
    # CRC32 sobre 0xA2 (cabecera BT de salida) + ID + payload
    crc = zlib.crc32(b"\xA2" + bytes(r[:REPORT_LEN - 4])) & 0xFFFFFFFF
    r[REPORT_LEN - 4:] = crc.to_bytes(4, "little")
    return bytes(r)


def to_s8(stereo: np.ndarray, gain: float) -> np.ndarray:
    """float [-1,1] (N,2) -> int8 (N,2) con ganancia y recorte."""
    return np.clip(np.round(stereo * gain * 127.0), -128, 127).astype(np.int8)


# ---------------------------------------------------------------------------
# Dispositivo HID
# ---------------------------------------------------------------------------

def find_controllers():
    import hid
    found = []
    for pid, name in PIDS.items():
        for d in hid.enumerate(VID_SONY, pid):
            path = d["path"]
            path_s = path.decode(errors="ignore") if isinstance(path, bytes) else str(path)
            bt = d.get("bus_type") == 2 or BT_HID_UUID in path_s.lower()
            found.append({"name": name, "path": path, "bt": bt,
                          "serial": d.get("serial_number") or ""})
    return found


class Controller:
    def __init__(self, index=0, allow_usb=False):
        import hid
        ctrls = find_controllers()
        if not ctrls:
            sys.exit("No encontré ningún DualSense. ¿Está emparejado y conectado por Bluetooth?")
        bt = [c for c in ctrls if c["bt"]]
        pool = bt if bt else (ctrls if allow_usb else [])
        if not pool:
            sys.exit("El DualSense está conectado por USB. Por cable la háptica ya funciona como "
                     "placa de sonido; esta herramienta es para Bluetooth (usá --allow-usb para forzar).")
        if index >= len(pool):
            sys.exit(f"Índice {index} fuera de rango: hay {len(pool)} joystick(s).")
        c = pool[index]
        self.bt = c["bt"]
        self.dev = hid.device()
        self.dev.open_path(c["path"])
        print(f"Conectado: {c['name']} {'(Bluetooth)' if c['bt'] else '(USB)'} {c['serial']}")
        # Leer el feature report 0x05 (calibración) pasa el joystick al modo
        # de reportes completos por Bluetooth (lo mismo que hace el driver de Linux).
        try:
            self.dev.get_feature_report(0x05, 41)
        except Exception:
            pass

    def write(self, data: bytes) -> bool:
        return self.dev.write(data) > 0

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass


class DryRun:
    """Joystick falso: no abre nada, opcionalmente guarda los reportes en un archivo."""

    def __init__(self, dump=None):
        self.f = open(dump, "wb") if dump else None
        print("Modo prueba: no se envía nada al joystick.")

    def write(self, data):
        if self.f:
            self.f.write(data)
        return True

    def close(self):
        if self.f:
            self.f.close()


# ---------------------------------------------------------------------------
# Buffer y envío temporizado
# ---------------------------------------------------------------------------

class Fifo:
    """Cola de frames estéreo con tope (en frames). dtype int8 para Bluetooth, float32 para audio."""

    def __init__(self, max_frames, drop_old, dtype=np.int8):
        self.dtype = dtype
        self.max = max(FRAMES * 2, max_frames)
        self.drop_old = drop_old        # True en vivo (latencia baja), False en archivo/fx
        self.buf = deque()
        self.n = 0
        self.cv = threading.Condition()
        self.closed = False
        self.underruns = 0
        # En vivo: no empezar a sacar audio hasta tener la mitad del buffer (absorbe jitter).
        self.prefill = self.max // 2 if drop_old else 0
        self.starved = drop_old

    def push(self, frames: np.ndarray):
        with self.cv:
            if self.drop_old:
                self.buf.append(frames)
                self.n += len(frames)
                while self.n > self.max and self.buf:
                    old = self.buf.popleft()
                    self.n -= len(old)
            else:
                while self.n >= self.max and not self.closed:
                    self.cv.wait(0.1)
                self.buf.append(frames)
                self.n += len(frames)

    def pop(self, k) -> np.ndarray:
        out = np.zeros((k, 2), self.dtype)
        got = 0
        with self.cv:
            if self.starved:
                if self.n < self.prefill:
                    return out              # silencio mientras se llena
                self.starved = False
            while got < k and self.buf:
                head = self.buf[0]
                take = min(k - got, len(head))
                out[got:got + take] = head[:take]
                got += take
                if take == len(head):
                    self.buf.popleft()
                else:
                    self.buf[0] = head[take:]
            self.n -= got
            self.cv.notify_all()
        if got < k:
            self.underruns += 1
            if self.prefill:
                self.starved = True
        return out

    def drained(self):
        with self.cv:
            return self.n == 0


class Sender(threading.Thread):
    """Manda un reporte cada ~10,67 ms con temporización precisa."""

    def __init__(self, dev, fifo, verbose=False):
        super().__init__(daemon=True)
        self.dev, self.fifo, self.verbose = dev, fifo, verbose
        self.stop_evt = threading.Event()
        self.sent = 0
        self.errors = 0
        self.late = 0

    def run(self):
        winmm = None
        if sys.platform == "win32":
            winmm = ctypes.WinDLL("winmm")
            winmm.timeBeginPeriod(1)    # sleep con resolución de 1 ms
        seq = counter = 0
        nxt = time.perf_counter()
        try:
            while not self.stop_evt.is_set():
                frames = self.fifo.pop(FRAMES)
                if not self.dev.write(build_report(frames.tobytes(), seq, counter)):
                    self.errors += 1
                    if self.errors in (1, 10, 100):
                        print(f"[aviso] falló la escritura HID ({self.errors} veces)")
                seq = (seq + 1) & 0x0F
                counter = (counter + 1) & 0xFF
                self.sent += 1
                nxt += PERIOD
                now = time.perf_counter()
                if now >= nxt:
                    # Llegamos tarde a uno o más turnos: se saltean, NUNCA se mandan
                    # reportes pegados para "ponerse al día". El buffer del joystick es
                    # chico y las ráfagas producen cortes (awalol/dualsense-bt-haptics#3).
                    missed = int((now - nxt) / PERIOD) + 1
                    self.late += missed
                    nxt += missed * PERIOD
                wait = nxt - now - 0.0015
                if wait > 0:
                    time.sleep(wait)
                while time.perf_counter() < nxt:   # espera activa los últimos ~1,5 ms
                    pass
        finally:
            silence = bytes(FRAMES * 2)
            for _ in range(3):
                self.dev.write(build_report(silence, seq, counter))
                seq, counter = (seq + 1) & 0x0F, (counter + 1) & 0xFF
            if winmm:
                winmm.timeEndPeriod(1)

    def stop(self):
        self.stop_evt.set()
        self.join(1.0)


# ---------------------------------------------------------------------------
# Procesamiento de audio
# ---------------------------------------------------------------------------

class StreamResampler:
    """Remuestreo en streaming (por defecto a 3 kHz): filtro con estado + interpolación lineal.
    El filtro corta en 1,35 kHz (o en lowpass_hz si es menor): más arriba los motores no responden."""

    def __init__(self, in_rate, lowpass_hz=None, out_rate=SAMPLE_RATE):
        from scipy.signal import butter, sosfilt_zi
        self.step = in_rate / out_rate
        cutoff = min(1350.0, lowpass_hz or 1350.0)
        self.sos = butter(8, cutoff, "low", fs=in_rate, output="sos")
        zi = sosfilt_zi(self.sos)
        self.zi = np.stack([zi, zi], axis=-1) * 0.0    # (secciones, 2, canales)
        self.pos = 0.0
        self.tail = np.zeros((0, 2), np.float32)

    def process(self, x: np.ndarray) -> np.ndarray:
        from scipy.signal import sosfilt
        y, self.zi = sosfilt(self.sos, x, axis=0, zi=self.zi)
        y = np.concatenate([self.tail, y.astype(np.float32)])
        n = len(y)
        if n < 2:
            self.tail = y
            return np.zeros((0, 2), np.float32)
        idx = np.arange(self.pos, n - 1, self.step)
        i0 = idx.astype(np.int64)
        frac = (idx - i0)[:, None]
        out = y[i0] * (1 - frac) + y[i0 + 1] * frac
        last = (idx[-1] + self.step) if len(idx) else self.pos
        keep = min(int(last), n)      # posición del próximo frame, relativa al inicio de la cola
        self.pos = last - keep
        self.tail = y[keep:]
        return out


def pick_channels(x: np.ndarray, chans) -> np.ndarray:
    """(N,C) -> (N,2). chans: lista 1-indexada de 1 o 2 canales; None = automático."""
    c = x.shape[1]
    if chans is None:
        if c == 1:
            return np.repeat(x, 2, axis=1)
        return x[:, :2]
    idx = [k - 1 for k in chans]
    if any(i < 0 or i >= c for i in idx):
        sys.exit(f"Canales {chans} fuera de rango: la fuente tiene {c} canal(es).")
    if len(idx) == 1:
        idx = idx * 2
    return x[:, idx[:2]]


def parse_channels(s):
    if not s:
        return None
    return [int(p) for p in s.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Apagar el joystick (Windows): cortar el enlace Bluetooth desde la PC.
# El DualSense se apaga solo cuando el host lo desconecta (igual que DS4Windows).
# ---------------------------------------------------------------------------

IOCTL_BTH_DISCONNECT_DEVICE = 0x41000C


def _bt_structs():
    c = ctypes

    class SYSTEMTIME(c.Structure):
        _fields_ = [(n, c.c_uint16) for n in
                    ("wYear", "wMonth", "wDayOfWeek", "wDay", "wHour", "wMinute", "wSecond", "wMs")]

    class FIND_RADIO_PARAMS(c.Structure):
        _fields_ = [("dwSize", c.c_uint32)]

    class SEARCH_PARAMS(c.Structure):
        _fields_ = [("dwSize", c.c_uint32), ("fReturnAuthenticated", c.c_int32),
                    ("fReturnRemembered", c.c_int32), ("fReturnUnknown", c.c_int32),
                    ("fReturnConnected", c.c_int32), ("fIssueInquiry", c.c_int32),
                    ("cTimeoutMultiplier", c.c_uint8), ("hRadio", c.c_void_p)]

    class DEVICE_INFO(c.Structure):
        _fields_ = [("dwSize", c.c_uint32), ("Address", c.c_uint64), ("ulClassofDevice", c.c_uint32),
                    ("fConnected", c.c_int32), ("fRemembered", c.c_int32), ("fAuthenticated", c.c_int32),
                    ("stLastSeen", SYSTEMTIME), ("stLastUsed", SYSTEMTIME),
                    ("szName", c.c_wchar * 248 if c.sizeof(c.c_wchar) == 2 else c.c_uint16 * 248)]

    return FIND_RADIO_PARAMS, SEARCH_PARAMS, DEVICE_INFO


def _bt_radios():
    """Handles de todos los adaptadores Bluetooth."""
    FIND_RADIO_PARAMS, _, _ = _bt_structs()
    bt = ctypes.WinDLL("bthprops.cpl")
    bt.BluetoothFindFirstRadio.restype = ctypes.c_void_p
    p = FIND_RADIO_PARAMS(ctypes.sizeof(FIND_RADIO_PARAMS))
    h = ctypes.c_void_p()
    find = bt.BluetoothFindFirstRadio(ctypes.byref(p), ctypes.byref(h))
    radios = []
    if find:
        radios.append(h.value)
        while True:
            h2 = ctypes.c_void_p()
            if not bt.BluetoothFindNextRadio(ctypes.c_void_p(find), ctypes.byref(h2)):
                break
            radios.append(h2.value)
        bt.BluetoothFindRadioClose(ctypes.c_void_p(find))
    return radios


def connected_dualsenses():
    """[(dirección 'aa:bb:..', nombre)] de los DualSense conectados por Bluetooth ahora."""
    _, SEARCH_PARAMS, DEVICE_INFO = _bt_structs()
    bt = ctypes.WinDLL("bthprops.cpl")
    k32 = ctypes.WinDLL("kernel32")
    bt.BluetoothFindFirstDevice.restype = ctypes.c_void_p
    found = {}
    for radio in _bt_radios():
        sp = SEARCH_PARAMS(ctypes.sizeof(SEARCH_PARAMS), 1, 1, 0, 1, 0, 0, radio)
        info = DEVICE_INFO()
        info.dwSize = ctypes.sizeof(DEVICE_INFO)
        find = bt.BluetoothFindFirstDevice(ctypes.byref(sp), ctypes.byref(info))
        while find:
            name = info.szName if isinstance(info.szName, str) else ""
            low = name.lower()
            if info.fConnected and ("dualsense" in low or "wireless controller" in low):
                addr = ":".join(f"{(info.Address >> (8 * i)) & 0xFF:02x}" for i in range(5, -1, -1))
                found[addr] = name
            info = DEVICE_INFO()
            info.dwSize = ctypes.sizeof(DEVICE_INFO)
            if not bt.BluetoothFindNextDevice(ctypes.c_void_p(find), ctypes.byref(info)):
                bt.BluetoothFindDeviceClose(ctypes.c_void_p(find))
                break
        k32.CloseHandle(ctypes.c_void_p(radio))
    return sorted(found.items())


def power_off(address):
    """Desconecta (y así apaga) el joystick con esa dirección. Devuelve True si algún adaptador lo hizo."""
    addr = ctypes.c_uint64(int(address.replace(":", "").replace("-", ""), 16))
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                    ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
                                    ctypes.c_void_p]
    ok, last_err = False, 0
    for radio in _bt_radios():
        ret = ctypes.c_uint32()
        if k32.DeviceIoControl(ctypes.c_void_p(radio), IOCTL_BTH_DISCONNECT_DEVICE,
                               ctypes.byref(addr), 8, None, 0, ctypes.byref(ret), None):
            ok = True
        else:
            last_err = ctypes.get_last_error()
        k32.CloseHandle(ctypes.c_void_p(radio))
    if not ok and last_err:
        raise OSError(last_err, f"Windows no pudo desconectar {address} (error {last_err})")
    return ok


# ---------------------------------------------------------------------------
# Gatillos adaptativos
# Efectos "oficiales" del DualSense (codificación de la investigación de Nielk1,
# la misma que usan DSX/DualSenseY). 11 bytes por gatillo; zonas 0-9 del recorrido.
# ---------------------------------------------------------------------------

def trigger_off():
    return bytes([0x05] + [0] * 10)


def trigger_feedback(position=0, strength=8):
    """Resistencia continua desde 'position' (0-9) con fuerza 1-8."""
    force, active = 0, 0
    for i in range(position, 10):
        force |= ((strength - 1) & 7) << (3 * i)
        active |= 1 << i
    return bytes([0x21, active & 0xFF, active >> 8, force & 0xFF, (force >> 8) & 0xFF,
                  (force >> 16) & 0xFF, (force >> 24) & 0xFF, 0, 0, 0, 0])


def trigger_weapon(start=2, end=6, strength=8):
    """Gatillo de arma: resistencia entre start (2-7) y end, y un 'clic' al pasarla."""
    zones = (1 << start) | (1 << end)
    return bytes([0x25, zones & 0xFF, zones >> 8, (strength - 1) & 7, 0, 0, 0, 0, 0, 0, 0])


def trigger_vibration(position=0, amplitude=8, frequency=40):
    """Vibración del gatillo desde 'position' (0-9), amplitud 1-8, frecuencia en Hz (1-255)."""
    amp, active = 0, 0
    for i in range(position, 10):
        amp |= ((amplitude - 1) & 7) << (3 * i)
        active |= 1 << i
    return bytes([0x26, active & 0xFF, active >> 8, amp & 0xFF, (amp >> 8) & 0xFF,
                  (amp >> 16) & 0xFF, (amp >> 24) & 0xFF, 0, 0, frequency & 0xFF, 0])


TRIGGER_EFFECTS = {
    "duro": trigger_feedback,
    "arma": trigger_weapon,
    "vibracion": trigger_vibration,
    "off": trigger_off,
}


def trigger_state(right=None, left=None):
    """Los 47 bytes de 'set state' con solo los gatillos habilitados."""
    st = bytearray(47)
    if right is not None:
        st[0] |= 0x04                       # allow_right_trigger_ffb
        st[10:21] = right
    if left is not None:
        st[0] |= 0x08                       # allow_left_trigger_ffb
        st[21:32] = left
    return bytes(st)


def trigger_report(state: bytes, bluetooth: bool, seq: int = 0) -> bytes:
    if not bluetooth:                       # USB (o el joystick virtual de vDS): reporte 0x02
        return bytes([0x02]) + state
    r = bytearray(78)                       # Bluetooth: reporte 0x31 con CRC
    r[0], r[1], r[2] = 0x31, (seq & 0x0F) << 4, 0x10
    r[3:3 + len(state)] = state
    crc = zlib.crc32(b"\xA2" + bytes(r[:74])) & 0xFFFFFFFF
    r[74:] = crc.to_bytes(4, "little")
    return bytes(r)


def set_triggers(effect, side="ambos", index=0):
    """Aplica un efecto. Con vDS en marcha va por el joystick virtual USB (como un juego)."""
    data = TRIGGER_EFFECTS[effect]()
    state = trigger_state(right=data if side in ("ambos", "derecho") else None,
                          left=data if side in ("ambos", "izquierdo") else None)
    dev = Controller(index, allow_usb=True)
    try:
        ok = dev.write(trigger_report(state, dev.bt))
    finally:
        dev.close()
    if not ok:
        raise OSError("Windows no aceptó el reporte de salida")
    return "Bluetooth directo" if dev.bt else "joystick virtual (vDS)"


def cmd_gatillos(args):
    via = set_triggers(args.efecto, args.lado, args.index)
    print(f"Gatillos: {args.efecto} ({args.lado}) por {via}.")
    if args.efecto != "off" and args.segundos > 0:
        print(f"Apretá los gatillos. Se apagan en {args.segundos:g} s...")
        try:
            time.sleep(args.segundos)
        except KeyboardInterrupt:
            pass
        set_triggers("off", args.lado, args.index)
        print("Gatillos apagados.")


# ---------------------------------------------------------------------------
# Identificar joysticks, barra de luz y LEDs de jugador
# ---------------------------------------------------------------------------

CONFIG_PATH = os.path.join(data_dir(), "config", "joysticks.json")
# Patrones de los 5 LEDs blancos, iguales a los de la PS5 (bit 0 = el de la izquierda)
PLAYER_PATTERNS = {0: 0x00, 1: 0x04, 2: 0x0A, 3: 0x15, 4: 0x1B, 5: 0x1F}
DEFAULT_COLOR = (0, 0, 255)


def output_report(state: bytes, bluetooth: bool, seq: int = 0) -> bytes:
    """Reporte de salida con 47 bytes de 'set state': 0x02 por USB/virtual, 0x31 + CRC por Bluetooth."""
    return trigger_report(state, bluetooth, seq)


def light_state(rgb=None, player=None):
    st = bytearray(47)
    if rgb is not None:
        st[1] |= 0x04                       # allow_led_color
        st[44:47] = bytes(rgb)
    if player is not None:
        st[1] |= 0x10                       # allow_player_indicators
        st[43] = PLAYER_PATTERNS.get(int(player), 0)
    return bytes(st)


def mac_from_pairing(report) -> str:
    """Reporte de característica 0x09: bytes 1-6 = dirección Bluetooth al revés."""
    r = bytes(report or b"")
    if len(r) >= 7 and r[0] == 0x09:
        return ":".join(f"{b:02x}" for b in reversed(r[1:7]))
    return ""


_mac_cache = {}


def list_pads():
    """Todos los DualSense que ve Windows, con su dirección real.
    En modo vDS son los joysticks virtuales; la dirección se pide con el reporte 0x09,
    que vDS reenvía al joystick Bluetooth de verdad."""
    import hid
    pads = []
    for c in find_controllers():
        key = c["path"]
        mac = _mac_cache.get(key, "")
        ser = (c.get("serial") or "").replace(":", "").lower()
        if not mac and len(ser) == 12 and all(ch in "0123456789abcdef" for ch in ser):
            mac = ":".join(ser[i:i + 2] for i in range(0, 12, 2))
        if not mac:
            try:
                d = hid.device()
                d.open_path(c["path"])
                try:
                    mac = mac_from_pairing(d.get_feature_report(0x09, 64))
                finally:
                    d.close()
            except Exception:
                mac = ""
        if mac:
            _mac_cache[key] = mac
        pads.append({"mac": mac, "path": c["path"], "bt": c["bt"], "model": c["name"],
                     "via": "Bluetooth" if c["bt"] else "USB / virtual (vDS)"})
    return pads


def send_state(pad, state: bytes):
    import hid
    d = hid.device()
    d.open_path(pad["path"])
    try:
        if pad["bt"]:
            try:
                d.get_feature_report(0x05, 41)      # modo de reportes completos
            except Exception:
                pass
        if d.write(output_report(state, pad["bt"])) <= 0:
            raise OSError("Windows no aceptó el reporte de salida")
    finally:
        d.close()


def find_pad(mac):
    mac = (mac or "").lower()
    for p in list_pads():
        if not mac or p["mac"] == mac:
            return p
    raise OSError(f"No encontré el joystick {mac or ''}".strip())


def parse_color(text):
    t = text.strip().lstrip("#")
    if len(t) != 6:
        raise ValueError(f"Color inválido: {text} (usá #RRGGBB)")
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def set_lights(mac, rgb=None, player=None):
    pad = find_pad(mac)
    send_state(pad, light_state(rgb, player))
    return pad


def identify(mac, seconds=2.0):
    """Hace parpadear la barra (blanco/apagado) y vuelve al color guardado."""
    pad = find_pad(mac)
    saved = load_config().get(pad["mac"], {})
    end = time.time() + seconds
    on = True
    while time.time() < end:
        send_state(pad, light_state((255, 255, 255) if on else (0, 0, 0)))
        on = not on
        time.sleep(0.2)
    color = parse_color(saved["color"]) if saved.get("color") else DEFAULT_COLOR
    send_state(pad, light_state(color, saved.get("player")))
    return pad


def cmd_luces(args):
    cfg = load_config()
    pads = list_pads()
    if not pads:
        print("No hay ningún DualSense conectado.")
        return
    for i, p in enumerate(pads):
        c = cfg.get(p["mac"], {})
        print(f"  {i}) {c.get('name') or p['model']:20s} {p['mac'] or '¿?':17s}  {p['via']:22s}"
              f"  color {c.get('color', '-'):8s} jugador {c.get('player', '-')}")


def cmd_color(args):
    if args.mac.startswith("#") and not args.color:      # "color #ff0000" sin dirección
        args.color, args.mac = args.mac, ""
    rgb = parse_color(args.color) if args.color else None
    pad = set_lights(args.mac, rgb, args.jugador)
    cfg = load_config()
    entry = cfg.setdefault(pad["mac"], {})
    if args.color:
        entry["color"] = "#%02x%02x%02x" % rgb
    if args.jugador is not None:
        entry["player"] = args.jugador
    if args.nombre:
        entry["name"] = args.nombre
    save_config(cfg)
    print(f"Listo: {entry.get('name') or pad['mac']} -> {entry}")


def cmd_identificar(args):
    pad = identify(args.mac)
    print(f"Parpadeó: {pad['mac']} ({pad['via']})")


def cmd_restablecer(args):
    """Deja el joystick como de fábrica en lo que tocamos: gatillos sin efecto."""
    via = set_triggers("off", "ambos", args.index)
    print(f"Joystick restablecido (gatillos sin efecto) por {via}.")


def decode_battery(report: bytes):
    """Batería desde un reporte de entrada completo: 0x31 (Bluetooth) o 0x01 de 64 bytes (USB).
    Devuelve (porcentaje, estado) o None."""
    if len(report) >= 55 and report[0] == 0x31:
        b = report[54]
    elif len(report) >= 54 and report[0] == 0x01:
        b = report[53]
    else:
        return None
    level = min(100, (b & 0x0F) * 10 + 5)
    state = {0: "descargando", 1: "cargando", 2: "carga completa"}.get(b >> 4, f"estado 0x{b >> 4:x}")
    return level, state


def cmd_bateria(args):
    dev = Controller(args.index, args.allow_usb)
    try:
        t0 = time.time()
        while time.time() - t0 < 2.0:
            r = dev.dev.read(128, 100)
            info = decode_battery(bytes(r)) if r else None
            if info:
                level, state = info
                print(f"Batería: ~{level} % ({state})")
                if level <= 25 and state == "descargando":
                    print("Batería baja: el DualSense se puede cortar al activar la luz o la vibración.")
                return
        sys.exit("No llegó ningún reporte de entrada completo (¿lo tiene tomado otro programa?).")
    finally:
        dev.close()


def cmd_apagar(args):
    if sys.platform != "win32":
        sys.exit("Apagar el joystick solo está implementado en Windows.")
    pads = connected_dualsenses()
    if args.address:
        pads = [(args.address.lower(), "")]
    if not pads:
        print("No hay ningún DualSense conectado por Bluetooth.")
        return
    failed = False
    for addr, name in pads:
        try:
            power_off(addr)
            print(f"Apagado: {name or 'DualSense'} {addr}")
        except OSError as e:
            failed = True
            print(f"No pude apagar {addr}: {e}")
    if failed:
        sys.exit(5)


# ---------------------------------------------------------------------------
# Modos
# ---------------------------------------------------------------------------

def cmd_diag(args):
    """Lista todo lo que hidapi ve, para entender por qué no aparece el joystick."""
    import platform
    print(f"Python {platform.python_version()} ({platform.architecture()[0]}), {platform.platform()}")
    try:
        import hid
    except ImportError as e:
        sys.exit(f"No se pudo importar hidapi: {e}")
    print(f"hidapi: {getattr(hid, '__file__', '?')}")
    devs = hid.enumerate()
    print(f"Dispositivos HID totales: {len(devs)}\n")
    usages = {(1, 4): "joystick", (1, 5): "gamepad", (1, 2): "mouse", (1, 6): "teclado"}
    shown = 0
    for d in devs:
        vid, pid = d.get("vendor_id", 0), d.get("product_id", 0)
        up, u = d.get("usage_page", 0), d.get("usage", 0)
        kind = usages.get((up, u), "")
        sony = vid == VID_SONY
        if not (sony or kind in ("joystick", "gamepad") or up >= 0xFF00 and vid not in (0, 0x046D)):
            continue
        path = d["path"].decode(errors="ignore") if isinstance(d["path"], bytes) else str(d["path"])
        bt = d.get("bus_type") == 2 or BT_HID_UUID in path.lower()
        print(f"{'>>' if sony else '  '} {vid:04X}:{pid:04X}  usage {up:04X}:{u:04X} {kind:8s} "
              f"{'BT ' if bt else '   '} {d.get('manufacturer_string') or ''} / {d.get('product_string') or ''}")
        print(f"     {path}")
        shown += 1
    if not shown:
        print("No hay ningún joystick/gamepad ni dispositivo de Sony visible por HID.")
    if not any(d.get("vendor_id") == VID_SONY for d in devs):
        print("\nNingún dispositivo con el ID de Sony (054C). Causas típicas:\n"
              "  - HidHide (viene con DS4Windows/DSX) está ocultando el joystick a otros programas.\n"
              "  - Está emparejado pero no conectado (la luz debe quedar fija, no apagada).\n"
              "  - Lo tiene tomado en exclusiva otro programa (DSX, DS4Windows).")


def cmd_list(args):
    print("Joysticks:")
    try:
        ctrls = find_controllers()
    except ImportError:
        ctrls = None
        print("  (falta el paquete 'hidapi': pip install hidapi)")
    if ctrls is not None:
        if not ctrls:
            print("  ninguno  (corré 'python dshaptics.py diag' para ver por qué)")
        for c in ctrls:
            print(f"  - {c['name']}  {'Bluetooth' if c['bt'] else 'USB'}  {c['serial']}")
    print("\nSalidas de audio (para --device en loopback):")
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        print("  (falta 'PyAudioWPatch', solo Windows: pip install PyAudioWPatch)")
        return
    p = pyaudio.PyAudio()
    try:
        for d in p.get_loopback_device_info_generator():
            print(f"  - {d['name'].replace(' [Loopback]', '')}  "
                  f"({d['maxInputChannels']} canales, {int(d['defaultSampleRate'])} Hz)")
    finally:
        p.terminate()


def open_output(args):
    return DryRun(args.dump) if args.dry_run else Controller(args.index, args.allow_usb)


def run_session(args, producer, live):
    """Arranca el envío y el productor; corta con Ctrl+C."""
    dev = open_output(args)
    fifo = Fifo(int(args.buffer / 1000 * SAMPLE_RATE), drop_old=live)
    sender = Sender(dev, fifo, args.verbose)
    sender.start()
    done = threading.Event()

    def prod():
        try:
            producer(fifo)
        finally:
            done.set()

    threading.Thread(target=prod, daemon=True).start()
    t0 = time.perf_counter()
    try:
        while not done.is_set():
            time.sleep(0.25)
            if args.verbose:
                el = time.perf_counter() - t0
                print(f"\r{el:6.1f}s  reportes={sender.sent}  ({sender.sent / max(el, 1e-9):5.1f}/s)  "
                      f"buffer={fifo.n * 1000 // SAMPLE_RATE:4d}ms  vacíos={fifo.underruns}  "
                      f"errores={sender.errors}  saltados={sender.late}", end="", flush=True)
        while not fifo.drained():
            time.sleep(0.02)
        time.sleep(PERIOD * 2)
    except KeyboardInterrupt:
        pass
    finally:
        fifo.closed = True
        sender.stop()
        dev.close()
        if args.verbose:
            print()
        print(f"Listo: {sender.sent} reportes enviados, {sender.errors} errores.")


def cmd_loopback(args):
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        sys.exit("El modo loopback necesita Windows y PyAudioWPatch: pip install PyAudioWPatch")
    chans = parse_channels(args.channels)
    p = pyaudio.PyAudio()
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    target = args.device or p.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
    loop = None
    for d in p.get_loopback_device_info_generator():
        if target.lower() in d["name"].lower():
            loop = d
            break
    if loop is None:
        p.terminate()
        sys.exit(f"No encontré la salida '{target}'. Mirá las disponibles con: dshaptics list")
    rate = int(loop["defaultSampleRate"])
    max_ch = loop["maxInputChannels"]
    st = {"fifo": None, "nch": max_ch, "dtype": np.float32, "rs": None}

    def cb(in_data, frame_count, time_info, status):
        fifo = st["fifo"]
        if fifo is not None:
            x = np.frombuffer(in_data, st["dtype"]).reshape(-1, st["nch"])
            if st["dtype"] is np.int16:
                x = x.astype(np.float32) / 32768.0
            y = st["rs"].process(pick_channels(x, chans))
            if len(y):
                fifo.push(to_s8(y, args.gain))
        return (None, pyaudio.paContinue)

    # WASAPI rechaza algunas combinaciones según el dispositivo/driver:
    # probamos formato, cantidad de canales y tamaño de bloque hasta que una abra.
    ch_options = [max_ch] + ([2] if max_ch != 2 else [])
    attempts = [(fmt, dt, ch, fpb)
                for ch in ch_options
                for fmt, dt in ((pyaudio.paFloat32, np.float32), (pyaudio.paInt16, np.int16))
                for fpb in (max(64, rate // 200), 1024, pyaudio.paFramesPerBufferUnspecified)]
    stream, last_err = None, None
    for fmt, dt, ch, fpb in attempts:
        st["nch"], st["dtype"] = ch, dt
        try:
            stream = p.open(format=fmt, channels=ch, rate=rate, input=True,
                            input_device_index=loop["index"],
                            frames_per_buffer=fpb, stream_callback=cb)
            break
        except OSError as e:
            last_err = e
            if args.verbose:
                print(f"  no abrió con {ch} canales, {'float32' if dt is np.float32 else 'int16'}, "
                      f"bloque {fpb}: {e}")
    if stream is None:
        p.terminate()
        sys.exit(f"No pude abrir la captura de '{loop['name']}': {last_err}\n"
                 "Probá: poner ese dispositivo en estéreo (2 canales) en el panel de sonido de "
                 "Windows, desactivar el sonido envolvente virtual (G HUB) o usar otra salida.")
    nch = st["nch"]
    print(f"Capturando: {loop['name']} ({nch} canales, {rate} Hz, "
          f"{'float32' if st['dtype'] is np.float32 else 'int16'})")
    if chans and max(chans) > nch:
        stream.close()
        p.terminate()
        sys.exit(f"Pediste los canales {chans}, pero la captura abrió con {nch}.")
    st["rs"] = StreamResampler(rate, args.lowpass)

    def producer(fifo):
        st["fifo"] = fifo
        print("Enviando a los motores. Ctrl+C para salir.")
        try:
            while stream.is_active():
                time.sleep(0.1)
        finally:
            stream.close()
            p.terminate()

    run_session(args, producer, live=True)


def load_audio(path):
    import soundfile as sf
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
    except Exception as e:
        sys.exit(f"No pude leer '{path}': {e}")
    return data, sr


def prepare_file(path, chans, lowpass):
    from fractions import Fraction
    from scipy.signal import resample_poly, butter, sosfiltfilt
    data, sr = load_audio(path)
    x = pick_channels(data, chans)
    # anti-alias fuerte antes de bajar a 3 kHz (Nyquist = 1,5 kHz)
    x = sosfiltfilt(butter(8, 1350, "low", fs=sr, output="sos"), x, axis=0)
    fr = Fraction(SAMPLE_RATE, int(sr)).limit_denominator(1000)
    y = resample_poly(x, fr.numerator, fr.denominator, axis=0)
    if lowpass:
        y = sosfiltfilt(butter(4, lowpass, "low", fs=SAMPLE_RATE, output="sos"), y, axis=0)
    return y.astype(np.float32), sr


def cmd_file(args):
    y, sr = prepare_file(args.path, parse_channels(args.channels), args.lowpass)
    if args.normalize:
        peak = float(np.max(np.abs(y))) or 1.0
        y = y / peak
    print(f"Archivo: {args.path} ({sr} Hz -> 3000 Hz, {len(y) / SAMPLE_RATE:.1f} s)")
    s8 = to_s8(y, args.gain)

    def producer(fifo):
        while True:
            for i in range(0, len(s8), FRAMES * 8):
                if fifo.closed:
                    return
                fifo.push(s8[i:i + FRAMES * 8])
            if not args.loop:
                return

    run_session(args, producer, live=False)


# ---- Efectos ---------------------------------------------------------------

def _t(seconds):
    return np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE


def _env(n, attack=0.005, release=0.03):
    """Envolvente con ataque y caída cortos para que no 'clickee'."""
    e = np.ones(n, np.float32)
    a = min(n, int(attack * SAMPLE_RATE))
    r = min(n, int(release * SAMPLE_RATE))
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def fx_tone(a):
    t = _t(a.duration)
    s = np.sin(2 * np.pi * a.freq * t) * _env(len(t))
    return np.stack([s, s], 1)


def fx_pulse(a):
    period = 1.0 / a.rate
    on = _t(period * a.duty)
    burst = np.sin(2 * np.pi * a.freq * on) * _env(len(on), 0.002, 0.01)
    one = np.zeros(int(period * SAMPLE_RATE))
    one[:len(burst)] = burst
    s = np.tile(one, max(1, int(a.duration * a.rate)))
    return np.stack([s, s], 1)


def fx_heartbeat(a):
    beat = 60.0 / a.bpm

    def thump(f, dur, amp):
        t = _t(dur)
        return amp * np.sin(2 * np.pi * f * t) * np.exp(-t * 18)

    one = np.zeros(int(beat * SAMPLE_RATE))
    lub, dub = thump(a.freq, 0.18, 1.0), thump(a.freq * 0.8, 0.16, 0.7)
    one[:len(lub)] += lub
    off = int(0.28 * SAMPLE_RATE)
    one[off:off + len(dub)] += dub[:len(one) - off]
    s = np.tile(one, max(1, int(a.duration / beat)))
    return np.stack([s, s], 1)


def fx_sweep(a):
    from scipy.signal import chirp
    t = _t(a.duration)
    s = chirp(t, f0=30, f1=1200, t1=a.duration, method="logarithmic") * _env(len(t))
    return np.stack([s, s], 1)


def fx_rumble(a):
    from scipy.signal import butter, sosfilt
    t = _t(a.duration)
    rng = np.random.default_rng(1)
    noise = rng.standard_normal((len(t), 2))
    sos = butter(4, [25, max(30, a.freq)], "bandpass", fs=SAMPLE_RATE, output="sos")
    y = sosfilt(sos, noise, axis=0)
    y /= np.max(np.abs(y)) or 1
    wobble = 0.65 + 0.35 * np.sin(2 * np.pi * 0.7 * t)       # motor que sube y baja
    return y * (wobble * _env(len(t), 0.2, 0.3))[:, None]


def fx_pingpong(a):
    period = 1.0 / a.rate
    on = _t(period * 0.5 * a.duty)
    burst = np.sin(2 * np.pi * a.freq * on) * _env(len(on), 0.002, 0.01)
    half = int(period * SAMPLE_RATE / 2)
    one = np.zeros((half * 2, 2))
    one[:len(burst), 0] = burst
    one[half:half + len(burst), 1] = burst
    return np.tile(one, (max(1, int(a.duration * a.rate)), 1))


EFFECTS = {"tone": fx_tone, "pulse": fx_pulse, "heartbeat": fx_heartbeat,
           "sweep": fx_sweep, "rumble": fx_rumble, "pingpong": fx_pingpong}

FX_FREQ_DEFAULT = {"tone": 160, "pulse": 180, "heartbeat": 55, "sweep": 0,
                   "rumble": 120, "pingpong": 200}


def cmd_fx(args):
    if args.freq is None:
        args.freq = FX_FREQ_DEFAULT[args.effect]
    y = EFFECTS[args.effect](args).astype(np.float32)
    y *= args.intensity
    if args.side == "left":
        y[:, 1] = 0
    elif args.side == "right":
        y[:, 0] = 0
    print(f"Efecto: {args.effect} ({len(y) / SAMPLE_RATE:.1f} s)")
    s8 = to_s8(y, args.gain)

    def producer(fifo):
        while True:
            for i in range(0, len(s8), FRAMES * 8):
                if fifo.closed:
                    return
                fifo.push(s8[i:i + FRAMES * 8])
            if not args.loop:
                return

    run_session(args, producer, live=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--gain", type=float, default=None,
                        help="ganancia (default: 2.0 en loopback, 1.0 en file/fx)")
    common.add_argument("--index", type=int, default=0, help="qué joystick usar si hay varios")
    common.add_argument("--buffer", type=int, default=60,
                        help="tamaño del buffer en ms (default 60; menos = menos latencia, más cortes)")
    common.add_argument("--allow-usb", action="store_true", help="permitir un joystick por USB")
    common.add_argument("--dry-run", action="store_true", help="no abrir el joystick (para probar)")
    common.add_argument("--dump", help="con --dry-run, guardar los reportes en este archivo")
    common.add_argument("-v", "--verbose", action="store_true", help="mostrar estadísticas")

    ap = argparse.ArgumentParser(prog="dshaptics",
                                 description="Háptica del DualSense por Bluetooth (basado en SAxense).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="listar joysticks y salidas de audio").set_defaults(fn=cmd_list)
    sub.add_parser("diag", help="diagnóstico: todo lo que se ve por HID").set_defaults(fn=cmd_diag)
    ap_off = sub.add_parser("apagar", help="apagar el/los DualSense conectados por Bluetooth")
    ap_off.add_argument("address", nargs="?", help="dirección (default: todos los DualSense conectados)")
    ap_off.set_defaults(fn=cmd_apagar)
    bat = sub.add_parser("bateria", parents=[common], help="nivel de batería del joystick (con vDS detenido)")
    bat.set_defaults(fn=cmd_bateria)
    tg = sub.add_parser("gatillos", help="probar los gatillos adaptativos (con o sin vDS)")
    tg.add_argument("efecto", choices=sorted(TRIGGER_EFFECTS))
    tg.add_argument("--lado", choices=["ambos", "derecho", "izquierdo"], default="ambos")
    tg.add_argument("--segundos", type=float, default=10, help="cuánto dura (0 = queda puesto)")
    tg.add_argument("--index", type=int, default=0)
    tg.set_defaults(fn=cmd_gatillos)
    rs = sub.add_parser("restablecer", help="sacar los efectos de los gatillos (con o sin vDS)")
    rs.add_argument("--index", type=int, default=0)
    rs.set_defaults(fn=cmd_restablecer)
    sub.add_parser("luces", help="listar los DualSense con su dirección, color y jugador").set_defaults(fn=cmd_luces)
    co = sub.add_parser("color", help="color de la barra y LEDs de jugador (queda guardado)")
    co.add_argument("mac", nargs="?", default="", help="dirección (default: el primero)")
    co.add_argument("color", nargs="?", help="#RRGGBB")
    co.add_argument("--jugador", type=int, choices=range(0, 6), help="LEDs de jugador 1-5 (0 = apagados)")
    co.add_argument("--nombre", help="nombre para reconocerlo")
    co.set_defaults(fn=cmd_color)
    idf = sub.add_parser("identificar", help="hacer parpadear la barra de un joystick")
    idf.add_argument("mac", nargs="?", default="")
    idf.set_defaults(fn=cmd_identificar)

    lb = sub.add_parser("loopback", parents=[common], help="audio de la PC -> motores")
    lb.add_argument("--device", help="parte del nombre de la salida a capturar (default: la predeterminada)")
    lb.add_argument("--channels", help="canales a usar, 1-indexados. Ej: 3,4 para un dispositivo "
                                       "de 4 canales estilo DualSense. Default: 1,2")
    lb.add_argument("--lowpass", type=float, help="filtrar por encima de N Hz (ej. 200 = solo graves)")
    lb.set_defaults(fn=cmd_loopback)

    fl = sub.add_parser("file", parents=[common], help="reproducir un archivo en los motores")
    fl.add_argument("path", help="WAV, FLAC, OGG, MP3...")
    fl.add_argument("--channels", help="canales a usar, 1-indexados (ej. 3,4)")
    fl.add_argument("--lowpass", type=float, help="filtrar por encima de N Hz")
    fl.add_argument("--normalize", action="store_true", help="llevar el pico al máximo")
    fl.add_argument("--loop", action="store_true", help="repetir")
    fl.set_defaults(fn=cmd_file)

    fx = sub.add_parser("fx", parents=[common], help="efectos sintetizados")
    fx.add_argument("effect", choices=sorted(EFFECTS))
    fx.add_argument("--duration", type=float, default=4.0, help="segundos (default 4)")
    fx.add_argument("--freq", type=float, help="frecuencia en Hz del efecto")
    fx.add_argument("--rate", type=float, default=4.0, help="pulsos por segundo (pulse, pingpong)")
    fx.add_argument("--duty", type=float, default=0.35, help="fracción del pulso encendida (0-1)")
    fx.add_argument("--bpm", type=float, default=72, help="latidos por minuto (heartbeat)")
    fx.add_argument("--intensity", type=float, default=0.9, help="0-1 (default 0.9)")
    fx.add_argument("--side", choices=["both", "left", "right"], default="both")
    fx.add_argument("--loop", action="store_true", help="repetir hasta Ctrl+C")
    fx.set_defaults(fn=cmd_fx)

    args = ap.parse_args(argv)
    if getattr(args, "gain", 0) is None:
        args.gain = 2.0 if args.cmd == "loopback" else 1.0
    args.fn(args)


if __name__ == "__main__":
    main()
