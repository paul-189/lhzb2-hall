#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Knights of the Round (CPS1, capcom/cps1.cpp + cps1.h, MAME 0.289) · hall api 补丁 v1
====================================================================================
目标：让 knights 以 -video none 跑逻辑，画面经驱动层导出 RGBA（ind16→palette→RGBA），页面 2D 自绘。
基线：apply_outzone_api.py（toaplan1 跑通版），移植到 cps_state。

与 outzone 的实质差异：
  1. 位图 = ind16（palette 索引），需 m_palette->pen_to_color() 转 RGBA
  2. 屏幕 384x224 横屏（CPS_HTOTAL=512,HBEND=64,HBSTART=448; VTOTAL=262,VBEND=16,VBSTART=240）
  3. 输入端口 = IN0(系统8位) / IN1(P1+P2合16位) / IN2(P3)
  4. 初始化钩子 = MACHINE_START_MEMBER(cps_state,cps1)（非 machine_reset）
  5. ROM 修正：audiocpu 改 64K 直载（旧套装 kr_09.rom=64K）；删 10 个 PAL ROM_LOAD（无代码读取）
  6. 补丁改两个文件：cps1.h（类成员）+ cps1.cpp（MACHINE_START + TAIL + ROM 修正）

锚点（mame0289 官方源码逐行核过）：
  A1 = cps1.h:333  "\trequired_device<m68000_base_device> m_maincpu;"  （类内，唯一）
  A2 = cps1.cpp:3899-3902  MACHINE_START_MEMBER(cps_state,cps1) 整个函数体（唯一）

键位（cps1_3b → cps1_2b → cps1_3players → knights，已核）：
  IN0: 0x01=COIN1 0x02=COIN2 0x04=SERVICE1 0x10=START1 0x20=START2 0x40=SERVICE
  IN1: P1 0x0001=右 0x0002=左 0x0004=下 0x0008=上 0x0010=攻击 0x0020=跳
       P2 0x0100=右 0x0200=左 0x0400=下 0x0800=上 0x1000=攻击 0x2000=跳
  IN2: P3 0x01=右 0x02=左 0x04=下 0x08=上 0x10=攻击 0x20=跳 0x40=COIN3 0x80=START3

hall_field port 映射：0=IN1(玩家) 1=IN0(系统) 2=IN2(P3)；mask=u16。
"""
import io
import sys
import re

# ===== 文件 1: cps1.h（注入类成员）=====
H_PATH = "src/mame/capcom/cps1.h"
h = io.open(H_PATH, encoding="utf-8").read()

A1 = "\trequired_device<m68000_base_device> m_maincpu;"
n = h.count(A1)
if n != 1:
    print("FATAL: cps1.h 锚点 A1 命中 %d 次（期望 1）" % n)
    sys.exit(2)

INS1 = """
	// ===== hall api (added by hall/apply_cps1_api.py) =====
public:
	ioport_port *hall_find_port(const char *tag)
	{
		const ioport_list &list = machine().ioport().ports();
		auto it = list.find(tag);
		if (it == list.end())
		{
			const std::string full = std::string(":") + tag;
			it = list.find(full);
		}
		return (it != list.end()) ? it->second.get() : nullptr;
	}
	// port: 0=IN1(P1+P2)  1=IN0(system)  2=IN2(P3)；mask=u16 字段掩码；val=0/1
	bool hall_field(int port, u16 mask, s32 val)
	{
		static const char *names[] = { "IN1", "IN0", "IN2" };
		if (port < 0 || port > 2) return false;
		ioport_port *p = hall_find_port(names[port]);
		if (!p) return false;
		ioport_field *f = p->field(mask);
		if (!f) return false;
		f->set_value(val);
		return true;
	}
	int hall_input(int port)
	{
		static const char *names[] = { "IN1", "IN0", "IN2" };
		if (port < 0 || port > 2) return -1;
		ioport_port *p = hall_find_port(names[port]);
		return p ? int(p->read()) : -1;
	}
	int hall_coin_count() { return machine().bookkeeping().coin_counter_get_count(0); }
	static cps_state *s_hall;
	int hall_frame_capture();
	u64 hall_frame_number() const { return m_screen->frame_number(); }
	static u32 s_frame_buf[384 * 224];
	static int s_frame_w, s_frame_h;
	// ===== hall api end ====="""

h = h.replace(A1, A1 + INS1, 1)
io.open(H_PATH, "w", encoding="utf-8", newline="\n").write(h)
print("OK cps1.h: A1 注入（hall 类成员，ind16 384x224）")

# ===== 文件 2: cps1.cpp =====
C_PATH = "src/mame/capcom/cps1.cpp"
t = io.open(C_PATH, encoding="utf-8").read()

# --- A2: MACHINE_START_MEMBER(cps_state,cps1) ---
A2 = ("MACHINE_START_MEMBER(cps_state,cps1)\n"
      "{\n"
      "\tm_audiobank->configure_entries(0, 2, memregion(\"audiocpu\")->base() + 0x10000, 0x4000);\n"
      "}")
