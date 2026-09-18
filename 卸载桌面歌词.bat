@echo off
chcp 65001 >nul 2>&1
title 卸载 桌面歌词 (Desktop-sing)
setlocal
set "PROGDIR=%~1"
if "%PROGDIR%"=="" set "PROGDIR=%~dp0"

REM 把自身复制到临时目录再从那里运行，确保能完整删除原程序目录（含本脚本自身）
if /i not "%~dp0"=="%TEMP%\" (
  if exist "%TEMP%\卸载桌面歌词_tmp.bat" del /f /q "%TEMP%\卸载桌面歌词_tmp.bat" >nul 2>&1
  copy /y "%~f0" "%TEMP%\卸载桌面歌词_tmp.bat" >nul 2>&1
  if exist "%TEMP%\卸载桌面歌词_tmp.bat" (
    start "" /min "%TEMP%\卸载桌面歌词_tmp.bat" "%PROGDIR%"
    exit /b
  )
)

echo ================================================
echo          卸载 桌面歌词 (Desktop-sing)
echo ================================================
echo.
echo [1/3] 正在关闭正在运行的 桌面歌词 ...
taskkill /f /im Desktop-sing.exe >nul 2>&1
timeout /t 1 >nul 2>&1

echo [2/3] 删除开机自启项（如已设置，需管理员权限时可能跳过）...
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Desktop-sing" /f >nul 2>&1

echo [3/3] 删除配置目录与程序目录...
rmdir /s /q "%APPDATA%\Desktop-sing" >nul 2>&1
rmdir /s /q "%PROGDIR%" >nul 2>&1

echo.
echo 卸载完成。若仍提示"文件正在使用"，请稍候几秒后重跑本脚本。
echo.
pause
