// rb_bridge.cpp — FBNeo 回滚联网桥（R1）
// 由 build-fbneo-rollback.sh 追加到 src/burner/sdl/main.cpp（与 web_bridge.cpp 并列）。
// 把 FBNeo 从「黑盒自走循环」改造成「可手动逐帧＋快照＋逐帧输入」的回滚核心。
// 回滚三要件（burn.h 已核实）：
//   1) 手动逐帧：run.cpp 循环补丁加 step 模式，rb_step(n) 请求 n 帧，无 pacing 快跑（重算用）。
//   2) 快照：复用 BurnStateSave/BurnStateLoad 到 MEMFS /save/rb.fs（RAM backed），
//      JS 侧 FS.readFile/writeFile 取字节做环形快照缓冲。
//   3) 逐帧输入：BurnDrvGetInputInfo 拿 pVal，rb_set_input(i,v) 直写驱动输入锁存。
//   人数：BurnDrvGetMaxPlayers() 运行时返回原生最大人数（不设上限）。
// 注意：输入直写 pVal 须绕过 SDL burner 键盘/手柄处理（inp_sdl2.cpp 覆盖 GameInp）；
//       step 模式下 burner 输入处理应跳过，由 JS 每帧注入。建时迭代核实。
#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#include <cstdio>
#include <cstring>
extern int bWebPaused;     // web_bridge.cpp
extern int bWebQuit;       // web_bridge.cpp
// step 模式状态（run.cpp 循环补丁读这些）
int bRbStepMode = 0;       // 1=手动步进（回滚）；0=自走 pacing
int nRbStepFrames = 0;     // 待推进帧数；循环每跑一帧减 1
int nRbFrameCount = 0;     // 自 init 累计推进帧（双方同步基准）
extern "C" {
EMSCRIPTEN_KEEPALIVE int rb_max_players(void){ if(!bDrvOkay) return 0; return BurnDrvGetMaxPlayers(); }
EMSCRIPTEN_KEEPALIVE const char* rb_driver_name(void){ if(!bDrvOkay) return ""; return BurnDrvGetText(DRV_NAME); }
EMSCRIPTEN_KEEPALIVE int rb_frame_count(void){ return nRbFrameCount; }
EMSCRIPTEN_KEEPALIVE void rb_set_step_mode(int on){ bRbStepMode=on?1:0; if(!on) nRbStepFrames=0; }
EMSCRIPTEN_KEEPALIVE void rb_step(int n){ if(n<0)n=0; bRbStepMode=1; bWebPaused=0; nRbStepFrames=n; }
EMSCRIPTEN_KEEPALIVE int rb_pending(void){ return nRbStepFrames; }
EMSCRIPTEN_KEEPALIVE int rb_save(void){ if(!bDrvOkay) return 0; return BurnStateSave("/save/rb.fs",1)==0?1:0; }
EMSCRIPTEN_KEEPALIVE int rb_load(void){ if(!bDrvOkay) return 0; return BurnStateLoad("/save/rb.fs",1,NULL)==0?1:0; }
EMSCRIPTEN_KEEPALIVE int rb_input_count(void){ if(!bDrvOkay) return 0; int n=0; struct BurnInputInfo bii; while(BurnDrvGetInputInfo(&bii,n)==0) n++; return n; }
EMSCRIPTEN_KEEPALIVE const char* rb_input_name(int i){ static struct BurnInputInfo bii; if(BurnDrvGetInputInfo(&bii,i)!=0) return ""; return bii.szName?bii.szName:""; }
EMSCRIPTEN_KEEPALIVE int rb_set_input(int i,int v){ struct BurnInputInfo bii; if(BurnDrvGetInputInfo(&bii,i)!=0) return 0; if(!bii.pVal) return 0; *bii.pVal=(unsigned char)(v?1:0); return 1; }

// ---- 同步单帧（rollback-netcode Game.step 用，同步非ASYNCIFY）----
// 直调 BurnDrvFrame：它读驱动输入锁存（rb_set_input 已写），不调 InputMake（ burner 实时轮询），
// 复用 boot 设好的 pBurnDraw/pBurnSoundOut。一帧确定性单元（R2 已证 RunFrame 确定）。
EMSCRIPTEN_KEEPALIVE void rb_tick(void)
{
	if (!bDrvOkay) return;
	BurnDrvFrame();
}
// 帧缓冲直读（绕 VidPaint 的 GL，headless 下 GL 刷屏越界）。JS 读 HEAPU8 转 RGBA 画 2D canvas。
EMSCRIPTEN_KEEPALIVE INT32 rb_framebuf(void){ return (INT32)(uintptr_t)pVidImage; }
EMSCRIPTEN_KEEPALIVE INT32 rb_vidwidth(void){ return nVidWidth; }
EMSCRIPTEN_KEEPALIVE INT32 rb_vidheight(void){ return nVidHeight; }
EMSCRIPTEN_KEEPALIVE INT32 rb_viddepth(void){ return nVidDepth; }
// 渲染开关：回滚重算时 off（pBurnDraw=NULL 跳视频，快）；显示帧 on。
EMSCRIPTEN_KEEPALIVE void rb_setrender(int on){ pBurnDraw = on ? pVidImage : (UINT8*)0; }
// 声音缓冲直读（帧钟同步喂 Web Audio）。pBurnSoundOut 每帧 nAudNextSound 字节 16bit 立体声。
EMSCRIPTEN_KEEPALIVE INT32 rb_soundbuf(void){ return (INT32)(uintptr_t)(void*)pBurnSoundOut; }
EMSCRIPTEN_KEEPALIVE INT32 rb_soundlen(void){ return nAudNextSound; }
EMSCRIPTEN_KEEPALIVE INT32 rb_soundrate(void){ return nBurnSoundRate; }
EMSCRIPTEN_KEEPALIVE INT32 rb_drvwidth(void){ INT32 w=0,h=0; BurnDrvGetVisibleSize(&w,&h); return w; }
EMSCRIPTEN_KEEPALIVE INT32 rb_drvheight(void){ INT32 w=0,h=0; BurnDrvGetVisibleSize(&w,&h); return h; }

} // extern "C"
#endif
