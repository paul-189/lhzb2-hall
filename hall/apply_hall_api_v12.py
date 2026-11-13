#!/usr/bin/env python3
# v12 = v10（稳定基线，帧导出/输入不变）+ 拨码读写导出 hall_dip / hall_dip_get。
# 目的：厅用侧需要机台原生运营功能「开分方式(Key-In)+开分比率100」——
#       DSW1 是物理指拨（ROM 只读显示，指拨测试屏 0x8A00 实证 cfg 无法改写），
#       wasm 无 cfg ⇒ 唯一干净路 = 运行时写 DSW 字段。
# API 依据（本机 mame0289 官方源码核对）：
#   - igs017.cpp:857  optional_ioport_array<3> m_io_dsw;  构造 "DSW%u",1U ⇒ idx0..2=DSW1..3
#   - ioport.h:785    ioport_port::field(ioport_value mask) const  公开
#   - ioport.h:595    ioport_field::set_value(ioport_value)        公开；位字段值=mask 内原始值
#   - 语义：DIPSWITCH 字段 IP_ACTIVE_LOW 由 read() 统一处理，set_value 传原始档位值
# 锚点不对就当场失败，绝不静默改坏。
import io, sys, os

V10 = os.path.join(os.path.dirname(__file__), "apply_hall_api_v10.py")
exec(compile(io.open(V10, encoding="utf-8").read(), V10, "exec"))

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内：hall_dip 方法（锚 = v10 写入的静态帧缓冲声明 + end 标记）----
A1 = ("\tstatic int s_frame_w, s_frame_h;\n"
      "\t// ===== hall api end =====")
H1 = ("\tstatic int s_frame_w, s_frame_h;\n"
"""
\t// 拨码读写：idx 0..2 → DSW1..DSW3；mask 定位字段；val = 字段原始值（mask 内）
\tbool hall_dip(int idx, u32 mask, u32 val)
\t{
\t\tif (idx < 0 || idx >= 3 || !m_io_dsw[idx]) return false;
\t\tioport_field *f = m_io_dsw[idx]->field(mask);
\t\tif (!f) return false;
\t\tf->set_value(val);
\t\treturn true;
\t}
\tint hall_dip_get(int idx, u32 mask)   // 存在性探针：字段在=1，不在/无口=-1
\t{
\t\tif (idx < 0 || idx >= 3 || !m_io_dsw[idx]) return -1;
\t\treturn m_io_dsw[idx]->field(mask) ? 1 : -1;
\t}
\t// ===== hall api end =====""")

# ---- 2) extern C 导出（锚 = v10 的 hall_frame_number 导出行 + 收尾大括号）----
A2 = ("EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs017_state::s_hall ? int(igs017_state::s_hall->hall_frame_number()) : -1; }\n}")
H2 = ("EMSCRIPTEN_KEEPALIVE int hall_frame_number() { return igs017_state::s_hall ? int(igs017_state::s_hall->hall_frame_number()) : -1; }\n"
"""EMSCRIPTEN_KEEPALIVE int hall_dip(int idx, int mask, int val)
{ return (igs017_state::s_hall && igs017_state::s_hall->hall_dip(idx, (u32)mask, (u32)val)) ? 0 : -1; }
EMSCRIPTEN_KEEPALIVE int hall_dip_get(int idx, int mask)
{ return igs017_state::s_hall ? igs017_state::s_hall->hall_dip_get(idx, (u32)mask) : -1; }
}""")

for name, a in (("锚1 v10帧缓冲+end", A1), ("锚2 v10frame_number导出收尾", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1）" % (name, src.count(a))); sys.exit(2)

src = src.replace(A1, H1, 1)
src = src.replace(A2, H2, 1)
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: v12 拨码补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
