; 桌面歌词 1.0 安装版 —— NSIS 3.11
; 页面：欢迎 -> 隐私声明(必须勾选同意) -> 安装目录(默认 D:\Desktop-sing) -> 组件 -> 安装 -> 完成
;
; build 2 关键修正：
;   1. 默认安装目录改为纯 ASCII（D:\Desktop-sing），避免中文路径带来的
;      权限/杀软/编码问题；
;   2. 安装前不光按进程名检测，还**直接探测目标文件是否被占用**（FileOpen r+），
;      任何原因（程序在跑、杀软扫描、权限）导致的占用都能抓到并给出明确提示。
Unicode true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"

!define PRODUCT_NAME "桌面歌词"
!define PRODUCT_VER "1.0.0"
!define PRODUCT_EXE "Desktop-sing.exe"
!define DIR_NAME "Desktop-sing"

; ---- 安装器自身的元数据（防报毒：完整版本信息） ----
VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "桌面歌词"
VIAddVersionKey /LANG=2052 "FileDescription" "桌面歌词 1.0 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "1.0.0.0"
VIAddVersionKey /LANG=2052 "ProductVersion" "1.0.0.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Copyright (C) 2026 Desktop-sing Project"
VIAddVersionKey /LANG=2052 "OriginalFilename" "Desktop-sing-Setup-1.0.0.exe"

Name "${PRODUCT_NAME} ${PRODUCT_VER}"
OutFile "..\dist\release\桌面歌词-v1.0.0-安装版.exe"
InstallDir "D:\${DIR_NAME}"
AllowRootDirInstall true
RequestExecutionLevel user

; ---- 图标（真实图标也是防报毒的基本盘） ----
!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"
!define MUI_ABORTWARNING

; ---- 欢迎页文案 ----
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 桌面歌词 1.0"
!define MUI_WELCOMEPAGE_TEXT "本向导将把 桌面歌词 安装到你的电脑。$\r$\n$\r$\n桌面歌词会自动读取系统正在播放的歌曲，在桌面显示卡拉OK式歌词悬浮条。软件完全免费、无广告、不上传任何数据。$\r$\n$\r$\n建议：安装前先从托盘退出正在运行的旧版本。"

; ---- 完成页：可选立即启动 ----
!define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 桌面歌词"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\使用说明.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "查看使用说明"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\build_privacy_unicode.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ------------------------------------------------------------------
; 确保目标文件可写：先把正在跑的实例关掉，再实测文件占用。
; 为什么不只看进程名：进程可能被改名、可能是别的程序/杀软在扫，
; 直接对目标 exe 做「可写打开」探测才是真相。
; ------------------------------------------------------------------
!macro _EnsureWritable UN
Function ${UN}EnsureWritable
  ; ① 按进程名先关一次（静默，没开就什么都不做）
  ReadEnvStr $R2 "COMSPEC"
  nsExec::ExecToStack `$R2 /C tasklist /FI "IMAGENAME eq ${PRODUCT_EXE}" | find /I "${PRODUCT_EXE}"`
  Pop $R0
  Pop $R1
  ${If} $R0 == 0
    MessageBox MB_OKCANCEL|MB_ICONQUESTION \
      "检测到 桌面歌词 正在运行。$\r$\n$\r$\n程序文件被占用会导致安装失败（「无法打开要写入的文件」）。$\r$\n$\r$\n点击「确定」自动关闭它并继续；想保留运行状态请点「取消」稍后再装。" \
      IDOK +2
    Abort
    DetailPrint "正在关闭 桌面歌词 ..."
    nsExec::Exec 'taskkill /F /T /IM ${PRODUCT_EXE}'
    Pop $R0
    Sleep 900
  ${EndIf}

  ; ② 实测目标 exe 能不能写：不能写就循环提示，直到用户处理完
  ${If} ${FileExists} "$INSTDIR\${PRODUCT_EXE}"
    StrCpy $R3 0
    ${Do}
      FileOpen $R4 "$INSTDIR\${PRODUCT_EXE}" a   ; a=追加打开（只探测可写性，不写内容）
      ${If} $R4 != ""
        FileClose $R4
        ${ExitDo}
      ${EndIf}
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION \
        "无法写入：$\r$\n$INSTDIR\${PRODUCT_EXE}$\r$\n$\r$\n该文件正被其它程序占用。请：$\r$\n  1. 右键托盘图标退出「桌面歌词」（旧版可能在托盘里运行）；$\r$\n  2. 或到「任务管理器」结束 Desktop-sing.exe；$\r$\n  3. 稍等几秒让杀毒软件结束扫描。$\r$\n$\r$\n处理完点「重试」；想换目录请点「取消」后重新运行安装程序。" \
        IDRETRY +2
      Abort
      Sleep 500
      IntOp $R3 $R3 + 1
      ${If} $R3 > 60
        Abort
      ${EndIf}
    ${Loop}
  ${EndIf}
