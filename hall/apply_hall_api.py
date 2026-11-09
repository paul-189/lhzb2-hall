#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/igs/igs017.cpp 打"厅用接口"补丁。
# 只做三处插入，全部锚定官方原文；任一处锚点找不到就报错退出（绝不静默改坏）。
import io, sys

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内加公开方法（锚：required_device<cpu_device> m_maincpu;）----
A1 = "\trequired_device<cpu_device> m_maincpu;"
HALL_METHODS = A1 + """

	// ===== hall api (added) =====
public:
	u8  hall_ram8(u32 a) const   { return m_maincpu->space(AS_PROGRAM).read_byte(a); }
	u16 hall_ram16(u32 a) const  { return m_maincpu->space(AS_PROGRAM).read_word(a); }
	// 写输入口的某个字段（掩码定位字段），厅用它投币/按牌
	bool hall_field(const char *tag, u8 mask, s32 val)
	{
		ioport_port *p = machine().ioport().port(tag);
		if (!p) return false;
		ioport_field *f = p->field(mask);
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	// 一枚币：按下再松开（PORT_IMPULSE(5) 由 MAME 自己整形）
	void hall_coin() { hall_field("COINS", 0x08, 1); hall_field("COINS", 0x08, 0); }
	static igs017_state *s_hall;
	// ===== hall api end ====="""

# ---- 2) init_lhzb2() 里记下机器实例（锚：函数体头两行）----
A2 = "void igs017_state::init_lhzb2()\n{\n\tconst int rom_size = memregion(\"maincpu\")->bytes();"
H2 = "void igs017_state::init_lhzb2()\n{\n\ts_hall = this;   // hall api\n" + \
     "\tconst int rom_size = memregion(\"maincpu\")->bytes();"

# ---- 3) 文件末尾导出给 JS 的 C 接口 ----
TAIL = """

// ===== hall api (added): 给 Emscripten/JS 的入口 =====
#ifdef EMSCRIPTEN
#include <emscripten/emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

igs017_state *igs017_state::s_hall = nullptr;

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready()               { return igs017_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a)           { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a)          { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin()                { if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_coin(); return 0; }
// bank: "KEY0".."KEY4"/"COINS"；mask: 位掩码；val: 字段逻辑值
EMSCRIPTEN_KEEPALIVE int hall_key(const char *bank, int mask, int val)
{
	return (igs017_state::s_hall && igs017_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1;
}
// 机台关键量：0x500060 状态字 / 0x500202 信用 / 0x50020d 押分档
EMSCRIPTEN_KEEPALIVE int hall_state_word()  { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(0x500060) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_credit()      { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram16(0x500202) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_bet_level()   { return igs017_state::s_hall ? igs017_state::s_hall->hall_ram8(0x50020d) : -1; }
}
// ===== hall api end =====
"""

for name, a in (("锚1 m_maincpu 成员", A1), ("锚2 init_lhzb2 头部", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1 次）" % (name, src.count(a))); sys.exit(2)

src = src.replace(A1, HALL_METHODS, 1)
src = src.replace(A2, H2, 1)
src += TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: 补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
