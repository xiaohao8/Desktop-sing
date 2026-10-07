@echo off
REM 编译保活守护进程（需要 VS 的 x64 工具链）。
REM MSVC 版本路径按本机安装调整；Windows SDK 用 10.0.26100。
REM 产物 watchdog.exe 与 Desktop-sing.exe 同目录分发，主程序自动优先使用。
set MSVC=C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Tools\MSVC\14.44.35207
set SDK=C:\Program Files (x86)\Windows Kits\10
set INCLUDE=%MSVC%\include;%SDK%\Include\10.0.26100.0\ucrt;%SDK%\Include\10.0.26100.0\um;%SDK%\Include\10.0.26100.0\shared
set LIB=%MSVC%\lib\x64;%SDK%\Lib\10.0.26100.0\ucrt\x64;%SDK%\Lib\10.0.26100.0\um\x64
cl /O1 /GS- /utf-8 /W4 /DUNICODE /D_UNICODE watchdog.c /Fe:watchdog.exe /Fo:watchdog.obj /link /subsystem:windows /entry:wWinMainCRTStartup shell32.lib shlwapi.lib user32.lib advapi32.lib
del watchdog.obj
