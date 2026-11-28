#!/usr/bin/env python3
# 给官方 MAME 0.289 的 src/mame/igs/igs_m027.cpp 打"厅用接口"补丁（龙虎大满贯 lhdmg / IGS027 ARM）。
# 三处插入，全部锚定官方原文；锚点不对就报错退出（绝不静默改坏）。
# RAM 直读 m_nvram 共享指针（0x18000000..0x18007fff mirror 32KB），不走总线、无副作用。
import io, sys

PATH = "src/mame/igs/igs_m027.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内方法（锚：m_maincpu 成员声明行）----
A1 = "\trequired_device<igs027a_cpu_device> m_maincpu;"
H1 = A1 + """

	// ===== hall api (added) =====
	u8 hall_m027_ram8(u32 a) const
	{
		u32 off = a & 0x7fff;
		return (m_nvram[off >> 2] >> (8 * (off & 3))) & 0xff;
	}
	void hall_m027_ram8_w(u32 a, u8 v)
	{
		u32 off = a & 0x7fff;
		u32 lane = (off & 3) * 8;
		u32 w = m_nvram[off >> 2];
		w = (w & ~(0xffu << lane)) | (u32(v) << lane);
		m_nvram[off >> 2] = w;
	}
	bool hall_field(const char *tag, u8 mask, s32 val)
	{
		ioport_port *p = machine().ioport().port(tag);
		if (!p) return false;
		ioport_field *f = p->field(mask);
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	static igs_m027_state *s_hall;
	// ===== hall api end ====="""

# ---- 2) init_slqz3 记实例（lhdmg/lhdmgp/lhzb3 共用此 init）----
A2 = "void igs_m027_state::init_slqz3()\n{\n\tslqz3_decrypt(machine());"
H2 = "void igs_m027_state::init_slqz3()\n{\n\ts_hall = this;   // hall api\n\tslqz3_decrypt(machine());"

# ---- 3) 文件尾导出 ----
TAIL = """

// ===== hall api (added): 给 Emscripten/JS 的入口 =====
#ifdef EMSCRIPTEN
#include <emscripten/emscripten.h>
#else
#define EMSCRIPTEN_KEEPALIVE
#endif

igs_m027_state *igs_m027_state::s_hall = nullptr;

extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready() { return igs_m027_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs_m027_state::s_hall ? (int)igs_m027_state::s_hall->machine().frame_number() : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram8(u32 a) { return igs_m027_state::s_hall ? igs_m027_state::s_hall->hall_m027_ram8(a) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_ram16(u32 a)
{
	if (!igs_m027_state::s_hall) return -1;
	return igs_m027_state::s_hall->hall_m027_ram8(a) | (igs_m027_state::s_hall->hall_m027_ram8(a + 1) << 8);
}
EMSCRIPTEN_KEEPALIVE int hall_ram32(u32 a)
{
	if (!igs_m027_state::s_hall) return -1;
	int v = 0;
	for (int i = 0; i < 4; i++) v |= igs_m027_state::s_hall->hall_m027_ram8(a + i) << (8 * i);
	return v;
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
// bank: "KEY0".."KEY4"/"TEST"/"DSW1"/"DSW2"；mask: 位掩码；val: 1=按下 0=抬起
EMSCRIPTEN_KEEPALIVE int hall_key(const char *bank, int mask, int val)
{
	return (igs_m027_state::s_hall && igs_m027_state::s_hall->hall_field(bank, (u8)mask, val)) ? 0 : -1;
}
}
"""

for name, a in (("锚1 m_maincpu 声明", A1), ("锚2 init_slqz3", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1）" % (name, src.count(a))); sys.exit(2)
if "hall api" in src:
    print("FAIL: 补丁疑似已应用"); sys.exit(2)
src = src.replace(A1, H1, 1)
src = src.replace(A2, H2, 1)
src = src + TAIL
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: m027 厅接口补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
