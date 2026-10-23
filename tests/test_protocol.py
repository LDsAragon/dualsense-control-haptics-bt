"""Pruebas del protocolo: lo que verificamos a mano durante el desarrollo, ahora automático.

Corren en cualquier sistema (no hace falta joystick ni Windows):  python -m pytest tests
"""
import os
import sys
import zlib

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
import dshaptics as dh  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ---------------------------------------------------------------------------
# Háptica Bluetooth (reporte 0x32 de SAxense)
# ---------------------------------------------------------------------------

def saxense_crc(data: bytes) -> int:
    """CRC tal cual está en SAxense.c (semilla ~0xEADA2D49 = estado tras procesar 0xA2)."""
    crc = (~0xEADA2D49) & 0xFFFFFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 & -(crc & 1) & 0xFFFFFFFF)
    return (~crc) & 0xFFFFFFFF


def test_report_matches_original_saxense_byte_for_byte():
    # saxense_ref.bin = salida del SAxense.c original con 5 bloques de entrada (i*7+3)&0xFF.
    # SAxense manda primero un reporte vacío; el reporte k lleva el bloque k-1 y el contador k.
    ref = open(os.path.join(FIXTURES, "saxense_ref.bin"), "rb").read()
    inp = bytes((i * 7 + 3) & 0xFF for i in range(64 * 5))
    assert len(ref) == 6 * dh.REPORT_LEN
    for k in range(1, 6):
        mine = dh.build_report(inp[64 * (k - 1):64 * k], 0, k)
        assert mine == ref[dh.REPORT_LEN * k:dh.REPORT_LEN * (k + 1)], f"reporte {k}"


def test_report_layout_and_crc():
    r = dh.build_report(bytes(range(64)), seq=5, counter=200)
    assert len(r) == 142 and r[0] == 0x32
    assert r[1] == 5 << 4
    assert r[2:4] == bytes([0x91, 7]) and r[4:11] == bytes([0xFE, 0, 0, 0, 0, 0xFF, 200])
    assert r[11:13] == bytes([0x92, 64]) and r[13:77] == bytes(range(64))
    assert int.from_bytes(r[138:], "little") == saxense_crc(r[:138])


def test_timing_is_exactly_3khz():
    assert dh.FRAMES / dh.PERIOD == pytest.approx(3000.0)


def test_to_s8_clips():
    y = dh.to_s8(np.array([[2.0, -2.0], [0.5, -0.5]]), 1.0)
    assert y.dtype == np.int8 and y.tolist() == [[127, -128], [64, -64]]


@pytest.mark.parametrize("rate", [44100, 48000, 96000])
def test_stream_resampler_does_not_drift(rate):
    # 20 s de audio en bloques irregulares tienen que dar exactamente 60000 frames a 3 kHz
    t = np.arange(rate * 20) / rate
    x = np.stack([np.sin(2 * np.pi * 200 * t)] * 2, 1).astype(np.float32)
    rs = dh.StreamResampler(rate)
    rng = np.random.default_rng(0)
    i = n = 0
    while i < len(x):
        k = int(rng.integers(50, 900))
        n += len(rs.process(x[i:i + k]))
        i += k
    assert abs(n - 60000) <= 1


def test_fifo_live_prefill_and_drop_old():
    f = dh.Fifo(300, drop_old=True)
    f.push(np.ones((100, 2), np.int8))
    assert not f.pop(32).any()                 # todavía llenando: silencio
    f.push(np.ones((200, 2), np.int8))
    assert f.pop(32).all()
    f.push(np.ones((1000, 2), np.int8))
    assert f.n <= 300                          # en vivo descarta lo viejo


# ---------------------------------------------------------------------------
# Gatillos adaptativos (codificación de Nielk1)
# ---------------------------------------------------------------------------

