# OmniMind Zalo Phase 1 Checklist

Ngày tạo: `2026-03-11`

Tài liệu này dùng để triển khai và theo dõi tiến độ `Phase 1 - OpenZCA Runtime Foundation` cho tích hợp Zalo trong `projects/omnimind`.

Tham chiếu gốc:
- [zalo_openzca_master_plan.md](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/docs/zalo_openzca_master_plan.md)

## Mục tiêu Phase 1

Kết thúc Phase 1, OmniMind phải:
- Tự kiểm tra được `node` và `npm`.
- Tự cài được `openzca` local vào app data.
- Tự resolve được binary `openzca` bằng absolute path trên `macOS` và `Windows`.
- Tạo và dùng được `OPENZCA_HOME` riêng.
- Chuẩn hóa `profile_name = omnimind`.
- Hiển thị rõ trạng thái runtime `openzca` trong UI.
- Có nút `Install` / `Repair` mà không cần người dùng dùng terminal.

Phase 1 chưa bao gồm:
- Login QR Zalo
- Auth status
- Connection monitor
- Listener nhận tin nhắn
- Auto reply
- Group mention
- Prompt Zalo

## Exit Criteria

Chỉ được xem là hoàn tất Phase 1 khi thỏa cả các điều kiện:
- `openzca` được cài local thành công trên `macOS`.
- `openzca` được cài local thành công trên `Windows`.
- App khởi động lại vẫn nhận ra runtime đã cài.
- Không dùng `npm install -g openzca` làm mặc định.
- Không đặt runtime `openzca` trong thư mục payload versioned của cơ chế update.
- Runtime `openzca` và home/session nằm trong app data root bền vững.

## 1) Chuẩn bị branch và phạm vi

- [ ] Tạo branch riêng cho tính năng Zalo, dự kiến: `feature/zalo-codex-bot-v1`
- [ ] Kiểm tra worktree hiện tại để tránh ghi đè thay đổi unrelated
- [ ] Xác nhận agent triển khai chỉ làm `Phase 1`, chưa lấn sang login/bot runtime
- [ ] Xác nhận lại các quyết định nền tảng:
  - [ ] `openzca` cài local
  - [ ] `1 profile cố định = omnimind`
  - [ ] `1 tài khoản Zalo tại 1 thời điểm`
  - [ ] `login tài khoản mới sẽ ghi đè session cũ`

## 2) Thiết kế path và runtime layout

- [ ] Chốt app data root theo OS:
  - [ ] macOS: `~/Library/Application Support/OmniMind`
  - [ ] Windows: `%LOCALAPPDATA%\\OmniMind`
- [ ] Chốt thư mục runtime:
  - [ ] `<app_data>/openzca-runtime`
- [ ] Chốt thư mục session/home:
  - [ ] `<app_data>/openzca-home`
- [ ] Chốt thư mục log nếu cần:
  - [ ] `<app_data>/logs`
- [ ] Xác nhận `openzca-runtime` và `openzca-home` không nằm trong `updates/payloads/<version>`
- [ ] Chốt `profile_name = omnimind`

## 3) Tạo `openzca_manager.py`

File:
- [ ] Tạo [openzca_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/openzca_manager.py)

### 3.1 Path helpers

- [ ] Implement `get_app_data_root()`
- [ ] Implement `get_openzca_runtime_root()`
- [ ] Implement `get_openzca_home()`
- [ ] Implement `get_openzca_logs_dir()`
- [ ] Implement `get_profile_name()`

### 3.2 Runtime detection

- [ ] Implement `is_node_available()`
- [ ] Implement `is_npm_available()`
- [ ] Implement `get_node_version()`
- [ ] Implement `get_npm_version()`
- [ ] Implement `check_openzca_installed()`
- [ ] Implement `get_openzca_version()`

### 3.3 Command resolution

- [ ] Implement `get_openzca_command()`
- [ ] Hỗ trợ binary local trên macOS/Linux
- [ ] Hỗ trợ binary local `.cmd` trên Windows
- [ ] Verify command path tồn tại trước khi trả về
- [ ] Không phụ thuộc `PATH` global để chạy `openzca`

