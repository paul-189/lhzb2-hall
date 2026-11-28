#!/usr/bin/env python3
# v3: hall_field 改成员访问（ioport_manager::port 是私有）+ 新增 m_io_test
# 给官方 MAME 0.289 的 src/mame/igs/igs_m027.cpp 打"厅用接口"补丁（龙虎大满贯 lhdmg / IGS027 ARM）。
# 接口与 lhzb2 厅同名（hall_ready/ram8/16/key/frame_capture...），页面代码可直接复用。
# RAM 直读写 m_nvram 共享指针（0x18000000.. mirror 32KB），不走总线、无副作用。
# bank: -1 → TEST 口（投币 0x10），0..4 → KEY0..KEY4。
import io, sys

PATH = "src/mame/igs/igs_m027.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

A1 = "\trequired_device<igs027a_cpu_device> m_maincpu;"
H1 = A1 + """

	// ===== hall api (added) =====
public:
	u8  hall_m027_ram8(u32 a) const
	{
		u32 off = a & 0x7fff;
		return (m_nvram[off >> 2] >> (8 * (off & 3))) & 0xff;
	}
	void hall_m027_ram8_w(u32 a, u8 v)
	{
		u32 off = a & 0x7fff;
		u32 lane = (off & 3) * 8;
		u32 word = m_nvram[off >> 2];
		word = (word & ~(0xffu << lane)) | (u32(v) << lane);
		m_nvram[off >> 2] = word;
	}
	// bank<0 → TEST 口；bank 0..4 → KEY0..KEY4；mask 定位字段；val 字段逻辑值
	bool hall_field(int bank, u8 mask, s32 val)
	{
		ioport_port *p = (bank < 0) ? m_io_test : (bank < 5 ? m_io_kbd[bank] : nullptr);
		if (!p) return false;
		ioport_field *f = p->field(mask);
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	void hall_coin() { hall_field(-1, 0x10, 1); hall_field(-1, 0x10, 0); }
	int hall_frame_number() const { return int(m_screen->frame_number()); }
	int hall_frame_capture();
	static igs_m027_state *s_hall;
	static u32 s_frame_buf[512 * 256];
	static int s_frame_w, s_frame_h;
	// ===== hall api end ====="""


# ---- 1b) 新增 TEST 口成员（构造初始化列表 + 声明）----
A1B = "\t\tm_io_misc(*this, \"MISC\"),"
H1B = "\t\tm_io_test(*this, \"TEST\"),\n" + A1B
A1C = "\toptional_ioport m_io_misc;"
H1C = "\trequired_ioport m_io_test;\n" + A1C

A2 = "void igs_m027_state::init_slqz3()\n{\n\tslqz3_decrypt(machine());"
H2 = ("void igs_m027_state::init_slqz3()\n{\n"
      "\ts_hall = this;   // hall api\n"
      "\tm_screen->set_video_attributes(VIDEO_ALWAYS_UPDATE);   // A 路：-video none 下屏幕位图仍每帧更新\n"
      "\tslqz3_decrypt(machine());")

TAIL = """

// ===== hall api (added): Emscripten/JS 入口 =====
#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#endif
#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

igs_m027_state *igs_m027_state::s_hall = nullptr;
u32 igs_m027_state::s_frame_buf[512 * 256];
int igs_m027_state::s_frame_w = 0;
int igs_m027_state::s_frame_h = 0;

// A 路帧捕获：屏幕位图(ind16 索引色)经调色板转 RGBA，纯 CPU，无 GL。
int igs_m027_state::hall_frame_capture()
{
	screen_bitmap &cb = m_screen->curbitmap();
	if (cb.format() != BITMAP_FORMAT_IND16) return -2;
	bitmap_ind16 &bm = cb.as_ind16();
	const int w = bm.width(), h = bm.height();
	if (w <= 0 || h <= 0 || w * h > 512 * 256) return -3;
	device_palette_interface &pal = m_screen->palette();
	const u32 n = pal.entries();
	for (int y = 0; y < h; y++)
	{
		const u16 *row = &bm.pix(y, 0);
		u32 *out = s_frame_buf + y * w;
		for (int x = 0; x < w; x++)
		{
			const u32 pen = row[x];
			const u32 c = (pen < n) ? u32(pal.pen_color(pen)) : 0xff000000u;
			out[x] = 0xff000000u | ((c & 0xffu) << 16) | (c & 0xff00u) | ((c >> 16) & 0xffu);
		}
	}
	s_frame_w = w; s_frame_h = h;
	return w * h;
}

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready()      { return igs_m027_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a)  { return igs_m027_state::s_hall ? igs_m027_state::s_hall->hall_m027_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a)
{
	if (!igs_m027_state::s_hall) return -1;
	return igs_m027_state::s_hall->hall_m027_ram8(a) | (igs_m027_state::s_hall->hall_m027_ram8(a + 1) << 8);
}
EMSCRIPTEN_KEEPALIVE int hall_ram8_write(u32 a, int v)
{ if (!igs_m027_state::s_hall) return -1; igs_m027_state::s_hall->hall_m027_ram8_w(a, (u8)v); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram16_write(u32 a, int v)
{
	if (!igs_m027_state::s_hall) return -1;
	igs_m027_state::s_hall->hall_m027_ram8_w(a, (u8)(v & 0xff));
	igs_m027_state::s_hall->hall_m027_ram8_w(a + 1, (u8)((v >> 8) & 0xff));
	return 0;
}
EMSCRIPTEN_KEEPALIVE int hall_coin()       { if (!igs_m027_state::s_hall) return -1; igs_m027_state::s_hall->hall_coin(); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int bank, int mask, int val)
{
	return (igs_m027_state::s_hall && igs_m027_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1;
}
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return igs_m027_state::s_hall ? igs_m027_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr()  { return u32(uintptr_t(igs_m027_state::s_frame_buf)); }
EMSCRIPTEN_KEEPALIVE int hall_frame_w()    { return igs_m027_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h()    { return igs_m027_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs_m027_state::s_hall ? igs_m027_state::s_hall->hall_frame_number() : -1; }
}
// ===== hall api end =====
"""

for name, a in (("锚1 m_maincpu 声明", A1), ("锚1b TEST初始化", A1B), ("锚1c m_io_misc声明", A1C), ("锚2 init_slqz3", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1）" % (name, src.count(a))); sys.exit(2)
if "hall api" in src:
    print("FAIL: 补丁疑似已应用"); sys.exit(2)
src = src.replace(A1, H1, 1)
src = src.replace(A1B, H1B, 1)
src = src.replace(A1C, H1C, 1)
src = src.replace(A2, H2, 1)
src += TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: m027 厅接口补丁(含帧导出)已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
