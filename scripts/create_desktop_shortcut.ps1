# Creates Desktop shortcut + app icon (run once or from start.bat)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Bat = Join-Path $Root "start.bat"
$Assets = Join-Path $Root "assets"
$Ico = Join-Path $Assets "finance.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Lnk = Join-Path $Desktop "Finance.lnk"

if (-not (Test-Path $Bat)) {
    Write-Error "start.bat not found: $Bat"
}

New-Item -ItemType Directory -Force -Path $Assets | Out-Null

if (-not (Test-Path $Ico)) {
    Add-Type -AssemblyName System.Drawing
    $size = 64
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::FromArgb(255, 245, 250, 247))
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 34, 139, 87))
    $g.FillEllipse($brush, 6, 6, $size - 12, $size - 12)
    $font = New-Object System.Drawing.Font("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
    $sf = New-Object System.Drawing.StringFormat
    $sf.Alignment = "Center"
    $sf.LineAlignment = "Center"
    $rect = New-Object System.Drawing.RectangleF(0, 0, $size, $size)
    $g.DrawString("F", $font, [System.Drawing.Brushes]::White, $rect, $sf)
    $g.Dispose()
    $hIcon = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($hIcon)
    $fs = [System.IO.File]::Create($Ico)
    $icon.Save($fs)
    $fs.Close()
    $icon.Dispose()
    $bmp.Dispose()
}

$Wsh = New-Object -ComObject WScript.Shell
$Sc = $Wsh.CreateShortcut($Lnk)
$Sc.TargetPath = $Bat
$Sc.WorkingDirectory = $Root
$Sc.WindowStyle = 1
$Sc.Description = "Finance tracker"
$Sc.IconLocation = "$Ico,0"
$Sc.Save()

Write-Host "Shortcut: $Lnk"
