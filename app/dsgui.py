#!/usr/bin/env python3
"""
DualSense Control — interfaz para vDS (joystick virtual USB) y la háptica por Bluetooth.

Pestaña "Joystick virtual (vDS)": servicio, joysticks, conectar/desconectar, registro.
Pestaña "Háptica": efectos, reactivo al audio de la PC y archivos.

La háptica sale por uno de dos caminos (se elige solo):
  - vDS conectado  -> canales 3 y 4 de la placa "DualSense Wireless Controller" (igual que un juego)
  - vDS en pausa   -> Bluetooth directo, reporte 0x32 (dshaptics)

Créditos: SAxense (egormanga, https://apps.sdore.me/SAxense), vDS (hurryman2212).
"""

import argparse
import ctypes
import json
import os
import queue
import shutil
import zipfile
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

import numpy as np

import dshaptics as dh

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(dh.data_dir(), "logs")
LOG_PATH = os.path.join(LOG_DIR, "dsgui.log")
USBIP_EXE = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "USBip", "usbip.exe")
HIDHIDE_CLI = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                           "Nefarius Software Solutions", "HidHide", "x64", "HidHideCLI.exe")
VDS_DIR = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "vDS")
VDSCTL = os.path.join(VDS_DIR, "vdsctl.exe")
VDSD_LOG = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "vDS", "vdsd.log")
VDSD_EXE = os.path.join(VDS_DIR, "vdsd.exe")
# Con el parche de dsgui, mientras exista este archivo vdsd silencia el parlante/auriculares
# del joystick (canales 1-2) y deja la háptica (canales 3-4) como está.
SPEAKER_MUTE_FLAG = os.environ.get("VDS_SPEAKER_MUTE_FLAG") or os.path.join(
    os.environ.get("ProgramData", r"C:\ProgramData"), "vDS", "speaker-muted")
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
VIRTUAL_RATE = 48000
DUALSENSE_AUDIO = "DualSense Wireless Controller"

SINK_AUTO, SINK_VIRTUAL, SINK_BT = "Automática", "Joystick virtual (vDS)", "Bluetooth directo"


# Lo que el .exe trae adentro. Se copia a %LOCALAPPDATA% para que los scripts sigan
# existiendo aunque se cierre el .exe (PyInstaller borra su carpeta temporal al salir).
RESOURCE_ITEMS = ["scripts", "vds-bin", "vds-packaging", os.path.join("herramientas", "diag-windows.ps1")]
REQUIRED_RESOURCES = [os.path.join("scripts", f) for f in ("instalar.ps1", "modo.ps1", "desinstalar.ps1")] + \
    [os.path.join("vds-bin", f) for f in ("vdsd.exe", "vdsctl.exe", "opus.dll")] + \
    [os.path.join("vds-packaging", f) for f in ("install_dependencies.ps1", "install_service.ps1",
                                                "stop_service.ps1", "uninstall_service.ps1")] + \
    [os.path.join("herramientas", "diag-windows.ps1")]


def resources_root():
    if not dh.FROZEN:
        return dh.REPO_ROOT
    dst = os.path.join(dh.data_dir(), "recursos", dh.__version__)
    marker = os.path.join(dst, ".completo")
    if not os.path.exists(marker):
        src = dh.resource_dir()
        for item in RESOURCE_ITEMS:
            a, b = os.path.join(src, item), os.path.join(dst, item)
            if os.path.isdir(a):
                shutil.copytree(a, b, dirs_exist_ok=True)
            elif os.path.isfile(a):
                os.makedirs(os.path.dirname(b), exist_ok=True)
                shutil.copy2(a, b)
        with open(marker, "w") as f:
            f.write(dh.__version__)
    return dst


def resource(*parts):
    return os.path.join(resources_root(), *parts)


def is_admin():
    if sys.platform != "win32":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Control de vDS (vdsctl.exe y sc.exe)
# ---------------------------------------------------------------------------

def run_cmd(argv, timeout=10):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return -1, f"No existe {argv[0]}"
    except subprocess.TimeoutExpired:
        return -2, f"{os.path.basename(argv[0])} no respondió"


