# FBNeo 回滚联网核心（R1）· 研究原型

> 落点已批：`game-demos/街机模拟器/fbneo-rollback/`（街机对象，与 MAME 线平级）。
> 目标：真回滚（自己操作 0 延迟＝和平精英手感），人数＝游戏原生（BurnDrvGetMaxPlayers，不设上限）。
> 底线：手机真机流畅才上线，不流畅不上（两套 A/B，System A＝现状 MAME 推流兜底）。

## 为什么 FBNeo（不是 MAME）
- libretro 权威共识：FBNeo 把存档＋确定性当所有驱动设计优先级；MAME 存档达不到回滚标准。
- FBNeo 覆盖我们全 11 款（含 outzone Toaplan）；比 MAME 快。
- 现成 @wasm-gaming/fbneo-wasm SDK 是黑盒（只 pause/文件存档槽），**不能回滚**→自建桥直调 burn API。

## 文件
- `rb_bridge.cpp`：回滚桥（追加到 FBNeo src/burner/sdl/main.cpp）。导出 rb_max_players/rb_step/rb_pending/rb_save/rb_load/rb_input_count/rb_input_name/rb_set_input/rb_frame_count/rb_driver_name/rb_set_step_mode。
- `build-fbneo-rollback.sh`：fork wasm-gaming build-fbneo.sh，加 rb_bridge 追加＋run.cpp step 模式（无 pacing 快跑）＋rb_* 导出。bash -n 通过。
- `build-fbneo-rollback.yml`：CI（推仓 .github/workflows/）。emsdk 6.0.2＋SDL2＋pin FBNeo commit d7179fef。

## 原生人数（运行时 BurnDrvGetMaxPlayers 动态读）
captcomm 名将 4P（旧表错写 3）；knights/kod/mercs/wof/dino 3P；ghouls/punisher/pang3/1941/outzone 2P。

## 回滚三要件
1. 手动逐帧：run.cpp step 模式，rb_step(n) 请求 n 帧无 pacing 快跑（重算）。
2. 快照：BurnStateSave/Load 到 MEMFS /save/rb.fs（RAM backed），JS FS.readFile/writeFile 取字节做环形缓冲。
3. 逐帧输入：BurnDrvGetInputInfo pVal 直写（rb_set_input）；JS 按 rb_input_name 做游戏专属 mask→index 映射。

## 状态 / 待迭代
- [x] R1 脚手架（桥＋构建脚本＋CI）。
- [ ] CI 首编（可能需迭代：输入直写须绕过 SDL burner 输入处理；step 模式与 burner 暂停交互；savestate 帧边界）。
- [ ] R2 确定性闸：dino save→load→重跑 N 帧逐位比对（FBNeo 设计保证，仍验）。
- [ ] R3 净码：rollback-netcode（TS/MIT）＋我们 WebRTC。
- [ ] R4 手机性能闸＋4P/加入离开/desync。
- [ ] R5 集成 System B＋A/B。

## 构建仓
paul-189/lhzb2-hall（与 MAME 线同仓）；token 在 routeA-mame-wasm/.github-token；REST 推码触发（github-rest-ci）。