FunctionEnd
!macroend
!insertmacro _EnsureWritable ""
!insertmacro _EnsureWritable "un."

; ------------------------------------------------------------------
; 目录可写性探测：$R1 = 目标目录 → $R5 = 1(可写) / 0(不可写)。
; 实测写一个临时文件再删掉，比只看目录属性可靠（ACL / 只读卷 / 受控文件夹
; 访问都能抓到）。$R5 是全局变量，调用方自行读取。
; ------------------------------------------------------------------
Function DirWritable
  CreateDirectory "$R1"
  FileOpen $R6 "$R1\__dl_wtest.tmp" w
  ${If} $R6 == ""
    StrCpy $R5 0
  ${Else}
    FileClose $R6
    Delete "$R1\__dl_wtest.tmp"
    StrCpy $R5 1
  ${EndIf}
FunctionEnd

; ---- 初始化：优先 D:\Desktop-sing；不可写则兜底到用户目录 ----
Function .onInit
  ; ① D 盘不存在 → 直接用用户目录
  ${IfNot} ${FileExists} "D:\*.*"
    StrCpy $INSTDIR "$LOCALAPPDATA\${DIR_NAME}"
  ${EndIf}

  ; ② 实测目标目录可写性（ACL / 只读卷 / 受控文件夹访问都能抓到）
  StrCpy $R1 "$INSTDIR"
  Call DirWritable
  ${If} $R5 == 0
    ${If} $INSTDIR == "D:\${DIR_NAME}"
      ; 默认位置不可写（用户实测：D 盘无写入权限）→ 弹窗告知后换用户目录
      RMDir "$R1"                    ; 探测时可能建出的空目录
      StrCpy $INSTDIR "$LOCALAPPDATA\${DIR_NAME}"
      MessageBox MB_OK|MB_ICONINFORMATION \
        "检测到 D 盘当前没有写入权限（无法在 D:\${DIR_NAME} 创建文件）。$\r$\n$\r$\n安装目录已自动改为：$\r$\n$INSTDIR$\r$\n$\r$\n如果想装到其它位置，可以在下一步自行选择。"
      StrCpy $R1 "$INSTDIR"
      Call DirWritable
      ${If} $R5 == 0
        MessageBox MB_OK|MB_ICONSTOP \
          "安装目录不可写：$\r$\n$INSTDIR$\r$\n$\r$\n请用有写入权限的账户运行，或在「安装目录」页手动选择可写的位置。"
        Abort
      ${EndIf}
    ${Else}
      ; 用户自己指定的目录不可写 → 不擅自改，明确告知后中止
      MessageBox MB_OK|MB_ICONSTOP \
        "指定的安装目录不可写：$\r$\n$INSTDIR$\r$\n$\r$\n请重新运行安装程序，并选择一个有写入权限的目录（例如 C:\Users\<你的用户名>\Desktop-sing）。"
      Abort
    ${EndIf}
  ${EndIf}

  Call EnsureWritable
