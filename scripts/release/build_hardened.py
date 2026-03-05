#!/usr/bin/env python3
"""Build hardened release artifacts for OmniMind.

This script is intentionally additive: it does not modify runtime logic.
It prepares release artifacts from source with optional obfuscation.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "release-artifacts"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(cmd)
    print(f"[run] {printable}")
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def _check_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Missing required command: {name}")
    return path


def _copy_project_to(work_dir: Path) -> None:
    # Only include files needed for build, keep temporary context small.
    for rel in ["src", "assets", "requirements.txt", "OmniMind.spec", "OmniMind-Intel.spec"]:
        src = PROJECT_ROOT / rel
        dst = work_dir / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        elif src.exists():
            shutil.copy2(src, dst)


def _obfuscate_src_pyarmor(work_dir: Path) -> None:
    _check_command("pyarmor")
    src_dir = work_dir / "src"
    out_dir = work_dir / "_src_obf"

    # pyarmor writes obfuscated code into out_dir/src/...
    _run([
        "pyarmor",
        "gen",
        "-r",
        "-i",
        "-O",
        str(out_dir),
        str(src_dir),
    ])

    obf_src = out_dir / "src"
    if not obf_src.exists():
        raise RuntimeError("PyArmor output does not contain expected src directory")

    shutil.rmtree(src_dir)
    shutil.copytree(obf_src, src_dir)


def _build_pyinstaller(work_dir: Path, target: str) -> Path:
    _check_command("pyinstaller")

    if target == "windows":
        cmd = [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            "--name",
            "OmniMind",
            "--windowed",
            "--paths",
            "src",
            "--icon",
            "assets/app-icons/omnimind.ico",
            "--add-data",
            "src/ui/styles.qss;ui",
            "--add-data",
            "src/ui/assets/omnimind-app.png;ui/assets",
            "src/main.py",
        ]
    elif target == "macos":
        cmd = [
            "pyinstaller",
            "--clean",
            "--noconfirm",
            str(work_dir / "OmniMind.spec"),
        ]
    else:
        raise ValueError(f"Unsupported target: {target}")

    _run(cmd, cwd=work_dir)

    dist_name = "OmniMind" if target == "windows" else "OmniMind.app"
    output_path = work_dir / "dist" / dist_name
    if not output_path.exists():
        raise RuntimeError(f"Build output not found: {output_path}")
    return output_path


def _zip_artifact(src_path: Path, output_zip: Path) -> Path:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()

    with tempfile.TemporaryDirectory(prefix="omnimind-zip-") as tmp:
        staging = Path(tmp) / src_path.name
        if src_path.is_dir():
            shutil.copytree(src_path, staging)
        else:
            shutil.copy2(src_path, staging)
        shutil.make_archive(str(output_zip.with_suffix("")), "zip", root_dir=Path(tmp), base_dir=src_path.name)

    return output_zip


def _build_windows_installer(work_dir: Path, app_dir: Path, output_dir: Path, version: str) -> Path:
    iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
    if not iscc:
        raise RuntimeError("Inno Setup compiler (ISCC) not found. Install Inno Setup to build installer.")

    template = PROJECT_ROOT / "installer" / "windows" / "OmniMind.iss"
    if not template.exists():
        raise RuntimeError(f"Installer script not found: {template}")

    generated = work_dir / "OmniMind.generated.iss"
    content = template.read_text(encoding="utf-8")
    content = content.replace("{{APP_VERSION}}", version)
    content = content.replace("{{APP_SOURCE_DIR}}", str(app_dir).replace("\\", "\\\\"))
    content = content.replace("{{OUTPUT_DIR}}", str(output_dir).replace("\\", "\\\\"))
    generated.write_text(content, encoding="utf-8")

    _run([iscc, str(generated)], cwd=work_dir)

    installer = output_dir / f"OmniMind-Setup-{version}.exe"
    if not installer.exists():
        raise RuntimeError(f"Installer output not found: {installer}")
    return installer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build hardened OmniMind release artifacts")
    parser.add_argument("--target", choices=["windows", "macos"], required=True)
    parser.add_argument("--obfuscate", choices=["none", "pyarmor"], default="none")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--version", default="dev")
    parser.add_argument(
        "--package",
        choices=["zip", "installer", "both"],
        default="zip",
        help="installer only applies to windows",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="omnimind-hardened-") as tmp:
        work_dir = Path(tmp)
        _copy_project_to(work_dir)

        if args.obfuscate == "pyarmor":
            print("[info] Obfuscating source with PyArmor")
            _obfuscate_src_pyarmor(work_dir)
        else:
            print("[info] Building without obfuscation")

        app_output = _build_pyinstaller(work_dir, args.target)

        produced: list[Path] = []

        if args.package in {"zip", "both"}:
            zip_name = output_dir / f"OmniMind-{args.target}-{args.version}.zip"
            produced.append(_zip_artifact(app_output, zip_name))

        if args.package in {"installer", "both"}:
            if args.target != "windows":
                raise RuntimeError("Installer packaging is currently supported only for windows target")
            produced.append(_build_windows_installer(work_dir, app_output, output_dir, args.version))

    print("[done] Produced artifacts:")
    for item in produced:
        print(f" - {item}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"[error] Command failed with exit code {e.returncode}")
        raise SystemExit(e.returncode)
    except Exception as e:
        print(f"[error] {e}")
        raise SystemExit(1)
