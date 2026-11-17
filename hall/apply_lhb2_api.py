#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/igs/igs011.cpp 打"厅用接口"补丁（搓牌高手 lhb2cpgs）。
# 借鉴 igs017 的 v10(帧导出/输入/ram 读) + v12(拨码)，适配 igs011_oki_state：
#   - 类锚点 = oki 类 m_io_key（private）；hall 方法加 public: 后可访问基类 protected 成员
#     （m_maincpu/m_screen/m_palette/m_io_coin/m_io_dsw 均 protected，igs011.cpp:122-137 实证）。
#   - coin 口 = m_io_coin（COIN bit0=投币，bit5=退分），与 igs017 的 m_io_coins(bit3) 不同。
#   - 屏幕 set_size(512,260)（igs011.cpp:3627），出画 IND16，调色板 2048 项(8层x256,
#     PALETTE xBGR_555 0x2000/4)，pen=layerpix|(pri<<8) 用全 16 位索引（不能 &0xff）。
#   - RAM 0x100000（≠igs017 0x500000）；信用候选 0x100066（投3币 0->3 实证，lhb2_credit4）。
#   - init 锚点 = init_lhb2cpgs（igs011.cpp:1996）。
# 锚点不对就当场失败，绝不静默改坏。
import io, sys

PATH = "src/mame/igs/igs011.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) oki 类内加公开方法（锚：m_io_key 成员声明行，唯一）----
A1 = "\toptional_ioport_array<5> m_io_key;"
HALL_METHODS = A1 + """

	// ===== hall api (added) =====
public:
	u8  hall_ram8(u32 a) const  { return m_maincpu->space(AS_PROGRAM).read_byte(a); }
	u16 hall_ram16(u32 a) const { return m_maincpu->space(AS_PROGRAM).read_word(a); }

	// bank<0 → COIN 口；bank 0..4 → KEY0..KEY4；mask 定位字段；val 为字段逻辑值
	bool hall_field(int bank, u8 mask, s32 val)
	{
		// bank<0：COIN 口同 mask 可挂多个 PORT_CONDITION 条件字段（COIN1 与 Key In 共用 0x01，
		// 由 DSW2 bit4 切换激活）。field(mask) 只返第一个、会落到失活字段；改遍历同 mask 全字段都写值，
		// 激活者生效、失活者被 MAME 屏蔽 → Coin/Key-In 两模式通用。（2026-11-17 投币提速）
		if (bank < 0)
		{
			if (!m_io_coin) return false;
			bool any = false;
			for (ioport_field &f : m_io_coin->fields())
				if (f.mask() == mask) { f.set_value(val); any = true; }
			return any;
		}
		ioport_field *f = nullptr;
		if (bank < 5) { if (m_io_key[bank]) f = m_io_key[bank]->field(mask); }
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	// 一枚币：COIN bit0 按下再松开
	void hall_coin() { hall_field(-1, 0x01, 1); hall_field(-1, 0x01, 0); }
	static igs011_oki_state *s_hall;

	// ===== hall frame export (A 路：纯 CPU，无 GL) =====
	int hall_frame_capture();                       // 索引位图+调色板 → RGBA；返回像素数，<0 失败
	u64 hall_frame_number() const { return m_screen->frame_number(); }
	static u32 s_frame_buf[512 * 260];              // 屏幕 set_size(512,260)
	static int s_frame_w, s_frame_h;

	// 拨码读写：idx 0..4 → DSW1..DSW5；mask 定位字段；val = 字段原始值（mask 内）
	bool hall_dip(int idx, u32 mask, u32 val)
	{
		if (idx < 0 || idx >= 5 || !m_io_dsw[idx]) return false;
		ioport_field *f = m_io_dsw[idx]->field(mask);
		if (!f) return false;
		f->set_value(val);
		f->live().value = (f->live().value & ~f->mask()) | ((ioport_value)val & f->mask());
		return true;
	}
	int hall_dip_get(int idx, u32 mask)
	{
		if (idx < 0 || idx >= 5 || !m_io_dsw[idx]) return -1;
		ioport_field *f = m_io_dsw[idx]->field(mask);
		if (!f) return -1;
		return int(f->live().value & f->mask());
	}
	// ===== hall api end ====="""

# ---- 2) init_lhb2cpgs() 里记下机器实例 + 打开屏幕常更新 ----
A2 = "void igs011_oki_state::init_lhb2cpgs()\n{\n\tlhb3_decrypt();"
H2 = ("void igs011_oki_state::init_lhb2cpgs()\n{\n"
      "\ts_hall = this;   // hall api\n"
      "\tm_screen->set_video_attributes(VIDEO_ALWAYS_UPDATE);   // -video none 下位图仍每帧更新\n"
      "\tlhb3_decrypt();")