def parse_jsonl(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


class Vds:
    @staticmethod
    def installed():
        return os.path.exists(VDSCTL)

    @staticmethod
    def service_state():
        code, out = run_cmd(["sc.exe", "query", "vdsd"])
        if code == 1060 or "1060" in out:
            return "NO INSTALADO"
        for st in ("RUNNING", "STOPPED", "START_PENDING", "STOP_PENDING"):
            if st in out:
                return st
        return "DESCONOCIDO"

    @staticmethod
    def autostart():
        """True si vdsd arranca con Windows (modo vDS), False si es manual (modo normal)."""
        return "AUTO_START" in run_cmd(["sc.exe", "qc", "vdsd"])[1]

    @staticmethod
    def set_mode(mode):
        """'normal' o 'vds', con el mismo script que usan los .bat (scripts/modo.ps1)."""
        script = resource("scripts", "modo.ps1")
        code, out = run_cmd(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", script, "-Modo", mode, "-SinPausa", "-SinRestablecer"], timeout=40)
        log(f"modo {mode}: código {code}\n{out.strip()}")
        if code != 0:
            err = [l for l in out.splitlines() if "ERROR" in l]
            return {"OK": False, "error": (err[-1] if err else out.strip()) or f"código {code}"}
        if mode == "normal":
            time.sleep(2)                         # que Windows vuelva a mostrar el joystick Bluetooth
            try:
                dh.set_triggers("off")
            except BaseException:
                log("no pude restablecer los gatillos al pasar a modo normal")
        return {"OK": True}

    @staticmethod
    def start():
        return run_cmd(["sc.exe", "start", "vdsd"])

    @staticmethod
    def stop():
        return run_cmd(["sc.exe", "stop", "vdsd"])

    @staticmethod
    def targets():
        return parse_jsonl(run_cmd([VDSCTL, "list-targets"])[1])

    @staticmethod
    def registered():
        return parse_jsonl(run_cmd([VDSCTL, "list"])[1])

    @staticmethod
    def attach(address, profile):
        # Sin --ports a propósito: en Windows vDS (commit ec53159) rechaza cualquier --ports.
        res = parse_jsonl(run_cmd([VDSCTL, "attach", address, "--profile", profile])[1])
        return res[0] if res else {"OK": False, "error": "vdsctl no respondió"}

    @staticmethod
    def detach(address):
        code, out = run_cmd([VDSCTL, "detach", address])
        res = parse_jsonl(out)
        return res[0] if res else {"OK": code == 0, "error": out.strip()}

    _patch_cache = (None, False)

    @staticmethod
    def speaker_patch_installed():
        """True si el vdsd.exe instalado trae el parche del interruptor de parlante."""
        try:
            mtime = os.path.getmtime(VDSD_EXE)
        except OSError:
            return False
        if Vds._patch_cache[0] != mtime:          # releer el .exe solo si cambió
            try:
                with open(VDSD_EXE, "rb") as f:
                    Vds._patch_cache = (mtime, b"speaker-muted" in f.read())
            except OSError:
                return False
        return Vds._patch_cache[1]

    @staticmethod
    def speaker_muted():
        return os.path.exists(SPEAKER_MUTE_FLAG)

    @staticmethod
    def set_speaker_muted(muted):
        if muted:
            os.makedirs(os.path.dirname(SPEAKER_MUTE_FLAG), exist_ok=True)
            with open(SPEAKER_MUTE_FLAG, "w") as f:
                f.write("1")
        elif os.path.exists(SPEAKER_MUTE_FLAG):
            os.remove(SPEAKER_MUTE_FLAG)

    @staticmethod
    def log_tail(n=40):
        try:
            with open(VDSD_LOG, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 16384))
                lines = f.read().decode("utf-8", "replace").splitlines()
            return "\n".join(lines[-n:])
        except OSError:
            return "(todavía no hay registro de vdsd)"


# ---------------------------------------------------------------------------
# Salidas de háptica
# ---------------------------------------------------------------------------

class BtSink:
    """Bluetooth directo (reporte 0x32 de SAxense)."""
    rate = dh.SAMPLE_RATE
    name = SINK_BT

    def __init__(self, live):
        self.dev = dh.Controller()          # puede lanzar SystemExit con un mensaje
        self.fifo = dh.Fifo(int(0.06 * self.rate), drop_old=live)
        self.sender = dh.Sender(self.dev, self.fifo)
        self.sender.start()
        self.peak = 0.0

    def push(self, stereo, gain):
        y = stereo * gain
        self.peak = float(np.max(np.abs(y))) if len(y) else 0.0
        self.fifo.push(dh.to_s8(y, 1.0))

    def drained(self):
        return self.fifo.drained()

    def close(self):
        self.fifo.closed = True
        self.sender.stop()
        self.dev.close()


def find_dualsense_output(p, pyaudio):
    """Busca la placa de audio del DualSense (la que crea vDS) en WASAPI."""
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    best = None
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d.get("hostApi") != wasapi or d.get("isLoopbackDevice") or d["maxOutputChannels"] < 4:
            continue
        if "dualsense" in d["name"].lower() or "wireless controller" in d["name"].lower():
            best = d
            break
    return best


class VirtualSink:
    """Canales 3 y 4 de la placa de audio del DualSense virtual (lo mismo que hace un juego)."""
    rate = VIRTUAL_RATE
    name = SINK_VIRTUAL

    def __init__(self, live):
        import pyaudiowpatch as pyaudio
        self.p = pyaudio.PyAudio()
        dev = find_dualsense_output(self.p, pyaudio)
        if dev is None:
            self.p.terminate()
            raise RuntimeError("No encontré la placa de audio 'DualSense Wireless Controller'. "
                               "¿Está vDS conectado?")
        self.fifo = dh.Fifo(int(0.06 * self.rate), drop_old=live, dtype=np.float32)
        self.peak = 0.0
        self.stream = None
        self._continue = pyaudio.paContinue       # el callback puede correr apenas se abre
        last = None
        for ch in sorted({4, dev["maxOutputChannels"]}):
            for fmt in (pyaudio.paFloat32, pyaudio.paInt16):
                try:
                    self.nch, self.fmt, self.int16 = ch, fmt, fmt == pyaudio.paInt16
                    self.stream = self.p.open(format=fmt, channels=ch, rate=self.rate, output=True,
                                              output_device_index=dev["index"],
                                              frames_per_buffer=480, stream_callback=self._cb)
                    break
                except OSError as e:
                    last = e
            if self.stream:
                break
        if not self.stream:
            self.p.terminate()
            raise RuntimeError(f"No pude abrir la placa del DualSense: {last}")
        log(f"VirtualSink: {dev['name']} {self.nch} canales {'int16' if self.int16 else 'float32'}")

    def _cb(self, in_data, frame_count, time_info, status):
        y = self.fifo.pop(frame_count)
        self.peak = float(np.max(np.abs(y))) if len(y) else 0.0   # lo que suena ahora
        out = np.zeros((frame_count, self.nch), np.float32)
        out[:, 2] = y[:, 0]                 # canal 3 -> motor izquierdo
        out[:, 3] = y[:, 1]                 # canal 4 -> motor derecho
        if self.int16:
            return ((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes(), self._continue)
        return (out.tobytes(), self._continue)

    def push(self, stereo, gain):
        self.fifo.push(np.clip(stereo * gain, -1.0, 1.0).astype(np.float32))

    def drained(self):
        return self.fifo.drained()

    def close(self):
        self.fifo.closed = True
        time.sleep(0.05)
        try:
            self.stream.close()
        finally:
            self.p.terminate()


# ---------------------------------------------------------------------------
# Trabajos de háptica (efecto, archivo, reactivo)
# ---------------------------------------------------------------------------

def to_rate(y3k, rate):
    if rate == dh.SAMPLE_RATE:
        return y3k
    from scipy.signal import resample_poly
    return resample_poly(y3k, rate // dh.SAMPLE_RATE, 1, axis=0).astype(np.float32)


class Job(threading.Thread):
    def __init__(self, make_sink, on_error, on_done):
        super().__init__(daemon=True)
        self.make_sink, self.on_error, self.on_done = make_sink, on_error, on_done
        self.stop_evt = threading.Event()
        self.sink = None
        self.gain = 1.0

    def stop(self):
        self.stop_evt.set()

    @property
    def peak(self):
        return self.sink.peak if self.sink else 0.0

    def run(self):
        try:
            self.body()
        except BaseException as e:          # SystemExit de dh.Controller incluido
            msg = str(e) or e.__class__.__name__
            log("ERROR " + msg + "\n" + traceback.format_exc())
            self.on_error(msg)
        finally:
            if self.sink:
                try:
                    self.sink.close()
                except Exception:
                    log(traceback.format_exc())
            self.on_done(self)


class BufferJob(Job):
    """Reproduce una señal ya calculada a 3 kHz (efecto o archivo)."""

    def __init__(self, y3k, loop, gain, *a):
        super().__init__(*a)
        self.y3k, self.loop, self.gain = y3k, loop, gain

    def body(self):
        self.sink = self.make_sink(live=False)
        y = to_rate(self.y3k, self.sink.rate)
        step = self.sink.rate // 20             # bloques de 50 ms
        while not self.stop_evt.is_set():
            for i in range(0, len(y), step):
                if self.stop_evt.is_set():
                    return
                self.sink.push(y[i:i + step], self.gain)
            if not self.loop:
                break
        while not self.sink.drained() and not self.stop_evt.is_set():
            time.sleep(0.02)
        time.sleep(0.05)


class LoopbackJob(Job):
    """Audio de una salida de la PC -> motores, en vivo."""

    def __init__(self, device_name, lowpass, gain, *a):
        super().__init__(*a)
        self.device_name, self.lowpass, self.gain = device_name, lowpass, gain

    def body(self):
        import pyaudiowpatch as pyaudio
        p = pyaudio.PyAudio()
        try:
            loop = None
            for d in p.get_loopback_device_info_generator():
                if self.device_name.lower() in d["name"].lower():
                    loop = d
                    break
            if loop is None:
                raise RuntimeError(f"No encontré la salida '{self.device_name}'")
            self.sink = self.make_sink(live=True)
            rate, max_ch = int(loop["defaultSampleRate"]), loop["maxInputChannels"]
            rs = dh.StreamResampler(rate, self.lowpass, out_rate=self.sink.rate)
            st = {"nch": max_ch, "int16": False}

            def cb(in_data, frame_count, time_info, status):
                x = np.frombuffer(in_data, np.int16 if st["int16"] else np.float32)
                x = x.reshape(-1, st["nch"])
                if st["int16"]:
                    x = x.astype(np.float32) / 32768.0
                y = rs.process(dh.pick_channels(x, None))
                if len(y):
                    self.sink.push(y, self.gain)
                return (None, pyaudio.paContinue)

            stream, last = None, None
            for ch in [max_ch] + ([2] if max_ch != 2 else []):
                for fmt, is16 in ((pyaudio.paFloat32, False), (pyaudio.paInt16, True)):
                    for fpb in (max(64, rate // 200), 1024, pyaudio.paFramesPerBufferUnspecified):
                        st["nch"], st["int16"] = ch, is16
                        try:
                            stream = p.open(format=fmt, channels=ch, rate=rate, input=True,
                                            input_device_index=loop["index"],
                                            frames_per_buffer=fpb, stream_callback=cb)
                            break
                        except OSError as e:
                            last = e
                    if stream:
                        break
                if stream:
                    break
            if stream is None:
                raise RuntimeError(f"No pude capturar '{loop['name']}': {last}. Probá ponerla en "
                                   "estéreo o desactivar el sonido envolvente virtual.")
            log(f"Loopback: {loop['name']} {st['nch']}ch {'int16' if st['int16'] else 'float32'}")
            try:
                while not self.stop_evt.is_set() and stream.is_active():
                    time.sleep(0.05)
            finally:
                stream.close()
        finally:
            p.terminate()


def loopback_devices():
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        return []
    p = pyaudio.PyAudio()
    try:
        names = [d["name"].replace(" [Loopback]", "") for d in p.get_loopback_device_info_generator()]
    finally:
        p.terminate()
    # nunca capturar la propia placa del DualSense (sería un bucle)
    return [n for n in names if "dualsense" not in n.lower() and "wireless controller" not in n.lower()]


def make_effect(name, intensity):
    a = argparse.Namespace(duration=4.0, freq=dh.FX_FREQ_DEFAULT.get(name, 160), rate=4.0,
                           duty=0.35, bpm=72)
    side = None
    if name == "left":
        name, side, a.freq = "tone", 0, 150
    elif name == "right":
        name, side, a.freq = "tone", 1, 150
    elif name == "pulse":
        a.rate, a.duty = 8, 0.3
    elif name == "pingpong":
        a.rate, a.duration = 3, 6
    elif name == "tone":
        a.duration, a.freq = 3, 150
    elif name == "sweep":
        a.duration = 6
    elif name == "rumble":
        a.duration = 6
    elif name == "heartbeat":
        a.duration = 6
    y = dh.EFFECTS[name](a).astype(np.float32) * intensity
    if side is not None:
        y[:, 1 - side] = 0
    return y


# ---------------------------------------------------------------------------
# Interfaz
# ---------------------------------------------------------------------------

EFFECT_BUTTONS = [("Latido", "heartbeat"), ("Tono", "tone"), ("Pulsos", "pulse"),
                  ("Barrido", "sweep"), ("Rumble", "rumble"), ("Ping-pong", "pingpong"),
                  ("Solo izquierdo", "left"), ("Solo derecho", "right")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"DualSense Control {dh.__version__}" + ("" if is_admin() else "  (sin permisos de administrador)"))
        self.geometry("860x760")
        self.minsize(760, 700)
        try:
            import sv_ttk
            sv_ttk.set_theme("dark")
        except Exception:
            ttk.Style(self).theme_use("clam")

        self.job = None
        self.ui_queue = queue.Queue()      # los hilos dejan acá lo que hay que hacer en la UI
        self.vds_state = {"service": "…", "targets": [], "registered": [], "log": ""}
        self.vds_busy = False
        self.file_path = None

        self._build_header()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tab_vds = ttk.Frame(nb, padding=12)
        self.tab_hap = ttk.Frame(nb, padding=12)
        nb.add(self.tab_vds, text="  Joystick virtual (vDS)  ")
        nb.add(self.tab_hap, text="  Háptica  ")
        self.tab_pads = ttk.Frame(nb, padding=12)
        nb.add(self.tab_pads, text="  Joysticks y luces  ")
        self.tab_inst = ttk.Frame(nb, padding=12)
        nb.add(self.tab_inst, text="  Instalación  ")
        self._build_vds_tab()
        self._build_haptics_tab()
        self._build_pads_tab()
        self._build_install_tab()
        if not Vds.installed():
            nb.select(self.tab_inst)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.refresh_vds)
        self.after(100, self.tick)
        self.after(500, self.refresh_pads)
        self.after(300, self.reload_capture_devices)
        # precargar scipy en segundo plano: sin esto el primer efecto tarda ~1,5 s
        threading.Thread(target=lambda: __import__("scipy.signal"), daemon=True).start()

    # ---- encabezado ------------------------------------------------------
    def _build_header(self):
        h = ttk.Frame(self, padding=(12, 10))
        h.pack(fill="x")
        ttk.Label(h, text="DualSense Control", font=("Segoe UI", 16, "bold")).pack(side="left")
        self.btn_off = ttk.Button(h, text="⏻  Apagar joystick", command=self.power_off)
        self.btn_off.pack(side="right", padx=(12, 0))
        self.header_status = ttk.Label(h, text="", font=("Segoe UI", 10))
        self.header_status.pack(side="right")
        self.flash_until = 0.0       # mientras tanto, el encabezado muestra un aviso puntual

    # ---- pestaña vDS -----------------------------------------------------
    def _build_vds_tab(self):
        t = self.tab_vds
        svc = ttk.LabelFrame(t, text="Modo del joystick", padding=10)
        svc.pack(fill="x")
        left = ttk.Frame(svc)
        left.pack(side="left", fill="x", expand=True)
        self.lbl_service = ttk.Label(left, text="Consultando…", font=("Segoe UI", 11, "bold"))
        self.lbl_service.pack(anchor="w")
        self.lbl_mode = ttk.Label(left, text="", foreground="#8a8a8a")
        self.lbl_mode.pack(anchor="w")
        self.btn_stop = ttk.Button(svc, text="Modo normal", command=lambda: self.set_mode("normal"))
        self.btn_stop.pack(side="right")
        self.btn_start = ttk.Button(svc, text="Modo vDS", command=lambda: self.set_mode("vds"))
        self.btn_start.pack(side="right", padx=6)

        au = ttk.LabelFrame(t, text="Audio del joystick", padding=10)
        au.pack(fill="x", pady=(10, 0))
        self.speaker_on = tk.BooleanVar(value=not Vds.speaker_muted())
        style = "Switch.TCheckbutton" if self._has_switch_style() else "TCheckbutton"
        self.chk_speaker = ttk.Checkbutton(au, text="Sonido por el joystick (parlante y auriculares)",
                                           variable=self.speaker_on, style=style,
                                           command=self.toggle_speaker)
        self.chk_speaker.pack(side="left")
        self.lbl_speaker = ttk.Label(au, text="", foreground="#8a8a8a")
        self.lbl_speaker.pack(side="right")
        self.speaker_patch = Vds.speaker_patch_installed()

        js = ttk.LabelFrame(t, text="Joysticks", padding=10)
        js.pack(fill="x", pady=10)
        cols = ("addr", "name", "online", "reg", "conn", "profile")
        self.tree = ttk.Treeview(js, columns=cols, show="headings", height=4, selectmode="browse")
        for c, txt, w in zip(cols, ("Dirección", "Nombre", "Encendido", "Registrado", "Conectado", "Perfil"),
                             (150, 230, 85, 85, 85, 70)):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor="w" if c in ("addr", "name") else "center")
        self.tree.pack(fill="x")
        row = ttk.Frame(js)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Perfil:").pack(side="left")
        self.profile = ttk.Combobox(row, values=["ds5", "dse"], width=6, state="readonly")
        self.profile.set("ds5")
        self.profile.pack(side="left", padx=(4, 12))
        ttk.Button(row, text="Conectar", command=self.attach).pack(side="left")
        ttk.Button(row, text="Desconectar", command=self.detach).pack(side="left", padx=6)
        ttk.Label(row, text="ds5 = DualSense · dse = DualSense Edge", foreground="#8a8a8a").pack(side="right")

        lg = ttk.LabelFrame(t, text="Registro de vdsd", padding=(10, 6))
        lg.pack(fill="both", expand=True)
        self.txt_log = tk.Text(lg, height=10, wrap="none", font=("Consolas", 9),
                               bg="#1c1c1c", fg="#cfcfcf", relief="flat", insertbackground="#cfcfcf")
        sb = ttk.Scrollbar(lg, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set, state="disabled")
        sb.pack(side="right", fill="y")
        self.txt_log.pack(fill="both", expand=True)

    # ---- pestaña háptica -------------------------------------------------
    def _build_haptics_tab(self):
        t = self.tab_hap
        top = ttk.Frame(t)
        top.pack(fill="x")
        ttk.Label(top, text="Salida:").pack(side="left")
        self.sink_choice = ttk.Combobox(top, values=[SINK_AUTO, SINK_VIRTUAL, SINK_BT],
                                        width=22, state="readonly")
        self.sink_choice.set(SINK_AUTO)
        self.sink_choice.pack(side="left", padx=6)
        self.lbl_sink = ttk.Label(top, text="", foreground="#8a8a8a")
        self.lbl_sink.pack(side="left", padx=6)
        ttk.Button(top, text="↺  Restablecer joystick", command=self.reset_joystick).pack(side="right")

        lev = ttk.Frame(t)
        lev.pack(fill="x", pady=(10, 0))
        ttk.Label(lev, text="Nivel").pack(side="left")
        self.meter = ttk.Progressbar(lev, maximum=100)
        self.meter.pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_job = ttk.Label(lev, text="En reposo", width=26)
        self.lbl_job.pack(side="right")

        fx = ttk.LabelFrame(t, text="Efectos", padding=10)
        fx.pack(fill="x", pady=10)
        grid = ttk.Frame(fx)
        grid.pack(fill="x")
        for i, (txt, key) in enumerate(EFFECT_BUTTONS):
            ttk.Button(grid, text=txt, command=lambda k=key, n=txt: self.play_effect(k, n)).grid(
                row=i // 4, column=i % 4, sticky="ew", padx=3, pady=3)
        for c in range(4):
            grid.columnconfigure(c, weight=1)
        r = ttk.Frame(fx)
        r.pack(fill="x", pady=(8, 0))
        ttk.Label(r, text="Intensidad").pack(side="left")
        self.intensity = tk.DoubleVar(value=0.9)
        ttk.Scale(r, from_=0.1, to=1.0, variable=self.intensity).pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_int = ttk.Label(r, text="90 %", width=6)
        self.lbl_int.pack(side="right")

        rx = ttk.LabelFrame(t, text="Reactivo al audio de la PC", padding=10)
        rx.pack(fill="x")
        r1 = ttk.Frame(rx)
        r1.pack(fill="x")
        ttk.Label(r1, text="Capturar:").pack(side="left")
        self.cap_dev = ttk.Combobox(r1, values=[], width=44, state="readonly")
        self.cap_dev.pack(side="left", padx=6)
        ttk.Button(r1, text="↻", width=3, command=self.reload_capture_devices).pack(side="left")
        self.btn_live = ttk.Button(r1, text="▶  Iniciar", command=self.toggle_live)
        self.btn_live.pack(side="right")
        r2 = ttk.Frame(rx)
        r2.pack(fill="x", pady=(8, 0))
        ttk.Label(r2, text="Corte de graves").pack(side="left")
        self.lowpass = tk.DoubleVar(value=150)
        ttk.Scale(r2, from_=40, to=1350, variable=self.lowpass).pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_lp = ttk.Label(r2, text="150 Hz", width=8)
        self.lbl_lp.pack(side="left")
        ttk.Label(r2, text="Ganancia").pack(side="left", padx=(12, 0))
        self.live_gain = tk.DoubleVar(value=2.0)
        ttk.Scale(r2, from_=0.5, to=6.0, variable=self.live_gain).pack(side="left", fill="x", expand=True, padx=8)
        self.lbl_gain = ttk.Label(r2, text="2.0×", width=5)
        self.lbl_gain.pack(side="left")

        tg = ttk.LabelFrame(t, text="Gatillos adaptativos", padding=10)
        tg.pack(fill="x", pady=(10, 0))
        for txt, key in (("Resistencia", "duro"), ("Gatillo de arma", "arma"),
                         ("Vibración", "vibracion"), ("Apagar", "off")):
            ttk.Button(tg, text=txt, command=lambda k=key: self.set_triggers(k)).pack(side="left", padx=(0, 6))
        self.trigger_side = ttk.Combobox(tg, values=["ambos", "derecho", "izquierdo"], width=10, state="readonly")
        self.trigger_side.set("ambos")
        self.trigger_side.pack(side="left", padx=(6, 0))
        self.lbl_trig = ttk.Label(tg, text="Con un juego abierto, manda el juego.",
                                  foreground="#8a8a8a")
        self.lbl_trig.pack(side="right")

        fl = ttk.LabelFrame(t, text="Archivo de audio", padding=10)
        fl.pack(fill="x", pady=10)
        ttk.Button(fl, text="Elegir…", command=self.pick_file).pack(side="left")
        self.lbl_file = ttk.Label(fl, text="Ninguno", foreground="#8a8a8a")
        self.lbl_file.pack(side="left", padx=8)
        self.file_loop = tk.BooleanVar(value=False)
        ttk.Button(fl, text="▶  Reproducir", command=self.play_file).pack(side="right")
        ttk.Checkbutton(fl, text="Repetir", variable=self.file_loop).pack(side="right", padx=8)

    # ---- pestaña instalación --------------------------------------------
    def _build_install_tab(self):
        t = self.tab_inst
        st = ttk.LabelFrame(t, text="Estado", padding=10)
        st.pack(fill="x")
        self.inst_rows = {}
        for key, label in (("app", "DualSense Control"), ("vds", "vDS (joystick virtual)"),
                           ("svc", "Servicio vdsd"), ("usbip", "USB/IP (usbip-win2)"), ("hidhide", "HidHide")):
            r = ttk.Frame(st)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=24).pack(side="left")
            v = ttk.Label(r, text="…")
            v.pack(side="left")
            self.inst_rows[key] = v

        ac = ttk.LabelFrame(t, text="Acciones", padding=10)
        ac.pack(fill="x", pady=10)
        ttk.Button(ac, text="Instalar o reparar", command=self.run_install).pack(side="left")
        ttk.Button(ac, text="Desinstalar vDS", command=self.run_uninstall).pack(side="left", padx=6)
        ttk.Button(ac, text="📦 Reportar problema", command=self.report_problem).pack(side="left", padx=6)
        ttk.Button(ac, text="Carpeta de registros", command=lambda: self._open_folder(LOG_DIR)).pack(side="left")
        self.lbl_inst = ttk.Label(t, text="", foreground="#8a8a8a", wraplength=760, justify="left")
        self.lbl_inst.pack(anchor="w")
        how = ("La instalación abre una ventana propia y pide confirmación. Instala USB/IP y HidHide "
               "(instaladores oficiales y firmados, bajados de sus sitios) y el servicio de vDS. "
               "Si Windows pide reiniciar, reiniciá y volvé a tocar \"Instalar o reparar\".")
        ttk.Label(t, text=how, foreground="#8a8a8a", wraplength=760, justify="left").pack(anchor="w", pady=(10, 0))

    def _render_install(self):
        ok, warn, bad = "#4caf50", "#e0a030", "#e05050"
        rows = self.inst_rows
        rows["app"].configure(text=f"versión {dh.__version__}" + (" (ejecutable)" if dh.FROZEN else " (código fuente)"),
                              foreground=ok)
        if not Vds.installed():
            rows["vds"].configure(text="no instalado", foreground=bad)
        elif self.speaker_patch:
            rows["vds"].configure(text="instalado, con nuestras modificaciones", foreground=ok)
        else:
            rows["vds"].configure(text="instalado, pero sin nuestras modificaciones: tocá Instalar o reparar",
                                  foreground=warn)
        svc = self.vds_state.get("service")
        rows["svc"].configure(text={"RUNNING": "en marcha (modo vDS)", "STOPPED": "detenido (modo normal)",
                                    "NO INSTALADO": "no registrado"}.get(svc, svc or "…"),
                              foreground=ok if svc in ("RUNNING", "STOPPED") else bad)
        rows["usbip"].configure(text="instalado" if os.path.exists(USBIP_EXE) else "no instalado",
                                foreground=ok if os.path.exists(USBIP_EXE) else bad)
        rows["hidhide"].configure(text="instalado" if os.path.exists(HIDHIDE_CLI) else "no instalado",
                                  foreground=ok if os.path.exists(HIDHIDE_CLI) else bad)

    def _open_folder(self, path, select=None):
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            if select:
                subprocess.Popen(["explorer", "/select,", select])
            else:
                os.startfile(path)

    def _console(self, script, args=()):
        """Corre un script de PowerShell en una ventana propia (para que se vea el progreso)."""
        flags = 0x00000010 if sys.platform == "win32" else 0       # CREATE_NEW_CONSOLE
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *args]
        log("consola: " + " ".join(cmd))
        return subprocess.Popen(cmd, creationflags=flags)

    def run_install(self):
        try:
            if dh.FROZEN:
                missing = [r for r in REQUIRED_RESOURCES if not os.path.exists(resource(r))]
                if missing:
                    raise RuntimeError("Al ejecutable le faltan archivos: " + ", ".join(missing))
                self._console(resource("scripts", "instalar.ps1"),
                              ["-Binarios", resource("vds-bin"), "-Paquete", resource("vds-packaging"),
                               "-Logs", LOG_DIR])
            else:
                self._console(resource("scripts", "instalar.ps1"))
            self.lbl_inst.configure(text="Se abrió la ventana de instalación. Cuando termine, el estado se actualiza solo.",
                                    foreground="#cfcfcf")
        except Exception as e:
            log(traceback.format_exc())
            messagebox.showerror("Instalación", str(e))

    def run_uninstall(self):
        if not messagebox.askyesno("Desinstalar", "¿Detener y quitar vDS? El joystick vuelve a ser Bluetooth común.\n"
                                                  "USB/IP y HidHide quedan instalados."):
            return
        self.stop_job()
        try:
            self._console(resource("scripts", "desinstalar.ps1"))
        except Exception as e:
            messagebox.showerror("Desinstalar", str(e))

    def report_problem(self):
        self.lbl_inst.configure(text="Juntando registros y diagnóstico…", foreground="#cfcfcf")

        def work():
            try:
                path = build_report_zip()
                msg, color = f"Listo: {path}. Mandalo junto con lo que pasó.", "#4caf50"
                self.post(lambda: self._open_folder(os.path.dirname(path), select=path))
            except Exception as e:
                log(traceback.format_exc())
                msg, color = f"No pude armar el reporte: {e}", "#e05050"
            self.post(lambda: self.lbl_inst.configure(text=msg, foreground=color))
        threading.Thread(target=work, daemon=True).start()

    # ---- pestaña joysticks y luces ---------------------------------------
    PRESETS = [("Azul", "#0040ff"), ("Rojo", "#ff0000"), ("Verde", "#00ff40"), ("Amarillo", "#ffc000"),
               ("Violeta", "#a000ff"), ("Celeste", "#00c0ff"), ("Blanco", "#ffffff"), ("Apagada", "#000000")]

    def _build_pads_tab(self):
        t = self.tab_pads
        self.pads = []                       # lo último que se detectó
        self.pads_busy = False
        self.pads_applied = set()            # (mac, path) a los que ya se les aplicó lo guardado
        self.pad_color = "#0040ff"

        lst = ttk.LabelFrame(t, text="DualSense conectados", padding=10)
        lst.pack(fill="x")
        cols = ("name", "mac", "via", "color", "player")
        self.pad_tree = ttk.Treeview(lst, columns=cols, show="headings", height=4, selectmode="browse")
        for c, txt, w in zip(cols, ("Nombre", "Dirección", "Conexión", "Color", "Jugador"),
                             (170, 150, 190, 90, 70)):
            self.pad_tree.heading(c, text=txt)
            self.pad_tree.column(c, width=w, anchor="w" if c in ("name", "mac", "via") else "center")
        self.pad_tree.pack(fill="x")
        self.pad_tree.bind("<<TreeviewSelect>>", lambda e: self._load_pad_editor())
        ttk.Label(lst, text="En modo vDS aparecen solo los joysticks conectados en la pestaña vDS. "
                            "Un juego abierto puede cambiar el color.", foreground="#8a8a8a").pack(anchor="w", pady=(6, 0))

        ed = ttk.LabelFrame(t, text="Joystick elegido", padding=10)
        ed.pack(fill="x", pady=10)
        r1 = ttk.Frame(ed)
        r1.pack(fill="x")
        ttk.Label(r1, text="Nombre").pack(side="left")
        self.pad_name = ttk.Entry(r1, width=24)
        self.pad_name.pack(side="left", padx=(6, 18))
        ttk.Label(r1, text="Jugador").pack(side="left")
        self.pad_player = ttk.Combobox(r1, values=["Ninguno", "1", "2", "3", "4", "5"], width=9, state="readonly")
        self.pad_player.set("1")
        self.pad_player.pack(side="left", padx=6)
        ttk.Button(r1, text="💡 Identificar", command=self.identify_pad).pack(side="right")

        r2 = ttk.Frame(ed)
        r2.pack(fill="x", pady=(10, 0))
        ttk.Label(r2, text="Color").pack(side="left")
        self.swatch = tk.Canvas(r2, width=46, height=22, highlightthickness=1, highlightbackground="#555")
        self.swatch.pack(side="left", padx=6)
        ttk.Button(r2, text="Elegir…", command=self.pick_color).pack(side="left")
        for name, hexc in self.PRESETS:
            b = tk.Button(r2, text=" ", width=2, bg=hexc, activebackground=hexc, relief="flat",
                          command=lambda c=hexc: self._set_swatch(c))
            b.pack(side="left", padx=2)
        self._set_swatch(self.pad_color)

        r3 = ttk.Frame(ed)
        r3.pack(fill="x", pady=(10, 0))
        ttk.Button(r3, text="Aplicar y guardar", command=self.apply_pad).pack(side="left")
        self.lbl_pad = ttk.Label(r3, text="", foreground="#8a8a8a")
        self.lbl_pad.pack(side="left", padx=10)

    def _set_swatch(self, hexc):
        self.pad_color = hexc
        self.swatch.delete("all")
        self.swatch.create_rectangle(0, 0, 48, 24, fill=hexc, outline="")

    def pick_color(self):
        rgb, hexc = colorchooser.askcolor(color=self.pad_color, title="Color de la barra")
        if hexc:
            self._set_swatch(hexc)

    def _selected_pad(self):
        sel = self.pad_tree.selection()
        if not sel:
            return None
        mac = self.pad_tree.item(sel[0])["values"][1]
        return next((p for p in self.pads if p["mac"] == str(mac)), None)

    def _load_pad_editor(self):
        pad = self._selected_pad()
        if not pad:
            return
        c = dh.load_config().get(pad["mac"], {})
        self.pad_name.delete(0, "end")
        self.pad_name.insert(0, c.get("name", ""))
        pl = c.get("player")
        self.pad_player.set("Ninguno" if pl == 0 else str(pl) if pl else "1")
        self._set_swatch(c.get("color", "#0040ff"))

    def refresh_pads(self):
        if not self.pads_busy:
            self.pads_busy = True
            threading.Thread(target=self._pads_worker, daemon=True).start()
        self.after(3000, self.refresh_pads)

    def _pads_worker(self):
        try:
            pads = dh.list_pads()
            cfg = dh.load_config()
            # aplicar lo guardado a los joysticks que aparecen (o reaparecen en otro modo)
            for p in pads:
                key = (p["mac"], p["path"])
                c = cfg.get(p["mac"])
                if p["mac"] and c and key not in self.pads_applied:
                    try:
                        rgb = dh.parse_color(c["color"]) if c.get("color") else None
                        dh.send_state(p, dh.light_state(rgb, c.get("player")))
                        self.pads_applied.add(key)
                        log(f"luces aplicadas a {p['mac']}: {c}")
                    except Exception:
                        log(traceback.format_exc())
            present = {(p["mac"], p["path"]) for p in pads}
            self.pads_applied &= present          # si se desconecta, al volver se aplica de nuevo
            self.post(lambda: self._render_pads(pads, cfg))
        except Exception:
            log(traceback.format_exc())
        finally:
            self.pads_busy = False

    def _render_pads(self, pads, cfg):
        self.pads = pads
        sel = self.pad_tree.selection()
        sel_mac = str(self.pad_tree.item(sel[0])["values"][1]) if sel else None
        self.pad_tree.delete(*self.pad_tree.get_children())
        first = None
        for p in pads:
            c = cfg.get(p["mac"], {})
            pl = c.get("player")
            iid = self.pad_tree.insert("", "end", values=(c.get("name") or p["model"], p["mac"] or "¿?", p["via"],
                                                          c.get("color", "—"),
                                                          "—" if pl is None else ("no" if pl == 0 else pl)))
            first = first or iid
            if p["mac"] == sel_mac:
                self.pad_tree.selection_set(iid)
        if not self.pad_tree.selection() and first:
            self.pad_tree.selection_set(first)

    def _pad_or_warn(self):
        pad = self._selected_pad()
        if not pad:
            messagebox.showinfo("Joysticks", "No hay ningún joystick elegido.")
        return pad

    def identify_pad(self):
        pad = self._pad_or_warn()
        if not pad:
            return
        self.lbl_pad.configure(text="Mirá cuál parpadea…", foreground="#cfcfcf")

        def work():
            try:
                dh.identify(pad["mac"])
                msg, color = "Ese es.", "#4caf50"
            except Exception as e:
                log(traceback.format_exc())
                msg, color = f"No pude: {e}", "#e05050"
            self.post(lambda: self.lbl_pad.configure(text=msg, foreground=color))
        threading.Thread(target=work, daemon=True).start()

    def apply_pad(self):
        pad = self._pad_or_warn()
        if not pad:
            return
        name = self.pad_name.get().strip()
        pl = self.pad_player.get()
        player = 0 if pl == "Ninguno" else int(pl)
        hexc = self.pad_color

        def work():
            try:
                dh.send_state(pad, dh.light_state(dh.parse_color(hexc), player))
                cfg = dh.load_config()
                entry = cfg.setdefault(pad["mac"], {})
                entry.update(color=hexc, player=player)
                if name:
                    entry["name"] = name
                dh.save_config(cfg)
                self.pads_applied.add((pad["mac"], pad["path"]))
                log(f"luces guardadas {pad['mac']}: {entry}")
                msg, color = "Guardado. Se vuelve a aplicar solo cuando se reconecte.", "#4caf50"
                self.post(lambda: self._render_pads(self.pads, cfg))
            except Exception as e:
                log(traceback.format_exc())
                msg, color = f"No pude: {e}", "#e05050"
            self.post(lambda: self.lbl_pad.configure(text=msg, foreground=color))
        threading.Thread(target=work, daemon=True).start()

    # ---- vDS: refresco en segundo plano ---------------------------------
    def post(self, fn):
        """Seguro desde cualquier hilo: la UI lo ejecuta en su próximo tick."""
        self.ui_queue.put(fn)

    def refresh_vds(self):
        if not self.vds_busy:
            self.vds_busy = True
            threading.Thread(target=self._refresh_worker, daemon=True).start()
        self.after(2000, self.refresh_vds)

    def _refresh_worker(self):
        try:
            st = {"service": Vds.service_state()}
            st["autostart"] = Vds.autostart() if st["service"] != "NO INSTALADO" else None
            if st["service"] == "RUNNING" and Vds.installed():
                st["targets"], st["registered"] = Vds.targets(), Vds.registered()
            else:
                st["targets"], st["registered"] = [], []
            st["log"] = Vds.log_tail()
            st["speaker_patch"] = Vds.speaker_patch_installed()
            self.vds_state = st
        except Exception:
            log(traceback.format_exc())
        finally:
            self.vds_busy = False
        self.post(self._render_vds)

    def vds_connected(self):
        return any(r.get("connected") for r in self.vds_state.get("registered", []))

    def _render_vds(self):
        st = self.vds_state
        svc = st["service"]
        nice = {"RUNNING": "● Modo vDS: joystick virtual USB",
                "STOPPED": "○ Modo normal: DualSense Bluetooth común",
                "NO INSTALADO": "vDS no está instalado", "START_PENDING": "Iniciando vDS…",
                "STOP_PENDING": "Deteniendo vDS…"}.get(svc, svc)
        color = {"RUNNING": "#4caf50", "STOPPED": "#e0a030"}.get(svc, "#cfcfcf")
        self.lbl_service.configure(text=nice, foreground=color)
        auto = st.get("autostart")
        if svc == "RUNNING":
            sub = ("Háptica nativa en juegos (con Steam Input desactivado)." +
                   ("" if auto else "  Ojo: no arranca con Windows."))
        elif svc == "STOPPED":
            sub = ("Para Steam, otros juegos o la PS5." +
                   ("  Ojo: vDS va a volver a arrancar al reiniciar." if auto else
                    "  vDS no arranca con Windows."))
        else:
            sub = ""
        self.lbl_mode.configure(text=sub)
        self.speaker_patch = st.get("speaker_patch", self.speaker_patch)
        self._render_speaker()
        self._render_install()
        # cada botón se habilita si hay algo que cambiar (incluye el arranque con Windows)
        can_vds = svc == "STOPPED" or (svc == "RUNNING" and auto is False)
        can_normal = svc == "RUNNING" or (svc == "STOPPED" and auto)
        self.btn_start.state(["!disabled"] if can_vds else ["disabled"])
        self.btn_stop.state(["!disabled"] if can_normal else ["disabled"])

        regs = {r.get("address"): r for r in st.get("registered", [])}
        rows = {}
        for tg in st.get("targets", []):
            rows[tg["address"]] = (tg.get("name", ""), tg.get("online"), tg.get("registered"))
        for a in regs:
            rows.setdefault(a, ("", None, True))
        sel = self.tree.selection()
        sel_addr = self.tree.item(sel[0])["values"][0] if sel else None
        self.tree.delete(*self.tree.get_children())
        yes = lambda v: "sí" if v else ("no" if v is not None else "—")
        for a, (name, online, reg) in rows.items():
            r = regs.get(a, {})
            iid = self.tree.insert("", "end", values=(a, name, yes(online), yes(reg or a in regs),
                                                      yes(r.get("connected")) if a in regs else "—",
                                                      r.get("profile", "")))
            if a == sel_addr or (sel_addr is None and len(rows) == 1):
                self.tree.selection_set(iid)

        self.txt_log.configure(state="normal")
        at_end = self.txt_log.yview()[1] > 0.98
        self.txt_log.delete("1.0", "end")
        self.txt_log.insert("end", st.get("log", ""))
        if at_end:
            self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

        if time.time() < self.flash_until:
            pass
        elif self.vds_connected():
            self.header_status.configure(text="● Joystick virtual conectado", foreground="#4caf50")
        elif svc == "RUNNING":
            self.header_status.configure(text="● Modo vDS, sin joystick conectado", foreground="#e0a030")
        else:
            self.header_status.configure(text="○ Modo normal (Bluetooth común)", foreground="#8a8a8a")
        self._render_sink_label()

    def _selected_address(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("DualSense Control", "Elegí un joystick de la lista.")
            return None
        return str(self.tree.item(sel[0])["values"][0])

    def _bg(self, fn, done_msg=None):
        def work():
            try:
                res = fn()
                if isinstance(res, dict) and not res.get("OK", True):
                    self.post(lambda: messagebox.showerror("vDS", res.get("error") or str(res)))
                elif done_msg:
                    log(done_msg)
            except Exception as e:
                log(traceback.format_exc())
                msg = str(e)
                self.post(lambda: messagebox.showerror("vDS", msg))
        threading.Thread(target=work, daemon=True).start()

    def _has_switch_style(self):
        try:
            ttk.Style(self).layout("Switch.TCheckbutton")
            return True
        except tk.TclError:
            return False

    def toggle_speaker(self):
        want_on = bool(self.speaker_on.get())
        try:
            Vds.set_speaker_muted(not want_on)
            log("parlante del joystick " + ("activado" if want_on else "silenciado"))
        except OSError as e:
            self.speaker_on.set(not want_on)
            messagebox.showerror("Audio del joystick", f"No pude cambiarlo: {e}")
        self._render_speaker()

    def _render_speaker(self):
        if not self.speaker_patch:
            self.chk_speaker.state(["disabled"])
            self.lbl_speaker.configure(text="Falta la modificación: corré instalar.bat", foreground="#e0a030")
            return
        self.chk_speaker.state(["!disabled"])
        self.speaker_on.set(not Vds.speaker_muted())
        if self.speaker_on.get():
            self.lbl_speaker.configure(text="Juego → parlantes de la PC y joystick", foreground="#8a8a8a")
        else:
            self.lbl_speaker.configure(text="Silenciado · la vibración sigue igual", foreground="#4caf50")

    def set_mode(self, mode):
        if mode == "normal":
            self.stop_job()
        self.lbl_service.configure(text="Cambiando de modo…", foreground="#cfcfcf")
        self.btn_start.state(["disabled"])
        self.btn_stop.state(["disabled"])
        self._bg(lambda: Vds.set_mode(mode), f"pedido modo {mode}")

    # compatibilidad: otras partes llaman a estos
    def svc_start(self):
        self.set_mode("vds")

    def svc_stop(self):
        self.set_mode("normal")

    def attach(self):
        a = self._selected_address()
        if a:
            profile = self.profile.get()          # leer la UI acá, nunca desde el hilo
            self._bg(lambda: Vds.attach(a, profile), f"attach {a}")

    def detach(self):
        a = self._selected_address()
        if a:
            self._bg(lambda: Vds.detach(a), f"detach {a}")

    # ---- háptica ---------------------------------------------------------
    def effective_sink(self):
        c = self.sink_choice.get()
        if c == SINK_AUTO:
            return SINK_VIRTUAL if self.vds_connected() else SINK_BT
        return c

    def _render_sink_label(self):
        s = self.effective_sink()
        txt = ("→ canales 3-4 de la placa del joystick virtual" if s == SINK_VIRTUAL
               else "→ reporte Bluetooth 0x32 (vDS tiene que estar detenido)")
        self.lbl_sink.configure(text=txt)

    def _sink_factory(self):
        kind = self.effective_sink()
        if kind == SINK_BT and self.vds_state.get("service") == "RUNNING":
            # con vDS en marcha HidHide esconde el joystick: avisar en lugar de fallar raro
            raise RuntimeError("vDS está en marcha y esconde el joystick. Detené el servicio en la "
                               "pestaña vDS, o elegí la salida 'Joystick virtual (vDS)'.")
        return (lambda live: VirtualSink(live)) if kind == SINK_VIRTUAL else (lambda live: BtSink(live))

    def _start_job(self, job_cls, label, *args):
        self.stop_job()
        try:
            factory = self._sink_factory()
        except RuntimeError as e:
            messagebox.showwarning("DualSense Control", str(e))
            return None
        job = job_cls(*args, factory, self._job_error, self._job_done)
        job.label = label
        self.job = job
        job.start()
        return job

    def _job_error(self, msg):
        self.post(lambda: messagebox.showerror("Háptica", msg))

    def _job_done(self, job):
        def upd():
            if self.job is job:
                self.job = None
        self.post(upd)

    def stop_job(self):
        if self.job:
            self.job.stop()
            self.job.join(1.5)
            self.job = None

    def play_effect(self, key, label):
        y = make_effect(key, float(self.intensity.get()))
        self._start_job(BufferJob, f"Efecto: {label}", y, False, 1.0)

    def reset_joystick(self):
        """Corta lo que esté sonando y deja los gatillos sin efecto. vDS sigue como está."""
        self.stop_job()
        self.set_triggers("off", side="ambos", quiet_label="Joystick restablecido")

    def set_triggers(self, effect, side=None, quiet_label=None):
        side = side or self.trigger_side.get()       # leer la UI acá, no desde el hilo
        if self.effective_sink() == SINK_BT and self.vds_state.get("service") == "RUNNING":
            messagebox.showwarning("Gatillos", "vDS está en marcha pero sin joystick conectado. "
                                   "Conectalo en la pestaña vDS o detené el servicio.")
            return
        self.lbl_trig.configure(text="Aplicando…", foreground="#cfcfcf")

        def work():
            try:
                via = dh.set_triggers(effect, side)
                msg = quiet_label or ("Gatillos apagados" if effect == "off" else "Listo: apretá los gatillos")
                color = "#4caf50"
                log(f"gatillos {effect} {side} via {via}")
            except BaseException as e:               # SystemExit de dh.Controller incluido
                log(traceback.format_exc())
                msg, color = f"No pude: {e}", "#e05050"
            self.post(lambda: self.lbl_trig.configure(text=msg, foreground=color))
        threading.Thread(target=work, daemon=True).start()

    def toggle_live(self):
        if self.job and isinstance(self.job, LoopbackJob):
            self.stop_job()
            return
        dev = self.cap_dev.get()
        if not dev:
            messagebox.showinfo("DualSense Control", "Elegí qué salida de audio capturar.")
            return
        self._start_job(LoopbackJob, f"Reactivo: {dev[:22]}", dev,
                        float(self.lowpass.get()), float(self.live_gain.get()))

    def reload_capture_devices(self):
        def work():
            devs = loopback_devices()
            def upd():
                self.cap_dev.configure(values=devs)
                if devs and self.cap_dev.get() not in devs:
                    self.cap_dev.set(devs[0])
            self.post(upd)
        threading.Thread(target=work, daemon=True).start()

    def pick_file(self):
        p = filedialog.askopenfilename(title="Elegí un archivo de audio",
                                       filetypes=[("Audio", "*.wav *.mp3 *.flac *.ogg"), ("Todos", "*.*")])
        if p:
            self.file_path = p
            self.lbl_file.configure(text=os.path.basename(p), foreground="")

    def play_file(self):
        if not self.file_path:
            self.pick_file()
            if not self.file_path:
                return
        try:
            y, _ = dh.prepare_file(self.file_path, None, 300)
        except BaseException as e:
            messagebox.showerror("Archivo", str(e))
            return
        peak = float(np.max(np.abs(y))) or 1.0
        y = y / peak * float(self.intensity.get())
        self._start_job(BufferJob, f"Archivo: {os.path.basename(self.file_path)[:20]}",
                        y, bool(self.file_loop.get()), 1.0)

    # ---- refresco rápido de la UI ---------------------------------------
    def tick(self):
        while True:
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log(traceback.format_exc())
        self.lbl_int.configure(text=f"{self.intensity.get() * 100:.0f} %")
        self.lbl_lp.configure(text=f"{self.lowpass.get():.0f} Hz")
        self.lbl_gain.configure(text=f"{self.live_gain.get():.1f}×")
        job = self.job
        if job and isinstance(job, LoopbackJob):
            job.gain = float(self.live_gain.get())      # la ganancia se ajusta en vivo
        if job and job.is_alive():
            self._meter = max(job.peak * 100, getattr(self, "_meter", 0) * 0.8)
            self.meter["value"] = min(100, self._meter)
            self.lbl_job.configure(text=getattr(job, "label", "Reproduciendo"))
        else:
            self.meter["value"] = 0
            self.lbl_job.configure(text="En reposo")
        self.btn_live.configure(text="■  Detener" if isinstance(job, LoopbackJob) else "▶  Iniciar")
        self.after(80, self.tick)

    def flash(self, text, color="#e0a030", seconds=5):
        self.flash_until = time.time() + seconds
        self.header_status.configure(text=text, foreground=color)

    def power_off(self):
        """Corta el Bluetooth del DualSense: el joystick se apaga solo (como en DS4Windows)."""
        self.stop_job()
        known = [t["address"] for t in self.vds_state.get("targets", []) if t.get("online")]
        self.btn_off.state(["disabled"])
        self.flash("Apagando…", "#cfcfcf")

        def work():
            msg, color = "", "#4caf50"
            try:
                pads = [a for a, _ in dh.connected_dualsenses()] or known
                if not pads:
                    msg, color = "No hay ningún DualSense conectado", "#e0a030"
                else:
                    for a in pads:
                        dh.power_off(a)
                    msg = "⏻ Joystick apagado" if len(pads) == 1 else f"⏻ {len(pads)} joysticks apagados"
                    log("apagado " + ", ".join(pads))
            except Exception as e:
                log(traceback.format_exc())
                msg, color = f"No pude apagarlo: {e}", "#e05050"

            def done():
                self.btn_off.state(["!disabled"])
                self.flash(msg, color)
            self.post(done)
        threading.Thread(target=work, daemon=True).start()

    def on_close(self):
        self.stop_job()
        self.destroy()


def build_report_zip():
    """Junta todo lo útil para diagnosticar en un .zip (en el Escritorio si existe)."""
    import platform
    stamp = time.strftime("%Y%m%d-%H%M%S")
    desk = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
    folder = desk if os.path.isdir(desk) else dh.data_dir()
    path = os.path.join(folder, f"DualSenseControl-reporte-{stamp}.zip")
    tmp = os.path.join(dh.data_dir(), "reporte-tmp")
    os.makedirs(tmp, exist_ok=True)
    diag = os.path.join(tmp, "diag-windows.txt")
    script = resource("herramientas", "diag-windows.ps1")
    if sys.platform == "win32" and os.path.exists(script):
        env = dict(os.environ, DSC_SIN_PAUSA="1")
        try:
            subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                            "-Out", diag], timeout=120, env=env, creationflags=NO_WINDOW,
                           capture_output=True)
        except Exception:
            log(traceback.format_exc())
    info = (f"DualSense Control {dh.__version__} ({'exe' if dh.FROZEN else 'fuente'})\n"
            f"Python {platform.python_version()} {platform.architecture()[0]}\n{platform.platform()}\n"
            f"administrador: {is_admin()}\nfecha: {time.strftime('%Y-%m-%d %H:%M:%S %z')}\n")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", info)
        if os.path.isdir(LOG_DIR):
            for f in os.listdir(LOG_DIR):
                fp = os.path.join(LOG_DIR, f)
                if os.path.isfile(fp):
                    z.write(fp, f"logs/{f}")
        if os.path.exists(diag):
            z.write(diag, "diag-windows.txt")
        vds_dir = os.path.dirname(VDSD_LOG)
        for f in ("vdsd.log", "vdsd.db"):
            fp = os.path.join(vds_dir, f)
            if os.path.exists(fp):
                with open(fp, "rb") as fh:
                    if f == "vdsd.log":
                        fh.seek(max(0, os.path.getsize(fp) - 2_000_000))      # últimos 2 MB
                    z.writestr(f"vds/{f}", fh.read())
        if os.path.exists(dh.CONFIG_PATH):
            z.write(dh.CONFIG_PATH, "config/joysticks.json")
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"reporte armado: {path}")
    return path