def test_trigger_effects_encoding():
    assert dh.trigger_feedback(0, 8) == bytes.fromhex("21ff03ffffff3f00000000")
    assert dh.trigger_weapon(2, 6, 8) == bytes.fromhex("2544000700000000000000")
    assert dh.trigger_vibration(0, 8, 40) == bytes.fromhex("26ff03ffffff3f00002800")
    assert dh.trigger_off() == bytes([0x05]) + bytes(10)
    assert dh.trigger_feedback(5, 1)[1:3] == bytes([0xE0, 0x03])      # zonas 5-9


def test_trigger_state_and_reports():
    st = dh.trigger_state(right=dh.trigger_feedback(), left=dh.trigger_weapon())
    assert len(st) == 47 and st[0] == 0x0C
    assert st[10:21] == dh.trigger_feedback() and st[21:32] == dh.trigger_weapon()
    usb = dh.trigger_report(st, bluetooth=False)
    assert len(usb) == 48 and usb[0] == 0x02 and usb[1:] == st
    bt = dh.trigger_report(st, bluetooth=True, seq=3)
    assert len(bt) == 78 and bt[0] == 0x31 and bt[1] == 0x30 and bt[2] == 0x10 and bt[3:50] == st
    assert int.from_bytes(bt[74:], "little") == zlib.crc32(b"\xA2" + bt[:74])
    only_right = dh.trigger_state(right=dh.trigger_off())
    assert only_right[0] == 0x04 and only_right[21:32] == bytes(11)


# ---------------------------------------------------------------------------
# Luces e identificación
# ---------------------------------------------------------------------------

def test_light_state():
    st = dh.light_state((0xFF, 0x40, 0x00), 2)
    assert st[1] == 0x14 and st[43] == 0x0A and st[44:47] == bytes([0xFF, 0x40, 0x00])
    assert dh.light_state(player=0)[43] == 0 and dh.light_state(player=0)[1] == 0x10
    assert [dh.PLAYER_PATTERNS[i] for i in (1, 2, 3, 4)] == [0x04, 0x0A, 0x15, 0x1B]


def test_mac_from_pairing_report():
    rep = bytes([0x09, 0xF3, 0xEB, 0x03, 0x9A, 0x3A, 0x14]) + bytes(13)
    assert dh.mac_from_pairing(rep) == "14:3a:9a:03:eb:f3"
    assert dh.mac_from_pairing(b"") == "" and dh.mac_from_pairing(bytes([0x05] * 20)) == ""


def test_parse_color():
    assert dh.parse_color("#FF4000") == (255, 64, 0) and dh.parse_color("00ff00") == (0, 255, 0)
    with pytest.raises(ValueError):
        dh.parse_color("#fff")


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(dh, "CONFIG_PATH", str(tmp_path / "config" / "joysticks.json"))
    assert dh.load_config() == {}
    dh.save_config({"14:3a:9a:03:eb:f3": {"name": "Lu", "color": "#ff0000", "player": 2}})
    assert dh.load_config()["14:3a:9a:03:eb:f3"]["name"] == "Lu"


# ---------------------------------------------------------------------------
# Batería y apagado
# ---------------------------------------------------------------------------

def test_decode_battery():
    r = bytearray(78); r[0] = 0x31; r[54] = 0x03
    assert dh.decode_battery(bytes(r)) == (35, "descargando")
    r[54] = 0x18
    assert dh.decode_battery(bytes(r)) == (85, "cargando")
    u = bytearray(64); u[0] = 0x01; u[53] = 0x2A
    assert dh.decode_battery(bytes(u)) == (100, "carga completa")
    assert dh.decode_battery(b"\x01\x02") is None


def test_bluetooth_structs_match_windows_sdk():
    import ctypes
    find_radio, search, info = dh._bt_structs()
    assert ctypes.sizeof(search) == 40 and search.hRadio.offset == 32
    assert ctypes.sizeof(info) == 560 and info.Address.offset == 8 and info.szName.offset == 64
