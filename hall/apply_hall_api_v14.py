#!/usr/bin/env python3
# v14 = v13 + 读档导出 hall_load_state(name)。
#   走 running_machine::schedule_load（与 F7 同路径，MAME 自选安全时机），
#   文件解析为 state_directory/<系统名>/<name>.sta。厅用它读役满存档，不依赖 -autosave。
import io, sys, os
V13 = os.path.join(os.path.dirname(__file__), "apply_hall_api_v13.py")
exec(compile(io.open(V13, encoding="utf-8").read(), V13, "exec"))

PATH = "src/mame/igs/igs017.cpp"
src = io.open(PATH, encoding="utf-8").read()
orig = src

NL = chr(10)
A = ("EMSCRIPTEN_KEEPALIVE int hall_ram16_write(u32 a, int v)" + NL +
     "{ if (!igs017_state::s_hall) return -1; igs017_state::s_hall->hall_ram_w16(a, (u32)v); return 0; }" + NL)
H = A + ("EMSCRIPTEN_KEEPALIVE int hall_load_state(const char *name)" + NL +
     "{ if (!igs017_state::s_hall || !name) return -1; igs017_state::s_hall->machine().schedule_load(std::string(name)); return 0; }" + NL)
if src.count(A) != 1:
    print("FAIL: v14 锚点命中 %d 次（必须正好 1）" % src.count(A)); sys.exit(2)
src = src.replace(A, H, 1)
io.open(PATH, "w", encoding="utf-8").write(src)
print("OK: v14 读档补丁已应用 %d -> %d 字节（+%d）" % (len(orig), len(src), len(src) - len(orig)))
