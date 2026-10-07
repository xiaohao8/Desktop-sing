// ============================================================================
// Desktop-sing 保活守护进程（watchdog）—— C 重写版
//
// 为什么用它：Python 版守护进程 = 再跑一份完整应用（导入全部 PySide6/Qt），
// 只为做「盯着 PID、挂了就重拉」这一件事，保活开启时常驻 ~55MB 内存。
// 这个 C 版做同样的事：常驻内存约 1~2 MB，磁盘约 10 KB。
//
// 协议与 Python 版（lyrics_overlay.py 的 run_supervisor）逐条兼容：
//   · 启动参数   watchdog.exe [--watch-pid <pid>]
//                （不带 --watch-pid = 直接进入拉起循环，开机自启场景）
//   · PID 文件   %APPDATA%\Desktop-sing\supervisor.pid  （写入自己的 PID）
//   · 停机哨兵   %APPDATA%\Desktop-sing\keepalive.off   （存在 = 退出）
//   · 子进程环境 DESKTOP_LYRICS_SUPERVISED=1（防子进程再拉守护进程）
//   · 重启语义   子进程 exit 0 = 正常退出，随之收工；非 0 = 退避后重拉
//                （3s 起步 ×2 递增，上限 60s，防崩溃风暴）
//   · 被监护进程 = 传入的 --watch-pid；它退出后转入拉起循环
//
// 全程 W 系 API：用户目录可能含非 ASCII（中文用户名）。
// GUI 子系统（无控制台）：开机自启经注册表 Run 拉起时不许闪黑窗。
//
// 重新编译（MSVC x64 本机工具命令提示符）：
//   cl /O1 /GS- /W4 /DUNICODE /D_UNICODE watchdog.c /Fe:watchdog.exe ^
//      /link /subsystem:windows /entry:WinMainCRTStartup shell32.lib user32.lib
// 产物 watchdog.exe 放在主程序 Desktop-sing.exe 同目录，主程序会自动优先使用。
// ============================================================================
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <shlwapi.h>
#include <stdio.h>
#include <stdlib.h>

#define POLL_MS          1500      // 监视轮询间隔（与 Python 版一致）
#define BACKOFF_START_S  3
#define BACKOFF_MAX_S   60
// STILL_ACTIVE（259）已在系统头文件 minwinbase.h 里定义，直接用

static WCHAR g_cfg_dir[MAX_PATH];
static WCHAR g_pid_path[MAX_PATH];
static WCHAR g_sentinel_path[MAX_PATH];
static WCHAR g_main_exe[MAX_PATH];

static BOOL file_exists(LPCWSTR path)
{
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static void build_paths(void)
{
    const WCHAR *appdata = _wgetenv(L"APPDATA");
    if (!appdata || !*appdata)
        appdata = L".";
    _snwprintf(g_cfg_dir, MAX_PATH, L"%s\\Desktop-sing", appdata);
    CreateDirectoryW(g_cfg_dir, NULL);      // 已存在则静默
    _snwprintf(g_pid_path,      MAX_PATH, L"%s\\supervisor.pid", g_cfg_dir);
    _snwprintf(g_sentinel_path, MAX_PATH, L"%s\\keepalive.off",  g_cfg_dir);

    // 主程序 = 本文件同目录下的 Desktop-sing.exe
    DWORD n = GetModuleFileNameW(NULL, g_main_exe, MAX_PATH);
    (void)n;
    WCHAR *slash = wcsrchr(g_main_exe, L'\\');
    if (slash) *(slash + 1) = L'\0';
    else       g_main_exe[0]  = L'\0';
    wcscat_s(g_main_exe, MAX_PATH, L"Desktop-sing.exe");
}

static void write_pid_file(void)
{
    HANDLE f = CreateFileW(g_pid_path, GENERIC_WRITE, 0, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE)
        return;
    char buf[16];
    int len = _snprintf(buf, sizeof(buf), "%lu", (unsigned long)GetCurrentProcessId());
    DWORD written = 0;
    if (len > 0)
        WriteFile(f, buf, (DWORD)len, &written, NULL);
    CloseHandle(f);
}

static void clear_pid_file(void)
{
    DeleteFileW(g_pid_path);
}

static BOOL pid_alive(DWORD pid)
{
    if (pid == 0)
        return FALSE;
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h)
        return FALSE;
    DWORD code = 0;
    BOOL ok = GetExitCodeProcess(h, &code);
    CloseHandle(h);
    return ok && code == STILL_ACTIVE;
}