FunctionEnd

; ---- 用户在「安装目录」页选了不可写的位置时，拦下并说明 ----
Function .onVerifyInstDir
  StrCpy $R1 "$INSTDIR"
  Call DirWritable
  ${If} $R5 == 0
    MessageBox MB_OK|MB_ICONEXCLAMATION \
      "该目录不可写：$\r$\n$INSTDIR$\r$\n$\r$\n请换一个你有写入权限的位置（例如 C:\Users\<你的用户名>\Desktop-sing），或先把该盘/目录的权限调整为可写。"
    Abort
  ${EndIf}
FunctionEnd

Function un.onInit
  Call un.EnsureWritable
FunctionEnd

; ---- 组件 ----
InstType "推荐（完整安装）"
InstType "最小安装"

Section "核心文件（必装）" SEC_CORE
  SectionIn RO 1 2
  SetOutPath "$INSTDIR"
  File /r "..\dist\Desktop-sing-v1.0.0\*.*"
  File /oname=隐私声明.txt "..\PRIVACY.md"
  ; 许可合规：Apache-2.0 第 4 条要求向接收者提供 NOTICE，内置 MiSans 也要求
  ; 保留许可说明。用户装的是这个 exe，看不到 GitHub 仓库 → 必须随包。
  File /oname=第三方许可.txt "..\LICENSE-THIRD-PARTY.txt"
  File "..\使用说明.txt"
  File "..\卸载桌面歌词.bat"
  ; 注册安装信息（控制面板可卸载 / 重装记忆位置）
  WriteRegStr HKCU "Software\Desktop-sing" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "DisplayName" "桌面歌词 ${PRODUCT_VER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "DisplayIcon" "$INSTDIR\${PRODUCT_EXE}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "UninstallString" '"$INSTDIR\卸载桌面歌词.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "DisplayVersion" "${PRODUCT_VER}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "Publisher" "Desktop-sing Project"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing" \
              "NoRepair" 1
  WriteUninstaller "$INSTDIR\卸载桌面歌词.exe"
SectionEnd

Section "桌面快捷方式" SEC_DESK
  SectionIn 1
  SetOutPath "$INSTDIR"
  CreateShortCut "$DESKTOP\桌面歌词.lnk" "$INSTDIR\${PRODUCT_EXE}"
SectionEnd

Section "开始菜单快捷方式" SEC_MENU
  SectionIn 1
  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\桌面歌词"
  CreateShortCut "$SMPROGRAMS\桌面歌词\桌面歌词.lnk" "$INSTDIR\${PRODUCT_EXE}"
  CreateShortCut "$SMPROGRAMS\桌面歌词\卸载桌面歌词.lnk" "$INSTDIR\卸载桌面歌词.exe"
SectionEnd

; ---- 卸载 ----
Section "Uninstall"
  Delete "$DESKTOP\桌面歌词.lnk"
  Delete "$SMPROGRAMS\桌面歌词\桌面歌词.lnk"
  Delete "$SMPROGRAMS\桌面歌词\卸载桌面歌词.lnk"
  RMDir "$SMPROGRAMS\桌面歌词"
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "Software\Desktop-sing"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Desktop-sing"
SectionEnd

LangString DESC_SEC_CORE ${LANG_SIMPCHINESE} "程序本体、内置字体、隐私声明、第三方许可与使用说明。"
LangString DESC_SEC_DESK ${LANG_SIMPCHINESE} "在桌面创建 桌面歌词 快捷方式。"
LangString DESC_SEC_MENU ${LANG_SIMPCHINESE} "在开始菜单创建程序与卸载入口。"

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_CORE} $(DESC_SEC_CORE)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESK} $(DESC_SEC_DESK)
  !insertmacro MUI_DESCRIPTION_TEXT ${SEC_MENU} $(DESC_SEC_MENU)
!insertmacro MUI_FUNCTION_DESCRIPTION_END