n = t.count(A2)
if n != 1:
    print("FATAL: cps1.cpp 锚点 A2 命中 %d 次（期望 1）" % n)
    sys.exit(2)

INS2 = ("MACHINE_START_MEMBER(cps_state,cps1)\n"
        "{\n"
        "\ts_hall = this;   // hall api\n"
        "\tm_screen->set_video_attributes(VIDEO_UPDATE_BEFORE_VBLANK | VIDEO_ALWAYS_UPDATE);\n"
        "\tm_audiobank->configure_entries(0, 2, memregion(\"audiocpu\")->base() + 0x10000, 0x4000);\n"
        "}")
t = t.replace(A2, INS2, 1)

# --- ROM 修正：knights audiocpu 改 64K 直载（限定在 knights 块内）---
OLD_AUDIO = ('ROM_LOAD( "kr_09.11a",  0x00000, 0x08000, CRC(5e44d9ee) SHA1(47a7503321be8d52b5c44af838e3bb82ee15a415) )\n'
             '\tROM_CONTINUE(           0x10000, 0x08000 )')
NEW_AUDIO = 'ROM_LOAD( "kr_09.rom",   0x00000, 0x10000, CRC(5e44d9ee) SHA1(47a7503321be8d52b5c44af838e3bb82ee15a415) )'
mk = re.search(r'(ROM_START\( knights \))(.*?)(ROM_END)', t, re.S)
if not mk:
    print("FATAL: 找不到 ROM_START( knights )"); sys.exit(2)
kb = mk.group(2)
n = kb.count(OLD_AUDIO)
if n != 1:
    print("FATAL: knights audiocpu ROM 锚点在 knights 块内命中 %d 次（期望 1）" % n); sys.exit(2)
kb = kb.replace(OLD_AUDIO, NEW_AUDIO, 1)
t = t[:mk.start(2)] + kb + t[mk.end(2):]

# --- ROM 修正：删 knights 的 10 个 PAL ROM_LOAD + 3 个 ROM_REGION ---
# 只删 knights ROM_START 内的 PAL 段（其他游戏不动）
m = re.search(r'(ROM_START\( knights \))(.*?)(ROM_END)', t, re.S)
if not m:
    print("FATAL: 找不到 ROM_START( knights )")
    sys.exit(2)
knight_body = m.group(2)
# 删除 plds 相关行
pal_lines = [l for l in knight_body.split('\n') if 'plds' in l.lower() or
             any(p in l for p in ['"buf1"', '"ioa1"', '"prg1"', '"rom1"', '"sou1"',
                                   '"kr63b.1a"', '"iob1.12d"', '"bprg1.11d"', '"ioc1.ic7"', '"c632.ic1"'])]
clean_body = knight_body
for l in pal_lines:
    clean_body = clean_body.replace(l + '\n', '', 1)
    # handle \r\n
    clean_body = clean_body.replace(l + '\r\n', '', 1)
t = t[:m.start(2)] + clean_body + t[m.end(2):]
print("OK cps1.cpp: 删除 knights PAL %d 行" % len(pal_lines))

# --- ROM 修正：主 CPU + GFX + OKI 文件名映射（旧→新）---
RENAME = {
    '"kr_23e.8f"': '"kr_23e.rom"',
    '"kr_22.7f"': '"kr_22.rom"',
    '"kr-5m.3a"': '"kr_gfx1.rom"',
    '"kr-7m.5a"': '"kr_gfx3.rom"',
    '"kr-1m.4a"': '"kr_gfx2.rom"',
    '"kr-3m.6a"': '"kr_gfx4.rom"',
    '"kr-6m.7a"': '"kr_gfx5.rom"',
    '"kr-8m.9a"': '"kr_gfx7.rom"',
    '"kr-2m.8a"': '"kr_gfx6.rom"',
    '"kr-4m.10a"': '"kr_gfx8.rom"',
    '"kr_18.11c"': '"kr_18.rom"',
    '"kr_19.12c"': '"kr_19.rom"',
}
# 只在 knights ROM_START 内做替换
m2 = re.search(r'(ROM_START\( knights \))(.*?)(ROM_END)', t, re.S)
if not m2:
    print("FATAL: ROM 映射后找不到 knights"); sys.exit(2)
kb = m2.group(2)
for new_name, old_name in RENAME.items():
    kb = kb.replace(new_name, old_name)
t = t[:m2.start(2)] + kb + t[m2.end(2):]
print("OK cps1.cpp: knights ROM 文件名映射 %d 项" % len(RENAME))