static BOOL stop_requested(void)
{
    return file_exists(g_sentinel_path);
}

// 用主程序的目录作为子进程工作目录；环境变量里带上「已被监护」标记
static BOOL spawn_main(HANDLE *out_proc)
{
    if (!file_exists(g_main_exe))
        return FALSE;

    WCHAR dir[MAX_PATH];
    wcscpy_s(dir, MAX_PATH, g_main_exe);
    WCHAR *slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = L'\0';

    WCHAR cmd[MAX_PATH + 4];
    _snwprintf(cmd, MAX_PATH, L"\"%s\"", g_main_exe);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    // 与 Python 版一致的分离标志：不随守护进程退出、无窗口
    DWORD flags = DETACHED_PROCESS | CREATE_NO_WINDOW;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, flags, NULL, dir, &si, &pi)) {
        return FALSE;
    }
    CloseHandle(pi.hThread);
    if (out_proc)
        *out_proc = pi.hProcess;
    else
        CloseHandle(pi.hProcess);
    return TRUE;
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR pCmdLine, int nShow)
{
    (void)hInst; (void)hPrev; (void)pCmdLine; (void)nShow;

    build_paths();
    // 子进程必须继承「已被监护」标记，否则主程序启动时又会拉一个守护进程，
    // 无限递归（Python 版用同样的环境变量防递归）
    SetEnvironmentVariableW(L"DESKTOP_LYRICS_SUPERVISED", L"1");
    write_pid_file();

    // 启动即清停机哨兵（与 Python 版 run_supervisor 一致：
    // 守护进程正常上岗 = 保活恢复，旧的「不要保活」指令随之作废；
    // 升级接管的等待时序由主程序 spawn_supervisor 负责，这里不管）
    DeleteFileW(g_sentinel_path);

    // ---- 解析 --watch-pid ----
    DWORD watch_pid = 0;
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (argv) {
        for (int i = 1; i < argc; i++) {
            if (lstrcmpiW(argv[i], L"--watch-pid") == 0 && i + 1 < argc)
                watch_pid = (DWORD)wcstoul(argv[i + 1], NULL, 10);
        }
        LocalFree(argv);
    }

    // ---- 第一阶段：监护已运行的实例 ----
    while (watch_pid && pid_alive(watch_pid)) {
        if (stop_requested()) {
            clear_pid_file();
            return 0;
        }
        Sleep(POLL_MS);
    }

    // ---- 第二阶段：拉起循环 ----
    int backoff_s = BACKOFF_START_S;
    for (;;) {
        if (stop_requested())
            break;

        HANDLE child = NULL;
        if (!spawn_main(&child)) {
            // 拉不起（文件缺失/被占用）：退避重试，别转成 CPU 空转
            if (stop_requested())
                break;
            Sleep(backoff_s * 1000);
            backoff_s *= 2;
            if (backoff_s > BACKOFF_MAX_S)
                backoff_s = BACKOFF_MAX_S;
            continue;
        }

        // 等子进程退出；期间哨兵随时生效
        while (WaitForSingleObject(child, POLL_MS) == WAIT_TIMEOUT) {
            if (stop_requested()) {
                // 哨兵出现：主程序可能正在被「退出」流程杀掉。
                // 不再重拉，等它自然退出后收工。
                break;
            }
        }
        DWORD code = 0;
        GetExitCodeProcess(child, &code);
        CloseHandle(child);

        if (code == 0 || stop_requested())
            break;                       // 正常退出 / 用户明确要求停 → 收工

        // 异常退出：退避后重拉
        Sleep(backoff_s * 1000);
        backoff_s *= 2;
        if (backoff_s > BACKOFF_MAX_S)
            backoff_s = BACKOFF_MAX_S;
    }

    clear_pid_file();
    return 0;
}
