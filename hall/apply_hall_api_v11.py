#!/usr/bin/env python3
# v11 = v10 帧导出/输入接口完全不变 + 声音链【纯诊断 printf】（零逻辑改动）。
# 目的：定位 -sound js 下 jsmame_stream_sink_update 全程 0 调用的断点。
# 打点位置（mame0289 官方源码核对）：
#   js_sound.cpp: init / get_information / stream_sink_open / stream_sink_update
#   sound.cpp:    streams_update 推送前（报 speakers/out_streams/in_streams/mappings/nodes 计数）
# 锚点不对就当场失败，绝不静默改坏。诊断完即移除（v12 起）。
import io, sys, os

# ---- 先原样执行 v10（补丁 igs017.cpp，帧导出/输入不变）----
V10 = os.path.join(os.path.dirname(__file__), "apply_hall_api_v10.py")
exec(compile(io.open(V10, encoding="utf-8").read(), V10, "exec"))

def patch_file(path, edits):
    src = io.open(path, encoding="utf-8").read()
    orig = src
    for name, a, b in edits:
        n = src.count(a)
        if n != 1:
            print("FAIL: %s 锚点[%s] 命中 %d 次（必须正好 1）" % (path, name, n)); sys.exit(2)
        src = src.replace(a, b, 1)
    io.open(path, "w", encoding="utf-8").write(src)
    print("OK: %s 诊断打点 %d -> %d 字节（+%d）" % (path, len(orig), len(src), len(src) - len(orig)))

# ---- js_sound.cpp 打点 ----
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

# ---- sound.cpp 打点（streams_update 推送前报计数）----
SND = "src/emu/sound.cpp"
snd_edits = [
    ("streams_update_counts",
     "\t\tmachine().osd().sound_begin_update();",
     "\t\t{ static unsigned hc = 0; if ((hc++ % 600u) == 0u) printf(\"SNDMGR: speakers=%zu out_streams=%zu in_streams=%zu mappings=%zu nodes=%zu muted=%u\\n\", m_speakers.size(), m_osd_output_streams.size(), m_osd_input_streams.size(), m_mappings.size(), m_osd_info.m_nodes.size(), (unsigned)m_muted); }\n\t\tmachine().osd().sound_begin_update();"),
]
patch_file(SND, snd_edits)
print("OK: v11 声音诊断补丁全部应用")