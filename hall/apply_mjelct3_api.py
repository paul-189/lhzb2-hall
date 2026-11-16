#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/dynax/dynax.{h,cpp} 打"厅用接口"补丁（电子基盘 mjelctrn/mjelct3）。
# 借鉴 igs011 lhb2 补丁（静态帧缓冲+无参 capture+ptr/w/h+mask 签名+DIP 读写），适配 Dynax Z80：
#   类在 dynax.h：dynax_state 基类含 m_maincpu/m_screen/m_palette/m_io_key[2]/m_dsw/m_coins。
#   输入 bank<0→m_coins(COIN1 bit0x40)；0..4→m_io_key[0][bank]=KEY0..4(P1)；5..9→m_io_key[1][bank-5]。
#   信用 0x7e30(u8 二进制,cal4/cal5 实证 0->1->4->14)。屏 visarea(0,507,16,255)=508x240,ROT180,IND16。
#   init 锚点 init_mjelct3(dynax.cpp:6287)。锚点不对当场失败。
import io, sys
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
HP = ROOT + "/src/mame/dynax/dynax.h"
CP = ROOT + "/src/mame/dynax/dynax.cpp"
h = io.open(HP, encoding="utf-8").read()
c = io.open(CP, encoding="utf-8").read()
oh, oc = h, c

A1 = "\toptional_ioport m_coins;"
HALL = A1 + """

public:
\t// ===== hall api (added, Dynax mjelctrn) =====
\tu8  hall_ram8(u32 a) const  { return m_maincpu->space(AS_PROGRAM).read_byte(a); }
\tu16 hall_ram16(u32 a) const { return u16(hall_ram8(a)) | (u16(hall_ram8(a + 1)) << 8); }
\tbool hall_field(int bank, u8 mask, s32 val)
\t{
\t\tioport_field *f = nullptr;
\t\tif (bank < 0)       { if (m_coins)           f = m_coins->field(mask); }
\t\telse if (bank < 5)  { if (m_io_key[0][bank]) f = m_io_key[0][bank]->field(mask); }
\t\telse if (bank < 10) { if (m_io_key[1][bank-5]) f = m_io_key[1][bank-5]->field(mask); }
\t\tif (!f) return false;
\t\tf->set_value(val);
\t\treturn true;
\t}
\tvoid hall_coin() { hall_field(-1, 0x40, 1); hall_field(-1, 0x40, 0); }
\tstatic dynax_state *s_hall;
\tint hall_frame_capture();
\tu64 hall_frame_number() const { return m_screen->frame_number(); }
\tstatic u32 s_frame_buf[508 * 240];
\tstatic int s_frame_w, s_frame_h;
\tbool hall_dip(int idx, u32 mask, u32 val)
\t{
\t\tif (idx < 0 || idx >= 5 || !m_dsw[idx]) return false;
\t\tioport_field *f = m_dsw[idx]->field(mask);
\t\tif (!f) return false;
\t\tf->set_value(val);
\t\tf->live().value = (f->live().value & ~f->mask()) | ((ioport_value)val & f->mask());
\t\treturn true;
\t}
\tint hall_dip_get(int idx, u32 mask)
\t{
\t\tif (idx < 0 || idx >= 5 || !m_dsw[idx]) return -1;
\t\tioport_field *f = m_dsw[idx]->field(mask);
\t\tif (!f) return -1;
\t\treturn int(f->live().value & f->mask());
\t}
protected:
\t// ===== hall api end ====="""
A2 = "void dynax_adpcm_state::init_mjelct3()\n{\n"
H2 = ("void dynax_adpcm_state::init_mjelct3()\n{\n"
      "\ts_hall = this;   // hall api\n"
      "\tif (m_screen.found()) m_screen->set_video_attributes(VIDEO_ALWAYS_UPDATE);\n")

