#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Out Zone (Toaplan, toaplan1.cpp, MAME 0.289) · hall api 补丁 v1
================================================================
目标：让 outzonea 以 -video none 跑逻辑，画面经驱动层导出 RGBA，页面 2D 自绘（A 路纯 CPU，零 GL）。
基线：lhzb2 线跑通的 apply_hall_api_v10/v11.py（同一套 hall api 形状），移植到 toaplan1_state。

与 v10 的唯一实质差异：outzone 屏幕是 rgb32（common_video_config: screen.set_update_callback(FUNC(toaplan1_state::screen_update), rgb32)），
帧捕获走 screen_bitmap::as_rgb32()（src/emu/screen.h:114 已核），不是 as_ind16。

锚点（mame0289 官方源码逐行核过）：
  A1 = toaplan1.cpp:739  "\trequired_device<m68000_device> m_maincpu;"   （类内，唯一）
  A2 = toaplan1.cpp:1848-1851  machine_reset() 整个函数体               （唯一）

键位（toaplipt.h:106 INPUT_GENERIC_JOY_UDLR + toaplan1_2b/3b/SYSTEM 宏，已核）：
  P1: 0x01=上 0x02=下 0x04=左 0x08=右 | 0x10=射击(BUTTON1) 0x20=炸弹(BUTTON2) 0x40=BUTTON3
  SYSTEM: 0x08=COIN1 0x20=START1（0x01=SERVICE 0x04=TEST 0x10=COIN2 0x40=START2）

声音诊断段与 v11 完全相同（js_sound.cpp / sound.cpp 锚点已在 0.289 CI 验证过）。
"""
import io
import sys

PATH = "src/mame/toaplan/toaplan1.cpp"
t = io.open(PATH, encoding="utf-8").read()

A1 = "\trequired_device<m68000_device> m_maincpu;"
A2 = ("void toaplan1_state::machine_reset()\n"
      "{\n"
      "\tmachine().bookkeeping().coin_lockout_global_w(0);\n"
      "}")

for name, a in (("A1", A1), ("A2", A2)):
    n = t.count(a)
    if n != 1:
        print("FATAL: 锚点 %s 命中 %d 次（期望 1）——源码版本不符，拒绝打补丁" % (name, n))
        sys.exit(2)

INS1 = """
	// ===== hall api (added by hall/apply_outzone_api.py) =====
public:
	ioport_port *hall_find_port(const char *tag)
	{
		const ioport_list &list = machine().ioport().ports();
		auto it = list.find(tag);
		if (it == list.end())
		{
			// 0.289 实测：根设备端口键带 ":" 前缀（:P1/:SYSTEM…，hall_port_tag 转储证实），补查一次
			const std::string full = std::string(":") + tag;
			it = list.find(full);
		}
		return (it != list.end()) ? it->second.get() : nullptr;
	}
	// port: 0=P1  1=P2  2=SYSTEM；mask=字段掩码；val=字段逻辑值(0/1)
	bool hall_field(int port, u8 mask, s32 val)
	{
		static const char *names[] = { "P1", "P2", "SYSTEM" };
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
		static const char *names[] = { "P1", "P2", "SYSTEM" };
		if (port < 0 || port > 2) return -1;
		ioport_port *p = hall_find_port(names[port]);
		return p ? int(p->read()) : -1;
	}
	int hall_coin_count() { return machine().bookkeeping().coin_counter_get_count(0); }
	static toaplan1_state *s_hall;
	int hall_frame_capture();
	u64 hall_frame_number() const { return m_screen->frame_number(); }
	static u32 s_frame_buf[320 * 240];
	static int s_frame_w, s_frame_h;
	// ===== hall api end =====
