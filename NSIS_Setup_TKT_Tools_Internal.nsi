; --- Script tạo bộ cài đặt cho TKT Multiform bằng NSIS (Đã sửa lỗi) ---

;================================
; 1. Thuộc tính cơ bản của ứng dụng
;================================
!define APP_NAME "TKT Multiform"
!define APP_VERSION "1.0"
!define PUBLISHER "TKT"
!define EXE_NAME "TKT_Multiform.exe"
; Thư mục chứa file .exe sau khi đóng gói bằng PyInstaller
!define SOURCE_FOLDER "dist" 

;================================
; 2. Cài đặt chung cho Installer
;================================
; Tên file .exe của bộ cài sẽ được tạo ra
OutFile "TKT_Multiform_Installer_v${APP_VERSION}.exe"

; Yêu cầu quyền Administrator để cài đặt
RequestExecutionLevel admin

; Thư mục cài đặt mặc định (trong Program Files)
InstallDir "$PROGRAMFILES64\${APP_NAME}"

;================================
; 3. Giao diện bộ cài
;================================
; Sử dụng giao diện Modern UI
!include "MUI2.nsh"

; Dùng MUI_ICON và MUI_UNICON
!define MUI_ICON "assets\logo.ico"
!define MUI_UNICON "assets\logo.ico"

; Trang chào mừng
!insertmacro MUI_PAGE_WELCOME
; Trang chọn thư mục cài đặt
!insertmacro MUI_PAGE_DIRECTORY
; Trang cài đặt (hiển thị tiến trình)
!insertmacro MUI_PAGE_INSTFILES
; Trang hoàn tất
!insertmacro MUI_PAGE_FINISH

; Giao diện cho trình gỡ cài đặt
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Ngôn ngữ
!insertmacro MUI_LANGUAGE "Vietnamese"

;================================
; 4. Section Cài đặt chính
;================================
Section "Cài đặt ${APP_NAME}"

  ; Thiết lập thư mục đích để sao chép file
  SetOutPath $INSTDIR
  
  ; Sao chép TẤT CẢ các file và thư mục con từ thư mục nguồn vào thư mục cài đặt
  File /r "${SOURCE_FOLDER}\*.*"
  
  ; --- Tạo shortcut ---
  ; SỬA LỖI: Thêm dấu '\' vào tất cả các đường dẫn
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0
  
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${EXE_NAME}" "" "$INSTDIR\${EXE_NAME}" 0

  ; --- Ghi thông tin vào Registry để gỡ cài đặt (Add/Remove Programs) ---
  ; SỬA LỖI: Tách các lệnh ra từng dòng riêng biệt và thêm dấu '\'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\${EXE_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${PUBLISHER}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
  
  ; Tạo file gỡ cài đặt
  WriteUninstaller "$INSTDIR\uninstall.exe"
  
SectionEnd

;================================
; 5. Section Gỡ cài đặt
;================================
Section "Uninstall"

  ; --- Xóa file và thư mục ---
  Delete "$INSTDIR\${EXE_NAME}"
  Delete "$INSTDIR\uninstall.exe"
  
  RMDir /r "$INSTDIR"
  
  ; --- Xóa shortcut ---
  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  RMDir "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  
  ; --- Xóa thông tin trong Registry ---
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
  
SectionEnd