def self_test(out_path=None):
    """Autoprueba sin joystick: la usa la CI sobre el .exe en un Windows limpio."""
    results = []

    def check(name, fn, critical=True):
        try:
            detail = fn()
            results.append({"check": name, "ok": True, "detail": "" if detail is None else str(detail)})
        except BaseException as e:
            results.append({"check": name, "ok": False, "critical": critical,
                            "detail": f"{type(e).__name__}: {e}"})

    def tk_theme():
        root = tk.Tk()
        root.withdraw()
        import sv_ttk
        sv_ttk.set_theme("dark")
        root.update()
        root.destroy()
        return "ok"

    def protocol():
        import zlib
        r = dh.build_report(bytes(64), 0, 0)
        assert int.from_bytes(r[138:], "little") == zlib.crc32(b"\xA2" + r[:138])
        assert dh.trigger_report(dh.trigger_state(right=dh.trigger_off()), True)[0] == 0x31
        return "reportes 0x32/0x31 y CRC ok"

    def resources_ok():
        missing = [r for r in REQUIRED_RESOURCES if not os.path.exists(resource(r))]
        assert not missing, "faltan: " + ", ".join(missing)
        return f"{len(REQUIRED_RESOURCES)} archivos en {resources_root()}"

    def vds_modified():
        with open(resource("vds-bin", "vdsd.exe"), "rb") as f:
            assert b"speaker-muted" in f.read(), "vdsd.exe sin la modificación del parlante"
        return "vdsd.exe trae 0001-silenciar-parlante"

    def audio():
        import pyaudiowpatch as pa
        p = pa.PyAudio()
        try:
            return f"{p.get_device_count()} dispositivos de audio"
        finally:
            p.terminate()

    check("versión", lambda: dh.__version__)
    check("numpy", lambda: np.__version__)
    check("scipy.signal", lambda: __import__("scipy.signal", fromlist=["butter"]) and "ok")
    check("soundfile", lambda: __import__("soundfile").__libsndfile_version__)
    check("hidapi", lambda: f"{len(__import__('hid').enumerate())} dispositivos HID")
    check("pyaudiowpatch", lambda: __import__("pyaudiowpatch") and "importa", critical=sys.platform == "win32")
    check("dispositivos de audio", audio, critical=False)       # las máquinas de CI pueden no tener audio
    check("tkinter + tema", tk_theme)
    check("protocolo", protocol)
    check("efectos", lambda: len([make_effect(k, 0.5) for _, k in EFFECT_BUTTONS]))
    check("recursos", resources_ok, critical=dh.FROZEN)
    check("vDS modificado", vds_modified, critical=dh.FROZEN)
    ok = all(r["ok"] or not r.get("critical", True) for r in results)
    report = {"ok": ok, "version": dh.__version__, "frozen": dh.FROZEN, "results": results}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
    try:
        print(text)
    except Exception:
        pass
    return 0 if ok else 1