TAIL = """

// ===== hall api (added): Emscripten/JS 入口 (Dynax mjelctrn) =====
#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#endif
#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

dynax_state *dynax_state::s_hall = nullptr;
u32 dynax_state::s_frame_buf[508 * 240];
int dynax_state::s_frame_w = 0;
int dynax_state::s_frame_h = 0;

int dynax_state::hall_frame_capture()
{
\tif (!m_screen.found()) return -1;
\tscreen_bitmap &cb = m_screen->curbitmap();
\tif (cb.format() != BITMAP_FORMAT_IND16) return -2;
\tbitmap_ind16 &bm = cb.as_ind16();
\tconst rectangle &va = m_screen->visible_area();
\tconst int w = va.width(), h = va.height();
\tif (w <= 0 || h <= 0 || w * h > 508 * 240) return -3;
\tdevice_palette_interface &pal = m_screen->palette();
\tconst u32 n = pal.entries();
\tfor (int y = 0; y < h; y++)
\t{
\t\tu32 *out = s_frame_buf + y * w;
\t\tconst int sy = va.bottom() - y;
\t\tfor (int x = 0; x < w; x++)
\t\t{
\t\t\tconst int sx = va.right() - x;
\t\t\tconst u32 pen = bm.pix(sy, sx);
\t\t\tconst u32 cc = (pen < n) ? u32(pal.pen_color(pen)) : 0xff000000u;
\t\t\tout[x] = 0xff000000u | ((cc & 0xffu) << 16) | (cc & 0xff00u) | ((cc >> 16) & 0xffu);
\t\t}
\t}
\ts_frame_w = w; s_frame_h = h;
\treturn w * h;
}

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready()      { return dynax_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a)  { return dynax_state::s_hall ? dynax_state::s_hall->hall_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a) { return dynax_state::s_hall ? dynax_state::s_hall->hall_ram16(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin()       { if (!dynax_state::s_hall) return -1; dynax_state::s_hall->hall_coin(); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int bank, int mask, int val)
{ return (dynax_state::s_hall && dynax_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_state_word() { return 0; }
EMSCRIPTEN_KEEPALIVE int hall_credit()     { return dynax_state::s_hall ? dynax_state::s_hall->hall_ram8(0x7e30) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_bet_level()  { return 0; }
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return dynax_state::s_hall ? dynax_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr()  { return u32(uintptr_t(dynax_state::s_frame_buf)); }
EMSCRIPTEN_KEEPALIVE int hall_frame_w()    { return dynax_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h()    { return dynax_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return dynax_state::s_hall ? int(dynax_state::s_hall->hall_frame_number()) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_dip(int idx, int mask, int val)
{ return (dynax_state::s_hall && dynax_state::s_hall->hall_dip(idx, (u32)mask, (u32)val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_dip_get(int idx, int mask)
{ return dynax_state::s_hall ? dynax_state::s_hall->hall_dip_get(idx, (u32)mask) : -1; }
}
// ===== hall api end =====
"""

for name, s, a in (("锚1 dynax.h m_coins", h, A1), ("锚2 init_mjelct3 头部", c, A2)):
    if s.count(a) != 1:
        print("FAIL: %s 命中 %d 次" % (name, s.count(a))); sys.exit(2)
for need in ("optional_ioport m_coins;", "optional_ioport_array<5> m_io_key[2];",
             "optional_device<screen_device> m_screen;", "optional_ioport_array<5> m_dsw;"):
    if need not in h:
        print("FAIL: dynax.h 缺成员:", need); sys.exit(3)
h = h.replace(A1, HALL, 1)
c = c.replace(A2, H2, 1)
c += TAIL
io.open(HP, "w", encoding="utf-8", newline="\n").write(h)
io.open(CP, "w", encoding="utf-8", newline="\n").write(c)
print("OK: mjelct3 hall dynax.h %d->%d, dynax.cpp %d->%d" % (len(oh), len(h), len(oc), len(c)))