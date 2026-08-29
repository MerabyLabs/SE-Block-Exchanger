param(
    [string]$TargetFolder = $PSScriptRoot
)

if (-not $TargetFolder) {
    $TargetFolder = (Get-Location).Path
}

$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath('Desktop')
$ShortcutPath = Join-Path $DesktopPath "SE Tactical Command.lnk"

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $TargetFolder "SE Tactical Command.bat"
$Shortcut.WorkingDirectory = $TargetFolder
$Shortcut.IconLocation = Join-Path $TargetFolder "app_icon.ico,0"
$Shortcut.Description = "Space Engineers Tactical Command - Blueprint Conversion, PB Doctor & Subgrid Manager"
$Shortcut.Save()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   SE Tactical Command Desktop Shortcut Created!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Shortcut location: $ShortcutPath"
Write-Host ""