### 3.4 Install / repair logic

- [ ] Implement `install_openzca(target_version=None)`
- [ ] Implement `ensure_openzca_installed(target_version=None)`
- [ ] Implement `repair_openzca()`
- [ ] Implement cleanup runtime hỏng trước khi repair nếu cần
- [ ] Dùng `npm install --prefix <runtime_dir> openzca@<version-or-latest>`
- [ ] Verify sau cài bằng `openzca --version` hoặc `openzca --help`

### 3.5 Environment builder

- [ ] Implement `build_openzca_env()`
- [ ] Inject `OPENZCA_HOME`
- [ ] Nếu cần, inject `OPENZCA_PROFILE=omnimind`

### 3.6 Error handling

- [ ] Chuẩn hóa lỗi thiếu `node`
- [ ] Chuẩn hóa lỗi thiếu `npm`
- [ ] Chuẩn hóa lỗi install timeout
- [ ] Chuẩn hóa lỗi binary không resolve được
- [ ] Chuẩn hóa lỗi verify sau install thất bại

## 4) Tích hợp với config

File:
- [ ] Sửa [config_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/config_manager.py)

### 4.1 Config keys

- [ ] Thêm `zalo_profile_name`
- [ ] Thêm `zalo_openzca_version`
- [ ] Thêm `zalo_openzca_install_status`
- [ ] Thêm `zalo_runtime_last_error`
- [ ] Thêm `zalo_runtime_last_checked_at`

### 4.2 Defaults

- [ ] Default `zalo_profile_name = omnimind`
- [ ] Default `zalo_openzca_install_status = not_installed`

### 4.3 Helpers

- [ ] Thêm helper `get_zalo_runtime_config()`
- [ ] Thêm helper `set_zalo_runtime_status(...)`
- [ ] Ghi `last_error` để UI có thể đọc

## 5) Tái sử dụng logic cross-platform hiện có

Files:
- [ ] Rà soát [environment_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/environment_manager.py)

Checklist:
- [ ] Tận dụng lại app data root logic thay vì copy-paste path resolver mới
- [ ] Tận dụng logic PATH user-level trên macOS nếu cần
- [ ] Tận dụng logic hidden subprocess trên Windows nếu cần
- [ ] Tránh duplicate quá nhiều utility giữa `EnvironmentManager` và `OpenZcaManager`

## 6) UI runtime block trong Auth page

File:
- [ ] Sửa [auth_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/auth_page.py)

### 6.1 Hiển thị trạng thái

- [ ] Hiển thị trạng thái `Node`
- [ ] Hiển thị trạng thái `npm`
- [ ] Hiển thị trạng thái `openzca`
- [ ] Hiển thị `openzca version`
- [ ] Hiển thị runtime path
- [ ] Hiển thị home path
- [ ] Hiển thị profile `omnimind`

### 6.2 Action buttons

- [ ] Thêm nút `Kiểm tra openzca`
- [ ] Thêm nút `Cài openzca`
- [ ] Thêm nút `Repair openzca`

### 6.3 UI state labels

- [ ] Có trạng thái `Chưa cài`
- [ ] Có trạng thái `Đang kiểm tra`
- [ ] Có trạng thái `Đang cài`
- [ ] Có trạng thái `Sẵn sàng`
- [ ] Có trạng thái `Lỗi cài đặt`

### 6.4 Worker/background handling

- [ ] Việc kiểm tra/cài đặt không block UI thread
- [ ] Có callback cập nhật trạng thái khi cài đặt xong
- [ ] Hiển thị lỗi cài đặt ngắn gọn, dễ hiểu

## 7) Dashboard integration tối thiểu

Files:
- [ ] Cân nhắc sửa [dashboard_manager.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/dashboard_manager.py) nếu cần
- [ ] Cân nhắc sửa [dashboard_page.py](/Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/dashboard_page.py) nếu cần

Checklist:
- [ ] Nếu làm ở Phase 1, chỉ hiển thị read-only runtime status
- [ ] Không thêm logic start/stop bot Zalo ở phase này
- [ ] Không thêm login state ở phase này

