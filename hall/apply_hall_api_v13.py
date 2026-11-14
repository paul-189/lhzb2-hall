#!/usr/bin/env python3
# v13 = v12（拨码读写基线）+ RAM 写导出 hall_ram8_write / hall_ram16_write。
# 目的：BOSS 参数台要能写机内配置区（$500B50 设置项1 / $500B55 比倍档），
#       以及玩家离开时把机内 credit($500202)/WIN 归零。
# 依据：v10 已有读口 m_maincpu->space(AS_PROGRAM).read_byte/read_word；
#       写用同一 space 的 write_byte/write_word（68k 总线写，与 ROM 自身写点同路径）。
# 锚点不对就当场失败，绝不静默改坏。
import io, sys, os

V12 = os.path.join(os.path.dirname(__file__), "apply_hall_api_v12.py")
exec(compile(io.open(V12, encoding="utf-8").read(), V12, "exec"))

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内：RAM 写方法（锚 = v12 写入的 hall_dip_get 收尾 + end 标记）----
A1 = ("\t\treturn int(f->live().value & f->mask());\n"
      "\t}\n"
      "\t// ===== hall api end =====")
H1 = ("\t\treturn int(f->live().value & f->mask());\n"
      "\t}\n"
"""\t// RAM 写：68k 总线直写（与 ROM 自身写点同路径）。仅供运行期参数/账务写入。
\tvoid hall_ram_w8(u32 a, u32 v)  { m_maincpu->space(AS_PROGRAM).write_byte(a, (u8)v); }
\tvoid hall_ram_w16(u32 a, u32 v) { m_maincpu->space(AS_PROGRAM).write_word(a, (u16)v); }
\t// ===== hall api end =====""")

# ---- 2) extern C 导出（锚 = v12 的 hall_dip_get 导出行 + 收尾大括号）----
A2 = ("EMSCRIPTEN_KEEPALIVE int hall_dip_get(int idx, int mask)\n"
      "{ return igs017_state::s_hall ? igs017_state::s_hall->hall_dip_get(idx, (u32)mask) : -1; }\n}")
H2 = ("EMSCRIPTEN_KEEPALIVE int hall_dip_get(int idx, int mask)\n"
      "{ return igs017_state::s_hall ? igs017_state::s_hall->hall_dip_get(idx, (u32)mask) : -1; }\n"
"""EMSCRIPTEN_KEEPALIVE int hall_ram8_write(u32 a, int v)
{ if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_ram_w8(a, (u32)v); return 0; }
EMSCRIPTEN_KEEPALIVE int hall_ram16_write(u32 a, int v)
{ if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_ram_w16(a, (u32)v); return 0; }
}""")

for name, a in (("锚1 v12 hall_dip_get收尾+end", A1), ("锚2 v12 hall_dip_get导出收尾", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1）" % (name, src.count(a))); sys.exit(2)

src = src.replace(A1, H1, 1)
src = src.replace(A2, H2, 1)
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: v13 RAM写补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
