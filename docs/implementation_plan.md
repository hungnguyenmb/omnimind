# Vault Resources CRUD with Encryption Implementation Plan

Implement secure Create, Read, Update, and Delete operations for sensitive resources (SSH, Email, API Keys, Database credentials).

## Proposed Changes

### Dependencies

#### [MODIFY] [requirements.txt](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/requirements.txt)
- Add `cryptography>=41.0.0` for secure data encryption.

### Engine Layer

#### [NEW] [security_utils.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/security_utils.py)
- Create a `SecurityUtils` class for encryption and decryption.
- Use a machine-specific key (or a generated one stored in `app_configs`) to encrypt sensitive data.
- Methods: `encrypt(text)`, `decrypt(token)`.

#### [NEW] [vault_manager.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/vault_manager.py)
- Create a `VaultManager` class to handle `vault_resources` table operations.
- Integrate with `SecurityUtils` to encrypt credentials before saving and decrypt after fetching.
- Methods: `get_all_resources()`, `add_resource(data)`, `update_resource(res_id, data)`, `delete_resource(res_id)`.

### UI Layer

#### [MODIFY] [vault_page.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/vault_page.py)
- Initialize `VaultManager` in `__init__`.
- Replace `self._sample_data` with data from `VaultManager`.
- Update `ResourceDialog` to return consistent data structures for CRUD.
- Update `_populate_table` and action handlers (Add, Edit, Delete) to sync with the database.

## Verification Plan

### Manual Verification
1. Add different types of resources (SSH, API Key) and verify they appear in the table.
2. Check the SQLite database directly to ensure `credentials` are stored as encrypted strings, not plain text.
3. Edit a resource and verify the new credentials still work (can be decrypted and shown in Edit dialog).
4. Delete a resource and verify it is removed from UI and DB.
5. Restart the app and verify all resources persist correctly.

---

# Dashboard & Skill Store API Integration Plan

Connect the Dashboard and Skill Store UIs to real backend data and provide update checking and skill download capabilities.

## Proposed Changes

### Engine Layer

#### [NEW] [dashboard_manager.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/dashboard_manager.py)
- Create `DashboardManager` class.
- Methods:
    - `get_license_display_info()`: Reads `license_plan`, `license_expires` and activation status from `app_configs`.
    - `check_for_updates()`: Hits `/api/v1/omnimind/app/version` and returns info on whether a newer version exists.

#### [NEW] [skill_store_manager.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/engine/skill_store_manager.py)
- Create `SkillStoreManager` class.
- Methods:
    - `fetch_skills(page=1, per_page=20)`: Hits `/api/v1/omnimind/skills` to get the list of available skills.
    - `fetch_skill_manifest(skill_id)`: Hits `/api/v1/omnimind/skills/:id/manifest`.
    - `install_skill(skill_id)`: Mock for now (downloads zip from manifest URL and extracts to a `skills/` directory).

### UI Layer

#### [MODIFY] [dashboard_page.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/dashboard_page.py)
- Initialize `DashboardManager`.
- Update status cards with real data on initialization.
- Implement "Kiểm Tra" button logic to trigger `check_for_updates()`.

#### [MODIFY] [skill_store_page.py](file:///Users/admin/hungnm/work/freelancer/project/antigravity-workspace/projects/omnimind/src/ui/pages/skill_store_page.py)
- Initialize `SkillStoreManager`.
- Replace `STORE_SKILLS` with a dynamic list fetched from the API.
- Implement pagination logic and "Tải Về" button to trigger `install_skill()`.

## Verification Plan

### Manual Verification
1. Open Dashboard and verify "Bản Quyền" and "Phiên Bản" cards show real data.
2. Click "Kiểm Tra" button and verify it correctly detects (or doesn't) a new version.
3. Open Skill Marketplace and verify the list of skills is fetched from the API.
4. Attempt to "Tải Về" a skill and verify it is marked as "Đã cài đặt" after success.
