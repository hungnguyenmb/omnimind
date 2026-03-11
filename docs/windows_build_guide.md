# Hướng Dẫn Build OmniMind Trên Windows

## Mục tiêu
Tạo bản chạy Windows từ source `projects/omnimind` bằng PyInstaller, ổn định và dễ lặp lại.

## 1. Yêu cầu trước khi build
- Windows 10/11 (64-bit).
- Git.
- Python 3.13 (khuyến nghị đồng bộ với GitHub Actions hiện tại).
- PowerShell.

Kiểm tra nhanh:

```powershell
py -V
git --version
```

## 2. Chuẩn bị source

```powershell
cd <duong-dan-repo>\projects\omnimind
git pull
```

## 3. Tạo môi trường ảo (khuyến nghị bắt buộc cho team)

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

## 4. Build ứng dụng

Chạy lệnh build chuẩn:

```powershell
pyinstaller --clean --noconfirm `
  --name OmniMind `
  --windowed `
  --paths src `
  --icon "assets/app-icons/omnimind.ico" `
  --add-data "src/ui/styles.qss;ui" `
  --add-data "src/ui/assets/omnimind-app.png;ui/assets" `
  src/main.py
```

Sau khi xong, output nằm ở:
- `dist\OmniMind\`

File chạy:
- `dist\OmniMind\OmniMind.exe`

## 5. Đóng gói ZIP để gửi cho máy khác

```powershell
$ts = Get-Date -Format "yyyyMMdd-HHmm"
$zipName = "OmniMind-windows-x64-$ts.zip"
Compress-Archive -Path "dist\OmniMind\*" -DestinationPath $zipName
```

## 6. Kiểm tra trước khi phát hành
- Mở `dist\OmniMind\OmniMind.exe` và vào được UI.
- Test các màn hình chính:
  - Kích hoạt license.
  - Xác thực OmniMind/Codex.
  - Bật Telegram bot.
  - Cài runtime (Node/npm/Python) nếu cần.
- Test gửi 1 tin nhắn Telegram để xác nhận runtime hoạt động.

## 7. Lỗi thường gặp

### 7.1 Thiếu package khi build
Biểu hiện: `ModuleNotFoundError`.
Giải pháp:
- Đảm bảo đã activate `.venv`.
- Cài lại deps:

```powershell
pip install -r requirements.txt
pip install pyinstaller
```

### 7.2 Build xong chạy app bị thiếu giao diện/icon
Giải pháp:
- Kiểm tra lại tham số `--add-data` và `--icon`.
- Không đổi cấu trúc thư mục `src/ui`.

### 7.3 Antivirus/Defender chặn file build
Giải pháp:
- Add exclusion tạm thời cho thư mục project.
- Build lại sau khi whitelist.

### 7.4 Lỗi do cache build cũ
Giải pháp:

```powershell
Remove-Item -Recurse -Force build, dist
pyinstaller --clean --noconfirm ... (chạy lại lệnh build)
```

## 8. Khuyến nghị release chính thức
- Build local chỉ dùng test nhanh nội bộ.
- Bản phát hành chính thức nên dùng GitHub Actions workflow `build-windows.yml` để môi trường đồng nhất.

## 9. Luồng hardened release (Sprint 4)

Khi cần bản phát hành chính thức (giảm lộ cấu trúc runtime), dùng script hardened:

```powershell
.\.venv-build\Scripts\python.exe scripts/release/build_hardened.py `
  --target windows `
  --version v1.1.0 `
  --obfuscate pyarmor `
  --package both
```

Hoặc dùng wrapper:

```powershell
.\scripts\release\build_windows_hardened.ps1 -Version v1.1.0 -Obfuscate pyarmor -Package both
```

Nếu chưa muốn obfuscate trong đợt đầu rollout, đặt `--obfuscate none` để giảm rủi ro build/runtime.

## 10. Bài học quan trọng về `cryptography`

Đã từng gặp trường hợp build pass nhưng app crash ngay khi mở, với lỗi:

```text
ModuleNotFoundError: No module named 'cryptography'
```

Nguyên nhân:
- Chạy build bằng Python/PyInstaller global trên máy thay vì environment `.venv-build`.

Nguyên tắc bắt buộc:
- Hardened build phải chạy bằng `.\.venv-build\Scripts\python.exe`.
- Không gọi `pyinstaller` global từ `PATH` cho release build.

Kiểm tra nhanh trước khi giao artifact:
- Mở app từ `dist` hoặc từ file zip vừa build.
- Nếu app không qua được màn hình khởi động đầu tiên, kiểm tra ngay stderr/log để loại trừ lỗi `cryptography`.
