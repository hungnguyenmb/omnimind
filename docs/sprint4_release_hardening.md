# Sprint 4 - Release Hardening

## Muc tieu
Giam kha nang reverse runtime Python o ban phat hanh va chuyen luong release sang installer/artefact chinh thuc.

## Da trien khai
1. **Script build hardened**
- File: `scripts/release/build_hardened.py`
- Ho tro:
  - Target: `windows`, `macos`
  - Obfuscation: `none` hoac `pyarmor`
  - Package:
    - Windows: `zip`, `installer`, `both`
    - macOS: `zip`

2. **Template installer Windows (Inno Setup)**
- File: `installer/windows/OmniMind.iss`
- Output mac dinh: `OmniMind-Setup-<version>.exe`

3. **Wrapper script cho team**
- `scripts/release/build_windows_hardened.ps1`
- `scripts/release/build_macos_hardened.sh`

4. **GitHub workflow build release hardened**
- File: `.github/workflows/release-hardened.yml`
- Input runtime:
  - `version`
  - `obfuscate` (`none` | `pyarmor`)
  - `windows_package` (`zip` | `installer` | `both`)
  - `build_macos` (`true` | `false`)

## Cach dung nhanh

### Local Windows
```powershell
python scripts/release/build_hardened.py `
  --target windows `
  --version v1.1.0 `
  --obfuscate pyarmor `
  --package both
```

### Local macOS
```bash
python3 scripts/release/build_hardened.py \
  --target macos \
  --version v1.1.0 \
  --obfuscate pyarmor \
  --package zip
```

### GitHub Actions
- Vao workflow `Release OmniMind Hardened`
- Chon input phu hop
- Tai artefact trong tab Actions

## Rui ro logic va muc do anh huong

### 1. Rui ro runtime app
- **Muc do: Thap**
- Ly do: Sprint nay khong sua logic engine/UI, chi them build pipeline.

### 2. Rui ro build fail khi bat obfuscation
- **Muc do: Trung binh**
- Nguyen nhan: PyArmor co the khong co san, hoac 1 so module dynamic import bi anh huong.
- Giam thieu:
  - Cho phep fallback `--obfuscate none`
  - Smoke-test artefact truoc khi release

### 3. Rui ro installer toolchain
- **Muc do: Trung binh**
- Nguyen nhan: Windows installer can Inno Setup (ISCC)
- Giam thieu:
  - Workflow da tu cai Inno Setup bang choco
  - Bao loi ro rang neu thieu tool

### 4. Rui ro debug/forensics
- **Muc do: Trung binh**
- Nguyen nhan: Obfuscation lam stacktrace kho doc hon
- Giam thieu:
  - Giu ban build non-obfuscated cho noi bo QA
  - Tach artefact release/public va artefact debug noi bo

## Checklist truoc release
- [ ] Build `obfuscate=none` pass
- [ ] Build `obfuscate=pyarmor` pass
- [ ] App mo len duoc, dang nhap Codex duoc
- [ ] Telegram bot nhan va tra loi duoc
- [ ] Installer windows cai/chay/go bo binh thuong
- [ ] Luu hash artefact va release note
