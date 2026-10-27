@echo off
rem Desktop-sing diagnostic collector - run on the machine where the app fails.
rem Outputs one txt on the Desktop; send it back for analysis. ASCII-only on purpose.
setlocal
set OUT=%USERPROFILE%\Desktop\desktop-sing-diag.txt
echo ===== Desktop-sing diagnostics ===== > "%OUT%"
date /t >> "%OUT%" 2>&1
time /t >> "%OUT%" 2>&1

echo --- 1. OS build --- >> "%OUT%"
ver >> "%OUT%" 2>&1
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v DisplayVersion >> "%OUT%" 2>&1
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CurrentBuild >> "%OUT%" 2>&1
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v UBR >> "%OUT%" 2>&1

echo --- 2. running process --- >> "%OUT%"
tasklist /FI "IMAGENAME eq Desktop-sing.exe" >> "%OUT%" 2>&1

echo --- 3. files under APPDATA\Desktop-sing --- >> "%OUT%"
dir /s /b "%APPDATA%\Desktop-sing" >> "%OUT%" 2>&1

echo --- 4. desktop-lyrics.log --- >> "%OUT%"
type "%APPDATA%\Desktop-sing\desktop-lyrics.log" >> "%OUT%" 2>&1

echo --- 5. fatal.txt --- >> "%OUT%"
type "%APPDATA%\Desktop-sing\fatal.txt" >> "%OUT%" 2>&1

echo --- 6. MSIX package data (if store/msix build was installed) --- >> "%OUT%"
dir /s /b "%LOCALAPPDATA%\Packages\A135C2AE.Desktop-sing_8ahsnwh40hshg" >> "%OUT%" 2>&1

echo --- 7. recent Application Error events --- >> "%OUT%"
wevtutil qe Application "/q:*[System[Provider[@Name='Application Error']]]" /c:5 /rd:true /f:text >> "%OUT%" 2>&1

echo --- 8. recent Application Hang events --- >> "%OUT%"
wevtutil qe Application "/q:*[System[Provider[@Name='Application Hang']]]" /c:5 /rd:true /f:text >> "%OUT%" 2>&1

echo ===== DONE ===== >> "%OUT%"
echo.
echo Wrote %OUT% - please send this file back.
endlocal
