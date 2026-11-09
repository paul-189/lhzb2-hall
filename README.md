# lhzb2-hall

官方 MAME 0.289 的 `src/mame/igs/igs017.cpp` 上打一层“厅用接口”补丁，编成浏览器可跑的 wasm。**不含任何 ROM**（ROM 由使用者自己提供，也不要把 lhzb2.zip 提交进来）。

- `hall/apply_hall_api.py` — 补丁脚本（锚点不对就失败退出）
- `.github/workflows/build-wasm.yml` — CI：取官方源码 → 打补丁 → Emscripten 6.0.2 → 编 IGS017 一族 → 发 Release
- 导出的 C 接口：`hall_coin()` / `hall_key(bank,mask,val)` / `hall_state_word()` / `hall_credit()` / `hall_bet_level()` / `hall_ram8/16`
