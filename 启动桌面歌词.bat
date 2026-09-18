@echo off
rem 双击启动桌面歌词（无控制台窗口）
rem 进程保活 / 开机自启都在应用内的「设置面板 → 系统」里开关，正常启动即可

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0lyrics_overlay.py"
) else (
    start "" python "%~dp0lyrics_overlay.py"
)
