#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/igs/igs017.cpp 打"厅用接口"补丁（v3：修正 EMSCRIPTEN_KEEPALIVE 缺头文件）。
# 只用该驱动类已有的成员（m_io_coins / m_io_key / m_maincpu），不碰任何私有 API
# （v1 用了 ioport_manager::port()，那是私有成员，编译报 'port' is a private member）。
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
	// ===== hall api end ====="""

# ---- 2) init_lhzb2() 里记下机器实例 ----
A2 = "void igs017_state::init_lhzb2()\n{\n\tconst int rom_size = memregion(\"maincpu\")->bytes();"
GLBLK = (
"\t#ifdef __EMSCRIPTEN__\n"
"\t// 实测：页面崩在 getCurTexUnit(GLctx==null)——emscripten 的 sdl3 移植（官方自称 experimental）\n"
"\t// 没把 WebGL 上下文设为当前，MAME 一调 glEnable 就炸。这里按标准 API 自建并 current。\n"
"\t{\n"
"\t\tEmscriptenWebGLContextAttributes at;\n"
"\t\temscripten_webgl_init_context_attributes(&at);\n"
"\t\tat.alpha = 0; at.antialias = 0; at.majorVersion = 1; at.minorVersion = 0;\n"
"\t\tEMSCRIPTEN_WEBGL_CONTEXT_HANDLE h = emscripten_webgl_create_context(\"#canvas\", &at);\n"
"\t\tif (h) emscripten_webgl_make_context_current(h);\n"
"\t}\n"
"\t#endif\n"
)
H2 = "void igs017_state::init_lhzb2()\n{\n" + GLBLK + "\ts_hall = this;   // hall api\n" + \
     "\tconst int rom_size = memregion(\"maincpu\")->bytes();"

# ---- 3) 文件末尾：导出给 JS 的 C 接口 ----
TAIL = """

// ===== hall api (added): Emscripten/JS 入口 =====
#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>   // EMSCRIPTEN_KEEPALIVE 的真身（v2 漏了这个，符号被剥掉）
#include <emscripten/html5.h>        // 自建/切当前 WebGL 上下文（v4）
#endif
#ifndef EMSCRIPTEN_KEEPALIVE
#define EMSCRIPTEN_KEEPALIVE
#endif

igs017_state *igs017_state::s_hall = nullptr;

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
}
// ===== hall api end =====
"""

for name, a in (("锚1 m_maincpu 成员", A1), ("锚2 init_lhzb2 头部", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1 次）" % (name, src.count(a))); sys.exit(2)

for need in ("optional_ioport m_io_coins;", "optional_ioport_array<5> m_io_key;"):
    if need not in src:
        print("FAIL: 类里缺少预期成员:", need); sys.exit(3)

src = src.replace(A1, HALL_METHODS, 1)
src = src.replace(A2, H2, 1)
src += TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: 补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