# --- TAIL: 静态成员 + ind16 帧捕获 + C 导出 ---
TAIL = """
// ===== hall api (added)：静态成员 + ind16→RGBA 帧捕获 + C 导出 =====
cps_state *cps_state::s_hall = nullptr;
u32 cps_state::s_frame_buf[384 * 224];
int cps_state::s_frame_w = 0;
int cps_state::s_frame_h = 0;

int cps_state::hall_frame_capture()
{
	screen_bitmap &cb = m_screen->curbitmap();
	if (cb.format() != BITMAP_FORMAT_IND16) return -2;
	bitmap_ind16 &bm = cb.as_ind16();
	const rectangle &vis = m_screen->visible_area();
	const int x0 = vis.left(), y0 = vis.top();
	const int w = vis.width(), h = vis.height();
	if (w <= 0 || h <= 0 || w * h > 384 * 224) return -3;
	if (x0 < 0 || y0 < 0 || x0 + w > bm.width() || y0 + h > bm.height()) return -4;
	for (int y = 0; y < h; y++)
	{
		const u16 *row = &bm.pix(y0 + y, x0);
		u32 *out = s_frame_buf + y * w;
		for (int x = 0; x < w; x++)
		{
			rgb_t c = m_palette->pen_color(row[x]);
			out[x] = 0xff000000u | (u32(c.r()) << 16) | (u32(c.g()) << 8) | u32(c.b());
		}
	}
	s_frame_w = w; s_frame_h = h;
	return w * h;
}

#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#endif
extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready() { return cps_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int port, int mask, int val) { return (cps_state::s_hall && cps_state::s_hall->hall_field(port, (u16)mask, val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_input(int port) { return cps_state::s_hall ? cps_state::s_hall->hall_input(port) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin_count() { return cps_state::s_hall ? cps_state::s_hall->hall_coin_count() : -1; }
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return cps_state::s_hall ? cps_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr() { return (u32)(uintptr_t)cps_state::s_frame_buf; }
EMSCRIPTEN_KEEPALIVE int hall_frame_w() { return cps_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h() { return cps_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return cps_state::s_hall ? (int)cps_state::s_hall->hall_frame_number() : -1; }
}
// ===== hall api end =====
"""

t = t.rstrip("\n") + "\n" + TAIL
io.open(C_PATH, "w", encoding="utf-8", newline="\n").write(t)
print("OK cps1.cpp: A2+ROM修正+TAIL 已注入（ind16 帧捕获，384x224）")

# ===== 声音链路诊断（与 outzone 完全相同的锚点，已在 0.289 CI 验证）=====
def patch_file(path, edits):
    src = io.open(path, encoding="utf-8").read()
    orig = src
    for name, a, b in edits:
        n = src.count(a)
        if n != 1:
            print("FAIL: %s 锚点[%s] 命中 %d 次（必须正好 1）" % (path, name, n)); sys.exit(2)
        src = src.replace(a, b, 1)
    io.open(path, "w", encoding="utf-8", newline="\n").write(src)
    print("OK: %s 诊断打点 %d -> %d 字节（+%d）" % (path, len(orig), len(src), len(src) - len(orig)))

JS = "src/osd/modules/sound/js_sound.cpp"
js_edits = [
    ("init",
     "\t\tm_current_stream_id = 0;\n\t\tm_next_stream_id = 1;\n\t\treturn 0;",
     "\t\tm_current_stream_id = 0;\n\t\tm_next_stream_id = 1;\n\t\tprintf(\"JS_SOUND: init ok\\n\");\n\t\treturn 0;"),
    ("get_information",
     "\t\tosd::audio_info result;\n\t\tresult.m_generation = 1;",
     "\t\tprintf(\"JS_SOUND: get_information called\\n\");\n\t\tosd::audio_info result;\n\t\tresult.m_generation = 1;"),
    ("sink_open",
     "\t\t// currently no support for multiple streams\n\t\tif (m_current_stream_id)",
     "\t\tprintf(\"JS_SOUND: sink_open node=%u rate=%u\\n\", node, rate);\n\t\t// currently no support for multiple streams\n\t\tif (m_current_stream_id)"),
    ("sink_update",
     "\t\tif (id != m_current_stream_id)\n\t\t\treturn;",
     "\t\t{ static unsigned hc = 0; if ((hc++ % 600u) == 0u) printf(\"JS_SOUND: sink_update id=%u cur=%u samples=%d call#%u\\n\", id, m_current_stream_id, samples_this_frame, hc); }\n\t\tif (id != m_current_stream_id)\n\t\t\treturn;"),
]
patch_file(JS, js_edits)

SND = "src/emu/sound.cpp"
snd_edits = [
    ("streams_update_counts",
     "\t\tmachine().osd().sound_begin_update();",
     "\t\t{ static unsigned hc = 0; if ((hc++ % 600u) == 0u) printf(\"SNDMGR: speakers=%zu out_streams=%zu in_streams=%zu mappings=%zu nodes=%zu muted=%u\\n\", m_speakers.size(), m_osd_output_streams.size(), m_osd_input_streams.size(), m_mappings.size(), m_osd_info.m_nodes.size(), (unsigned)m_muted); }\n\t\tmachine().osd().sound_begin_update();"),
]
patch_file(SND, snd_edits)
print("ALL DONE — knights CPS1 hall api v1")