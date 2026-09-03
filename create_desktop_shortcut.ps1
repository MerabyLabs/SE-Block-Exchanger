param(
    [string]$TargetFolder = $PSScriptRoot,
    [string]$TargetPath = "",
    [string]$ShortcutPath = ""
)

if (-not $TargetFolder) {
    $TargetFolder = (Get-Location).Path
}

if (-not $TargetPath) {
    $exe = Get-ChildItem -Path $TargetFolder -Filter "SE_Tactical_Command*.exe" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($exe) {
        $TargetPath = $exe.FullName
    }
    else {
        $Launcher = Join-Path $TargetFolder "launch.bat"
        if (-not (Test-Path $Launcher)) {
            $Launcher = Join-Path $TargetFolder "launch_gui.bat"
        }
        $TargetPath = $Launcher
    }
}

$WshShell = New-Object -ComObject WScript.Shell
if (-not (Test-Path -LiteralPath $TargetPath -PathType Leaf)) {
    throw "Shortcut target does not exist: $TargetPath"
}
$TargetPath = (Resolve-Path -LiteralPath $TargetPath).Path
$TargetFolder = (Resolve-Path -LiteralPath $TargetFolder).Path
if (-not $ShortcutPath) {
    $DesktopPath = [System.Environment]::GetFolderPath('Desktop')
    $ShortcutPath = Join-Path $DesktopPath "SE Tactical Command.lnk"
}

$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $TargetPath
$Shortcut.WorkingDirectory = $TargetFolder
if ([IO.Path]::GetExtension($TargetPath) -ieq ".exe") {
    $Shortcut.IconLocation = "$TargetPath,0"
}
else {
    $iconFile = Join-Path $TargetFolder "app_icon.ico"
    if (Test-Path $iconFile) {
        $Shortcut.IconLocation = "$iconFile,0"
    }
}
$Shortcut.Description = "Space Engineers Tactical Command - Blueprint Conversion, PB Doctor & Subgrid Manager"
$Shortcut.Save()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "   SE Tactical Command Desktop Shortcut Created!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Shortcut location: $ShortcutPath"
Write-Host "Target: $TargetPath"
Write-Host ""
