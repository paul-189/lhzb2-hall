#!/usr/bin/env python3
# v15 = v14 + ROM 区直写导出 hall_region16_write。
#   用途：lhzb2a 套装在 maincpu region（init 解码后的视图）打 JMP 补丁，
#   等价 rockywall lhzb2a.msf 的 6 个调试断点（bp addr,{pc=target;g}）。
#   68k 核无跨取指缓存，region 写即时生效；zip 保持原始 CRC，不触发加载期校验。
import io, sys, os

V14 = os.path.join(os.path.dirname(__file__), "apply_hall_api_v14.py")
exec(compile(io.open(V14, encoding="utf-8").read(), V14, "exec"))

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

# ---- 1) 类内方法（锚 = v13 的 hall_ram_w16 行）----
A1 = ("\tvoid hall_ram_w16(u32 a, u32 v) { m_maincpu->space(AS_PROGRAM).write_word(a, (u16)v); }\n")
H1 = A1 + ("\t// ROM 区直写：a 为 CPU 字节地址（须偶数），写解码后 maincpu region 的 u16。\n"
           "\tvoid hall_region_w16(u32 a, u32 v)\n"
           "\t{\n"
           "\t\tmemory_region *reg = memregion(\"maincpu\");\n"
           "\t\tif (!reg) return;\n"
           "\t\tu16 *rom = (u16 *)reg->base();\n"
           "\t\trom[a >> 1] = (u16)v;\n"
           "\t}\n")

# ---- 2) extern C 导出（锚 = v14 的 hall_load_state 函数体收尾）----
A2 = ("{ if (!igs017_state::s_hall || !name) return -1; igs017_state::s_hall->machine().schedule_load(std::string(name)); return 0; }\n")
H2 = A2 + ("EMSCRIPTEN_KEEPALIVE int hall_region16_write(u32 a, int v)\n"
           "{ if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_region_w16(a, (u32)v); return 0; }\n")

for name, a in (("锚1 v13 hall_ram_w16", A1), ("锚2 v14 hall_load_state收尾", A2)):
    if src.count(a) != 1:
        print("FAIL: %s 命中 %d 次（必须正好 1）" % (name, src.count(a))); sys.exit(2)

src = src.replace(A1, H1, 1)
src = src.replace(A2, H2, 1)
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: v15 区域写补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