def attach_console():
    """El .exe no tiene consola propia: para --cli, usar la de quien lo llamó."""
    if sys.platform == "win32" and dh.FROZEN:
        try:
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stderr = sys.stdout
        except Exception:
            pass


def relaunch_elevated():
    """Vuelve a abrirse pidiendo administrador (UAC). True si lo pudo lanzar."""
    if dh.FROZEN:
        exe, params = sys.executable, subprocess.list2cmdline(sys.argv[1:])
    else:
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        params = subprocess.list2cmdline([os.path.abspath(__file__)] + sys.argv[1:])
    try:
        return ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1) > 32
    except Exception:
        return False


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "--self-test":
        attach_console()
        sys.exit(self_test(argv[1] if len(argv) > 1 else None))
    if argv and argv[0] == "--cli":
        attach_console()
        sys.exit(dh.main(argv[1:]))
    if argv and argv[0] in ("--version", "-V"):
        attach_console()
        print(dh.__version__)
        return
    if sys.platform == "win32" and not is_admin() and "--sin-elevar" not in argv:
        if relaunch_elevated():
            return
        # si el usuario no aceptó el UAC, seguimos con funciones limitadas

    def excepthook(t, v, tb):
        log("".join(traceback.format_exception(t, v, tb)))
        try:
            messagebox.showerror("DualSense Control", f"{t.__name__}: {v}\n\nDetalle en {LOG_PATH}")
        except Exception:
            pass
    sys.excepthook = excepthook
    log("--- inicio ---")
    app = App()
    app.report_callback_exception = excepthook
    app.mainloop()


if __name__ == "__main__":
    main()
