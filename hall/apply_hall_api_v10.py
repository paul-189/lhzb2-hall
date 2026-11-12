#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/igs/igs017.cpp 打"厅用接口"补丁
# v10 = v3 稳定逻辑（无 GL）+ A 路帧导出：
#   1) init_lhzb2 里给屏幕设 VIDEO_ALWAYS_UPDATE —— 绕过 update_partial 的
#      frameskip / render().is_live 两道闸（screen.cpp:1151-1166），
#      使 -video none 下扫描线/vblank 定时器仍每帧把画面写进屏幕位图。
#   2) hall_frame_capture()：读 curbitmap()（ind16 索引位图）+ 调色板 pen_color()，
#      转成 canvas ImageData 字节序(R,G,B,A) 的静态 RGBA 缓冲，导出指针/宽/高/帧号。
# 依据（全部本机源码核对，mame0289 官方 tar）：
#   - screen.h:369 set_video_attributes 公开；screen.h:70 VIDEO_ALWAYS_UPDATE=0x0080
#   - screen.h:378 curbitmap() 公开；screen.h:400 frame_number() 公开
#   - screen.cpp:1781-1796 双缓冲交换只在 render().is_live 时发生 ⇒ -video none 下
#     m_curbitmap/m_curtexture 恒为 0，curbitmap() 读到的就是正在写的那块
#   - igs017_igs031.h:62 screen_update 是 bitmap_ind16（索引色），故需查调色板
#   - dipalette.h pen_color/entries 公开；palette.h entry_color 越界返回黑
#   - rgb_t = 0xAARRGGBB；wasm 小端 ⇒ 存 0xAABBGGRR 才是 ImageData 的 R,G,B,A 字节序
# 锚点不对就当场失败，绝不静默改坏。
import io, sys

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内加公开方法（锚：m_maincpu 成员声明行）----
A1 = "\trequired_device<cpu_device> m_maincpu;"
HALL_METHODS = A1 + """

	// ===== hall api (added) =====
public:
	u8  hall_ram8(u32 a) const  { return m_maincpu->space(AS_PROGRAM).read_byte(a); }
	u16 hall_ram16(u32 a) const { return m_maincpu->space(AS_PROGRAM).read_word(a); }

	// bank<0 → COINS 口；bank 0..4 → KEY0..KEY4；mask 定位字段；val 为字段逻辑值
	bool hall_field(int bank, u8 mask, s32 val)
	{
		ioport_field *f = nullptr;
		if (bank < 0)      { if (m_io_coins)     f = m_io_coins->field(mask); }
		else if (bank < 5) { if (m_io_key[bank]) f = m_io_key[bank]->field(mask); }
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	// 一枚币：按下再松开（PORT_IMPULSE(5) 由 MAME 自己整形）
	void hall_coin() { hall_field(-1, 0x08, 1); hall_field(-1, 0x08, 0); }
	static igs017_state *s_hall;

	// ===== hall frame export (A 路：纯 CPU，无 GL) =====
	int hall_frame_capture();                       // 索引位图+调色板 → RGBA 静态缓冲；返回像素数，<0 失败
	u64 hall_frame_number() const { return m_screen->frame_number(); }
	static u32 s_frame_buf[512 * 256];              // 屏幕 set_size(512,256)，512KB
	static int s_frame_w, s_frame_h;
	// ===== hall api end ====="""

# ---- 2) init_lhzb2() 里记下机器实例 + 打开屏幕常更新 ----
A2 = "void igs017_state::init_lhzb2()\n{\n\tconst int rom_size = memregion(\"maincpu\")->bytes();"
H2 = ("void igs017_state::init_lhzb2()\n{\n"
      "\ts_hall = this;   // hall api\n"
      "\tm_screen->set_video_attributes(VIDEO_ALWAYS_UPDATE);   // A 路：-video none 下屏幕位图仍每帧更新\n"
      "\tconst int rom_size = memregion(\"maincpu\")->bytes();")

# ---- 3) 文件末尾：导出给 JS 的 C 接口 ----
TAIL = """

// ===== hall api (added): Emscripten/JS 入口 =====
#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>   // EMSCRIPTEN_KEEPALIVE 的真身（v2 漏了这个，符号被剥掉）
#endif
#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

igs017_state *igs017_state::s_hall = nullptr;
u32 igs017_state::s_frame_buf[512 * 256];
int igs017_state::s_frame_w = 0;
int igs017_state::s_frame_h = 0;

// A 路帧捕获：把当前屏幕位图（ind16 索引色）经调色板转成 RGBA。
// 纯 CPU 读内存，不依赖任何视频后端/GL 上下文。
int igs017_state::hall_frame_capture()
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
			// rgb_t=0xAARRGGBB → 小端内存字节序 R,G,B,A ⇒ 存 0xAABBGGRR
			out[x] = 0xff000000u | ((c & 0xffu) << 16) | (c & 0xff00u) | ((c >> 16) & 0xffu);
		}
	}
	s_frame_w = w; s_frame_h = h;
	return w * h;
}

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready()      { return igs017_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a)  { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a) { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin()       { if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_coin(); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int bank, int mask, int val)
{
	return (igs017_state::s_hall && igs017_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1;
}
// 机台关键量：$500060 状态字 / $500202 信用 / $50020d 押分档
EMSCRIPTEN_KEEPALIVE int hall_state_word() { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(0x500060) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_credit()     { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(0x500202) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_bet_level()  { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram8(0x50020d) : -1; }
// A 路帧导出：JS 每帧调 capture，再用 ptr/w/h 从 HEAPU8 取 RGBA 画到 canvas
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return igs017_state::s_hall ? igs017_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr()  { return u32(uintptr_t(igs017_state::s_frame_buf)); }
EMSCRIPTEN_KEEPALIVE int hall_frame_w()    { return igs017_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h()    { return igs017_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs017_state::s_hall ? int(igs017_state::s_hall->hall_frame_number()) : -1; }
}
// ===== hall api end =====
"""

for name, a in (("锚1 m_maincpu 成员", A1), ("锚2 init_lhzb2 头部", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1 次）" % (name, src.count(a))); sys.exit(2)

for need in ("optional_ioport m_io_coins;", "optional_ioport_array<5> m_io_key;",
             "required_device<screen_device> m_screen;"):
    if need not in src:
        print("FAIL: 类里缺少预期成员:", need); sys.exit(3)

src = src.replace(A1, HALL_METHODS, 1)
src = src.replace(A2, H2, 1)
src += TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: 补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