## 8) Install flow chi tiết

- [ ] Kiểm tra `node --version`
- [ ] Kiểm tra `npm --version`
- [ ] Tạo thư mục runtime nếu chưa có
- [ ] Chạy `npm install --prefix <openzca-runtime> openzca@latest` hoặc target version
- [ ] Resolve binary local
- [ ] Chạy lệnh verify
- [ ] Ghi version đã cài vào config
- [ ] Ghi install status cuối cùng vào config

## 9) Windows-specific checklist

- [ ] Dùng subprocess args dạng list, không ghép command string tay
- [ ] Ẩn cửa sổ console cho command nền/cài đặt
- [ ] Resolve đúng `openzca.cmd` nếu npm tạo file `.cmd`
- [ ] Xử lý đúng path có khoảng trắng trong `%LOCALAPPDATA%`
- [ ] Verify lại command sau install trên Windows thật

## 10) macOS-specific checklist

- [ ] Verify app mở từ Finder vẫn resolve được `node` / `npm` nếu đã cài đúng
- [ ] Nếu PATH shell không đủ, đảm bảo vẫn gọi được binary local bằng absolute path
- [ ] Verify install và re-open app vẫn nhận đúng runtime

## 11) Logging và telemetry tối thiểu

- [ ] Log trạng thái check/install `openzca` vào `omnimind_app.log`
- [ ] Log lỗi runtime install rõ ràng
- [ ] Persist `zalo_runtime_last_error`
- [ ] Persist `zalo_runtime_last_checked_at`

Phase 1 chưa bắt buộc:
- [ ] JSONL structured logs riêng cho inbound/outbound Zalo

## 12) Negative test checklist

- [ ] Máy thiếu `node`, UI báo lỗi đúng
- [ ] Máy thiếu `npm`, UI báo lỗi đúng
- [ ] Install bị timeout, UI báo lỗi đúng
- [ ] Runtime folder bị xóa thủ công, app detect lại là chưa cài
- [ ] Runtime hỏng, nút `Repair openzca` hoạt động
- [ ] Verify command thất bại, app không đánh dấu nhầm là `Sẵn sàng`

## 13) Manual verification checklist

### macOS

- [ ] Cài `openzca` local thành công
- [ ] Hiển thị đúng version `openzca`
- [ ] Tạo đúng `openzca-home`
- [ ] Tạo đúng `profile_name = omnimind`
- [ ] Đóng mở lại app vẫn nhận là runtime đã sẵn sàng

### Windows

- [ ] Cài `openzca` local thành công
- [ ] Không bật console khó chịu khi chạy flow nền
- [ ] Hiển thị đúng version `openzca`
- [ ] Tạo đúng `openzca-home`
- [ ] Đóng mở lại app vẫn nhận là runtime đã sẵn sàng

## 14) Definition of Done cho từng file

### `src/engine/openzca_manager.py`

- [ ] Có đầy đủ path resolver
- [ ] Có install flow
- [ ] Có repair flow
- [ ] Có verify flow
- [ ] Hoạt động trên macOS
- [ ] Hoạt động trên Windows

### `src/engine/config_manager.py`

- [ ] Có config keys cho runtime Zalo
- [ ] Có helper read/write trạng thái runtime

### `src/ui/pages/auth_page.py`

- [ ] Có khu vực runtime Zalo
- [ ] Có trạng thái rõ ràng
- [ ] Có nút kiểm tra/cài/repair
- [ ] Không block UI

### `src/engine/environment_manager.py`

- [ ] Chỉ chỉnh nếu thật sự cần để tái sử dụng helper cross-platform
- [ ] Không làm tăng coupling quá mức

## 15) Ghi chú triển khai

- [ ] Không dùng global npm install làm mặc định
- [ ] Không tạo profile mới ngoài `omnimind`
- [ ] Không lấn sang login QR trong Phase 1
- [ ] Không đặt session/runtime vào vùng payload update theo version
- [ ] Không refactor lớn `TelegramBotService` trong Phase 1

