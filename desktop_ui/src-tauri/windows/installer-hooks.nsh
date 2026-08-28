!macro NSIS_HOOK_POSTUNINSTALL
  ; Tauri retains the install path and installer-language values in the product key.
  ; This key contains installer metadata only, not governed Temper data, and must not
  ; redirect or block a later install.
  ${If} $UpdateMode <> 1
    DeleteRegKey SHCTX "${MANUPRODUCTKEY}"
    DeleteRegKey /ifempty SHCTX "${MANUKEY}"
  ${EndIf}
!macroend
