// Pruebas contra el código real de vDS (commit de vds-mods/VDS_COMMIT + vds-mods/*.patch).
//  1. 0001-silenciar-parlante: con el archivo speaker-muted, el parlante decodificado queda en 0
//     y la háptica no cambia; sin el archivo, vuelve el sonido.
//  2. Los reportes que arma dshaptics (gatillos y luces) pasan por DsOutputState y salen por
//     Bluetooth (0x31) con los bytes intactos y el CRC correcto.
// Uso: test_vds_mods <dir_temporal> <usb_triggers.bin> <usb_off.bin> <usb_light.bin>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <thread>
#include <vector>
#include <opus/opus.h>
#include <zlib.h>
#include "vds_protocol.hh"
using namespace vds;

static int failures = 0;
#define CHECK(cond, ...) do { if (!(cond)) { ++failures; std::printf("FALLA: "); std::printf(__VA_ARGS__); std::printf("\n"); } else { std::printf("ok: "); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

static std::vector<uint8_t> pcm(int frames, int start) {
  std::vector<uint8_t> b(frames * 8);
  for (int i = 0; i < frames; ++i) {
    double t = (start + i) / 48000.0;
    int16_t v[4] = {(int16_t)(12000 * std::sin(2 * M_PI * 440 * t)), (int16_t)(12000 * std::sin(2 * M_PI * 440 * t)),
                    (int16_t)(20000 * std::sin(2 * M_PI * 120 * t)), (int16_t)(20000 * std::sin(2 * M_PI * 120 * t))};
    for (int c = 0; c < 4; ++c) { b[i * 8 + c * 2] = v[c] & 0xff; b[i * 8 + c * 2 + 1] = (uint16_t)v[c] >> 8; }
  }
  return b;
}

struct Levels { double speaker = 0, haptics = 0; };
static Levels run_audio() {
  PcmAudioExtractor ex; int err = 0;
  OpusDecoder *dec = opus_decoder_create(48000, 2, &err);
  Levels lv; int n = 0, pos = 0;
  for (int k = 0; k < 60; ++k) {
    auto chunks = ex.push_usb_audio(pcm(480, pos)); pos += 480;
    for (auto &c : chunks) {
      opus_int16 out[480 * 2 * 3];
      int f = opus_decode(dec, c.speaker.data(), (int)c.speaker.size(), out, 480 * 3, 0);
      if (++n > 10) {
        for (int i = 0; i < f * 2; ++i) lv.speaker = std::max(lv.speaker, (double)std::abs(out[i]));
        for (auto h : c.haptics) lv.haptics = std::max(lv.haptics, (double)std::abs(h));
      }
    }
  }
  opus_decoder_destroy(dec);
  return lv;
}

static std::vector<uint8_t> rd(const char *p) {
  std::ifstream f(p, std::ios::binary);
  return {std::istreambuf_iterator<char>(f), {}};
}

static bool crc_ok(const BtStateReport &r) {
  unsigned char a2 = 0xa2; uLong c = crc32(0, &a2, 1); c = crc32(c, r.data(), 74);
  unsigned got = r[74] | r[75] << 8 | r[76] << 16 | (unsigned)r[77] << 24;
  return got == (unsigned)c;
}

int main(int argc, char **argv) {
  if (argc < 5) { std::printf("uso: %s dir usb_triggers.bin usb_off.bin usb_light.bin\n", argv[0]); return 2; }
  // --- 1. parlante (el flag se lee de VDS_SPEAKER_MUTE_FLAG, que el script de prueba define) ---
  std::filesystem::path flag = std::filesystem::path(argv[1]) / "speaker-muted";
  std::filesystem::remove(flag);
  Levels a = run_audio();
  std::ofstream(flag).put('1');
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  Levels b = run_audio();
  std::filesystem::remove(flag);
  std::this_thread::sleep_for(std::chrono::milliseconds(300));
  Levels c = run_audio();
  CHECK(a.speaker > 5000, "sin silencio el parlante suena (pico %.0f)", a.speaker);
  CHECK(b.speaker == 0, "con speaker-muted el parlante queda en 0 (pico %.0f)", b.speaker);
  CHECK(a.haptics > 20 && b.haptics == a.haptics, "la háptica no cambia (%.0f -> %.0f)", a.haptics, b.haptics);
  CHECK(c.speaker > 5000, "al quitar el archivo vuelve el sonido (pico %.0f)", c.speaker);

  // --- 2. gatillos y luces a través de DsOutputState ---
  DsOutputState st;
  auto trig = rd(argv[2]), off = rd(argv[3]), light = rd(argv[4]);
  CHECK(st.apply_usb_output_report(trig), "vDS acepta el reporte de gatillos de dshaptics");
  auto r = st.build_bt_state_report();
  CHECK(r[0] == 0x31 && r[2] == 0x10 && crc_ok(r), "sale como 0x31 con CRC correcto");
  CHECK(std::equal(trig.begin() + 1 + 10, trig.begin() + 1 + 32, r.begin() + 3 + 10), "los 22 bytes de los gatillos llegan intactos");
  CHECK(st.apply_usb_output_report(off), "vDS acepta el apagado de gatillos");
  r = st.build_bt_state_report();
  CHECK(r[3 + 10] == 0x05 && r[3 + 21] == 0x05, "gatillos en Off (0x05)");
  CHECK(st.apply_usb_output_report(light), "vDS acepta el reporte de luces");
  r = st.build_bt_state_report();
  CHECK(r[3 + 43] == light[1 + 43] && r[3 + 44] == light[1 + 44] && r[3 + 45] == light[1 + 45] && r[3 + 46] == light[1 + 46] && crc_ok(r),
        "color %02x%02x%02x y LEDs 0x%02x llegan intactos", r[3 + 44], r[3 + 45], r[3 + 46], r[3 + 43]);

  std::printf("%s (%d fallas)\n", failures ? "HAY FALLAS" : "TODO OK", failures);
  return failures ? 1 : 0;
}