# ---- 2b) 奖分小游戏保护检查补全（2026-11-17，修连庄2次后第3次进小游戏黑屏）----
# 原 init_lhb2cpgs 仅 6 处 ROM 补丁，MAME 自注 "possibly incomplete"（上游 TODO 列 lhb2cpgs
# parametric bitswap 未实现）。解密 ROM 扫保护签名 move.w $100de0,d1; cmp.w d1,d0; beq 得 13 处：
# 6 已知(beq.s 6736→6036)＋7 未补(beq.w 6700)，7 处聚集 0x50e0e-0x51a74(奖分小游戏子程序)，
# fall-through=pea 错误串($19b2a/$19b52/$19b7a/$19ba2/$19bca/$19bf2/$19c1a)+clr -(sp)x2+jsr 错误处理→黑屏。
# 修法与上游同：beq.w(6700)→bra.w(6000)，位移字 00d2 不动，强制跳错误处理(检查恒过)。
A3 = "\trom[0x3f144 / 2] = 0x6036;\n}"
H3 = ("\trom[0x3f144 / 2] = 0x6036;\n"
      "\t// 奖分小游戏保护补全（7 处未补检查，beq.w→bra.w 保位移；详见上方注释）\n"
      "\trom[0x50e0e / 2] = 0x6000;\n"
      "\trom[0x50fdc / 2] = 0x6000;\n"
      "\trom[0x51232 / 2] = 0x6000;\n"
      "\trom[0x51460 / 2] = 0x6000;\n"
      "\trom[0x516c6 / 2] = 0x6000;\n"
      "\trom[0x518d0 / 2] = 0x6000;\n"
      "\trom[0x51a74 / 2] = 0x6000;\n"
      "}")

# ---- 3) 文件末尾：导出给 JS 的 C 接口 ----
TAIL = """

// ===== hall api (added): Emscripten/JS 入口 =====
#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>   // EMSCRIPTEN_KEEPALIVE 真身，漏了符号会被剥掉
#endif
#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

igs011_oki_state *igs011_oki_state::s_hall = nullptr;
u32 igs011_oki_state::s_frame_buf[512 * 260];
int igs011_oki_state::s_frame_w = 0;
int igs011_oki_state::s_frame_h = 0;

// A 路帧捕获：curbitmap()（ind16 索引色）经调色板 pen_color() 转 RGBA。
// igs011 调色板 2048 项，pen 为全 16 位索引（layerpix|pri<<8），直接 pen_color(pen)。
int igs011_oki_state::hall_frame_capture()
{
	screen_bitmap &cb = m_screen->curbitmap();
	if (cb.format() != BITMAP_FORMAT_IND16) return -2;
	bitmap_ind16 &bm = cb.as_ind16();
	const int w = bm.width(), h = bm.height();
	if (w <= 0 || h <= 0 || w * h > 512 * 260) return -3;
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
			// rgb_t=0xAARRGGBB → 小端字节序 R,G,B,A ⇒ 存 0xAABBGGRR
			out[x] = 0xff000000u | ((c & 0xffu) << 16) | (c & 0xff00u) | ((c >> 16) & 0xffu);
		}
	}
	s_frame_w = w; s_frame_h = h;
	return w * h;
}

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready()      { return igs011_oki_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a)  { return igs011_oki_state::s_hall ? igs011_oki_state::s_hall->hall_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a) { return igs011_oki_state::s_hall ? igs011_oki_state::s_hall->hall_ram16(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin()       { if (!igs011_oki_state::s_hall) return -1; igs011_oki_state::s_hall->hall_coin(); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int bank, int mask, int val)
{
	return (igs011_oki_state::s_hall && igs011_oki_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1;
}
// 机台关键量：活信用 0x100dbc（cal4 实证：投5币=5，开局押分 5->4 递减；0x100d72/0x1010c2 是总投币不递减）；押分/状态字待游戏页标定，先占位 0
EMSCRIPTEN_KEEPALIVE int hall_state_word() { return 0; }
EMSCRIPTEN_KEEPALIVE int hall_credit()     { return igs011_oki_state::s_hall ? igs011_oki_state::s_hall->hall_ram16(0x100dbc) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_bet_level()  { return 0; }
// A 路帧导出：JS 每帧调 capture，再用 ptr/w/h 从 HEAPU8 取 RGBA 画到 canvas
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return igs011_oki_state::s_hall ? igs011_oki_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr()  { return u32(uintptr_t(igs011_oki_state::s_frame_buf)); }
EMSCRIPTEN_KEEPALIVE int hall_frame_w()    { return igs011_oki_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h()    { return igs011_oki_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs011_oki_state::s_hall ? int(igs011_oki_state::s_hall->hall_frame_number()) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_dip(int idx, int mask, int val)
{ return (igs011_oki_state::s_hall && igs011_oki_state::s_hall->hall_dip(idx, (u32)mask, (u32)val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_dip_get(int idx, int mask)
{ return igs011_oki_state::s_hall ? igs011_oki_state::s_hall->hall_dip_get(idx, (u32)mask) : -1; }
}
// ===== hall api end =====
"""

for name, a in (("锚1 m_io_key 成员", A1), ("锚2 init_lhb2cpgs 头部", A2), ("锚3 init_lhb2cpgs 末补丁", A3)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1 次）" % (name, src.count(a))); sys.exit(2)

for need in ("optional_ioport m_io_coin;", "optional_ioport_array<5> m_io_key;",
             "required_device<screen_device> m_screen;", "optional_ioport_array<5> m_io_dsw;"):
    if need not in src:
        print("FAIL: 类里缺少预期成员:", need); sys.exit(3)

src = src.replace(A1, HALL_METHODS, 1)
src = src.replace(A2, H2, 1)
src = src.replace(A3, H3, 1)
src += TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: lhb2 hall 补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))