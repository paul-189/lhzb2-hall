#!/usr/bin/env python3
# 给 MAME 0.289 的 dynax 驱动注入游戏厅 hall API（mjelctrn 电子基盘专用）。
# 改两个文件：dynax.h（dynax_state 基类加 public 方法）+ dynax.cpp（init 记 s_hall + 文件尾 extern C）。
# 口径来源：本机 MAME 0.289 Lua 实证（scratch/dynax_cal*.lua）：
#   信用主地址 0x7e30（u8，二进制；0->1->4->14 跟踪；镜像 0x7d33/7d49/7d51 同值）。
#   投币 COINS bit0x40(active-low)；开始 KEY0 bit0x20；押分 KEY1 bit0x20；收分 KEY4 bit0x02。
#   屏 visarea(0,507,16,255)=508x240，ROT180；bitmap_ind16 + palette.pen_color。
# 与 IGS(68000) 完全不同：Z80 8位总线、ioport 矩阵 KEY0-4(P1)/KEY5-9(P2)、COINS 独立口。
import sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
H = ROOT + "/src/mame/dynax/dynax.h"
C = ROOT + "/src/mame/dynax/dynax.cpp"

def patch(path, old, new, label):
    s = open(path, encoding="utf-8").read()
    if new.strip() and new.split("\n")[0].strip() in s and label.startswith("tail"):
        print("SKIP already:", label); return
    n = s.count(old)
    if n != 1:
        print("ANCHOR FAIL:", label, "count=", n); sys.exit(2)
    open(path, "w", encoding="utf-8", newline="\n").write(s.replace(old, new))
    print("OK:", label)

# ---- 1) dynax.h：基类加 hall 方法（m_coins 之后，恢复 protected）----
H_METHODS = """\toptional_ioport m_coins;

public:
\t/* --- gamebar hall API (Dynax mjelctrn) --- */
\tuint8_t hall_ram8(uint32_t a) { return m_maincpu->space(AS_PROGRAM).read_byte(a); }
\tuint16_t hall_ram16(uint32_t a) { return (uint16_t)hall_ram8(a) | ((uint16_t)hall_ram8(a + 1) << 8); }
\tvoid hall_field(int bank, uint8_t bit, int val) {
\t\toptional_ioport *p = nullptr;
\t\tif (bank < 0) p = &m_coins;
\t\telse if (bank < 5) p = &m_io_key[0][bank];
\t\telse if (bank < 10) p = &m_io_key[1][bank - 5];
\t\tif (p && p->found()) (*p)->field(bit)->set_value(val ? 1 : 0);
\t}
\tvoid hall_coin() { hall_field(-1, 0x40, 1); hall_field(-1, 0x40, 0); }
\tint hall_dip(int idx, uint8_t bit) {
\t\tif (idx < 0 || idx >= 5 || !m_dsw[idx].found()) return -1;
\t\treturn (m_dsw[idx]->read() & bit) ? 1 : 0;
\t}
\tuint8_t hall_credit() { return hall_ram8(0x7e30); }
\tint hall_frame_capture(uint8_t *dst, int cap) {
\t\tif (!m_screen.found() || !m_palette.found()) return 0;
\t\tconst rectangle &va = m_screen->visible_area();
\t\tint W = va.width(), H = va.height();
\t\tif (cap < W * H * 4) return 0;
\t\tbitmap_ind16 &bm = m_screen->curbitmap();
\t\tpalette_device &pal = *m_palette;
\t\tfor (int y = 0; y < H; y++) {
\t\t\tfor (int x = 0; x < W; x++) {
\t\t\t\tint sx = va.right() - x;   /* ROT180 */
\t\t\t\tint sy = va.bottom() - y;
\t\t\t\trgb_t c = pal.pen_color(bm.pix(sy, sx));
\t\t\t\tuint8_t *p = dst + (y * W + x) * 4;
\t\t\t\tp[0] = c.r(); p[1] = c.g(); p[2] = c.b(); p[3] = 255;
\t\t\t}
\t\t}
\t\treturn W * H * 4;
\t}
protected:
"""
patch(H, "\toptional_ioport m_coins;\n", H_METHODS, "dynax.h hall methods")

# ---- 2) dynax.cpp：init_mjelct3 记 s_hall + VIDEO_ALWAYS_UPDATE ----
patch(C,
      "void dynax_adpcm_state::init_mjelct3()\n{\n",
      "static dynax_state *s_hall = nullptr;\n"
      "void dynax_adpcm_state::init_mjelct3()\n{\n"
      "\ts_hall = this;\n"
      "\tif (m_screen.found()) m_screen->set_video_always_update(true);\n",
      "init_mjelct3 s_hall")

# ---- 3) dynax.cpp 文件尾：extern C 导出 ----
TAIL = """
/* ===== gamebar hall API exports (mjelctrn / Dynax) ===== */
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define HALL_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define HALL_EXPORT
#endif
extern "C" {
HALL_EXPORT int hall_ready() { return s_hall ? 1 : 0; }
HALL_EXPORT void hall_coin() { if (s_hall) s_hall->hall_coin(); }
HALL_EXPORT void hall_key(int bank, int bit, int val) { if (s_hall) s_hall->hall_field(bank, (uint8_t)bit, val); }
HALL_EXPORT unsigned int hall_ram16(unsigned int a) { return s_hall ? s_hall->hall_ram16(a) : 0xffff; }
HALL_EXPORT unsigned int hall_ram8(unsigned int a) { return s_hall ? s_hall->hall_ram8(a) : 0xff; }
HALL_EXPORT int hall_dip(int idx, int bit) { return s_hall ? s_hall->hall_dip(idx, (uint8_t)bit) : -1; }
HALL_EXPORT unsigned int hall_credit() { return s_hall ? s_hall->hall_credit() : 0; }
HALL_EXPORT unsigned int hall_frame() { return (508u << 16) | 240u; }
HALL_EXPORT int hall_frame_capture(unsigned char *dst, int cap) { return s_hall ? s_hall->hall_frame_capture(dst, cap) : 0; }
}
"""
s = open(C, encoding="utf-8").read()
if "gamebar hall API exports (mjelctrn" in s:
    print("SKIP already: tail")
else:
    open(C, "a", encoding="utf-8", newline="\n").write(TAIL)
    print("OK: tail exports")
print("ALL PATCHES DONE (mjelct3hall / Dynax)")