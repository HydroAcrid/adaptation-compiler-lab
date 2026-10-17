; RMDir /r follows junctions. Validate the exact executable cache and every
; ancestor/descendant before mutation; never recurse into redirected paths.
!macro TemperCacheFunctions PREFIX
Function ${PREFIX}TemperValidateCacheTree
  Exch $0
  Push $1
  Push $2
  Push $3
  System::Call 'kernel32::GetFileAttributesW(w r0) i.r3'
  ${If} $3 != -1
    IntOp $3 $3 & 0x400
    ${If} $3 != 0
      SetErrorLevel 1
      Abort "Temper engine cache is redirected; no files were removed."
    ${EndIf}
    FindFirst $1 $2 "$0\*"
    ${DoWhile} $2 != ""
      ${If} $2 != "."
      ${AndIf} $2 != ".."
        System::Call 'kernel32::GetFileAttributesW(w "$0\$2") i.r3'
        IntOp $3 $3 & 0x400
        ${If} $3 != 0
          SetErrorLevel 1
          Abort "Temper engine cache is redirected; no files were removed."
        ${EndIf}
        System::Call 'kernel32::GetFileAttributesW(w "$0\$2") i.r3'
        IntOp $3 $3 & 0x10
        ${If} $3 != 0
          Push "$0\$2"
          Call ${PREFIX}TemperValidateCacheTree
        ${EndIf}
      ${EndIf}
      FindNext $1 $2
    ${Loop}
    FindClose $1
  ${EndIf}
  Pop $3
  Pop $2
  Pop $1
  Pop $0
FunctionEnd

Function ${PREFIX}TemperCleanEngineCache
  Push $0
  Push $1
  ${If} $INSTDIR == ""
    SetErrorLevel 1
    Abort "Temper install directory is unavailable."
  ${EndIf}
  GetFullPathName $0 "$INSTDIR\.temper-engine-cache"
  ; Check ancestors separately, without recursively visiting unrelated data.
  ${Do}
    System::Call 'kernel32::GetFileAttributesW(w r0) i.r1'
    ${If} $1 != -1
      IntOp $1 $1 & 0x400
      ${If} $1 != 0
        SetErrorLevel 1
        Abort "Temper cache path is redirected; no files were removed."
      ${EndIf}
    ${EndIf}
    ${GetParent} "$0" $1
    ${If} $1 == ""
    ${OrIf} $1 == $0
      ${ExitDo}
    ${EndIf}
    StrCpy $0 $1
  ${Loop}
  Push "$INSTDIR\.temper-engine-cache"
  Call ${PREFIX}TemperValidateCacheTree
  ClearErrors
  RMDir /r "$INSTDIR\.temper-engine-cache"
  System::Call 'kernel32::GetFileAttributesW(w "$INSTDIR\.temper-engine-cache") i.r0'
  ${If} $0 != -1
    SetErrorLevel 1
    MessageBox MB_OK|MB_ICONSTOP "Close Temper and Codex chats using Temper before upgrading." /SD IDOK
    Abort
  ${EndIf}
  ClearErrors
  Pop $1
  Pop $0
FunctionEnd
!macroend

!insertmacro TemperCacheFunctions ""
!insertmacro TemperCacheFunctions "un."

!macro NSIS_HOOK_PREINSTALL
  Call TemperCleanEngineCache
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  Call un.TemperCleanEngineCache
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; Tauri retains the install path and installer-language values in the product key.
  ; This key contains installer metadata only, not governed Temper data, and must not
  ; redirect or block a later install.
  ${If} $UpdateMode <> 1
    DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
    DeleteRegKey /ifempty SHCTX "${MANUKEY}"
  ${EndIf}
!macroend