"""

INS2 = ("void toaplan1_state::machine_reset()\n"
        "{\n"
        "\ts_hall = this;   // hall api\n"
        "\tm_screen->set_video_attributes(VIDEO_UPDATE_BEFORE_VBLANK | VIDEO_ALWAYS_UPDATE);   // A 路：-video none 下屏幕位图仍逐帧更新（保留原 BEFORE_VBLANK）\n"
        "\tmachine().bookkeeping().coin_lockout_global_w(0);\n"
        "}")

TAIL = """
// ===== hall api (added)：静态成员 + rgb32 帧捕获 + C 导出 =====
toaplan1_state *toaplan1_state::s_hall = nullptr;
u32 toaplan1_state::s_frame_buf[320 * 240];
int toaplan1_state::s_frame_w = 0;
int toaplan1_state::s_frame_h = 0;

int toaplan1_state::hall_frame_capture()
{
	screen_bitmap &cb = m_screen->curbitmap();
	if (cb.format() != BITMAP_FORMAT_RGB32) return -2;
	bitmap_rgb32 &bm = cb.as_rgb32();
	// set_raw 的位图含消隐期（450x282），只裁可见区 320x240（screen.h:191 visible_area）
	const rectangle &vis = m_screen->visible_area();
	const int x0 = vis.left(), y0 = vis.top();
	const int w = vis.width(), h = vis.height();
	if (w <= 0 || h <= 0 || w * h > 320 * 240) return -3;
	if (x0 < 0 || y0 < 0 || x0 + w > bm.width() || y0 + h > bm.height()) return -4;
	for (int y = 0; y < h; y++)
	{
		const u32 *row = &bm.pix(y0 + y, x0);
		u32 *out = s_frame_buf + y * w;
		for (int x = 0; x < w; x++)
		{
			const u32 c = row[x];   // 0xAARRGGBB
			out[x] = 0xff000000u | ((c & 0xffu) << 16) | (c & 0xff00u) | ((c >> 16) & 0xffu);   // → RGBA 字节序
		}
	}
	s_frame_w = w; s_frame_h = h;
	return w * h;
}

#ifdef __EMSCRIPTEN__
#include <emscripten/emscripten.h>
#endif
extern "C" {
EMSCRIPTEN_KEEPALIVE int hall_ready() { return toaplan1_state::s_hall ? 1 : 0; }
EMSCRIPTEN_KEEPALIVE int hall_key(int port, int mask, int val) { return (toaplan1_state::s_hall && toaplan1_state::s_hall->hall_field(port, (u8)mask, val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_input(int port) { return toaplan1_state::s_hall ? toaplan1_state::s_hall->hall_input(port) : -1; }
EMSCRIPTEN_KEEPALIVE int hall_coin_count() { return toaplan1_state::s_hall ? toaplan1_state::s_hall->hall_coin_count() : -1; }
EMSCRIPTEN_KEEPALIVE int hall_frame_capture() { return toaplan1_state::s_hall ? toaplan1_state::s_hall->hall_frame_capture() : -1; }
EMSCRIPTEN_KEEPALIVE u32 hall_frame_ptr() { return (u32)(uintptr_t)toaplan1_state::s_frame_buf; }
EMSCRIPTEN_KEEPALIVE int hall_frame_w() { return toaplan1_state::s_frame_w; }
EMSCRIPTEN_KEEPALIVE int hall_frame_h() { return toaplan1_state::s_frame_h; }
EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return toaplan1_state::s_hall ? (int)toaplan1_state::s_hall->hall_frame_number() : -1; }
}
// ===== hall api end =====
"""

t = t.replace(A1, A1 + INS1, 1)
t = t.replace(A2, INS2, 1)
t = t.rstrip("\n") + "\n" + TAIL
io.open(PATH, "w", encoding="utf-8", newline="\n").write(t)
print("OK toaplan1.cpp: A1+A2+TAIL 已注入（rgb32 帧捕获，320x240）")

# ===== 声音链路诊断（锚点逐字复制 hall/apply_hall_api_v11.py，已在 0.289 CI #24 验证）=====
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
print("ALL DONE")
