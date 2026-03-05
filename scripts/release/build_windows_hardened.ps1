param(
  [string]$Version = "dev",
  [ValidateSet("none", "pyarmor")]
  [string]$Obfuscate = "none",
  [ValidateSet("zip", "installer", "both")]
  [string]$Package = "both"
)

$ErrorActionPreference = "Stop"

Write-Host "[OmniMind] Hardened build started"
Write-Host "  Version  : $Version"
Write-Host "  Obfuscate: $Obfuscate"
Write-Host "  Package  : $Package"

python scripts/release/build_hardened.py `
  --target windows `
  --version $Version `
  --obfuscate $Obfuscate `
  --package $Package

Write-Host "[OmniMind] Hardened build completed"
