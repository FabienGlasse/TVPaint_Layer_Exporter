$ErrorActionPreference = 'Stop'
$source = $PSScriptRoot
$workspace = Split-Path -Parent $source
$batFolder = Join-Path $workspace 'dist\TVPaint_CMD_Installer'
New-Item -ItemType Directory -Path $batFolder -Force | Out-Null
$packageFiles = @()
foreach ($name in @('Install.bat','setup_steps.py','Uninstall.bat','uninstall.py','component_cleanup.py','User Guide.html','Freelancer Guide.pdf')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination (Join-Path $batFolder $name) -Force
    $packageFiles += Join-Path $batFolder $name
}
foreach ($name in @('export_layers.py','export_options.py','exporter_ui.py','requirements.txt','TVPaint_Exporter_Logo.png','TVPaint_Exporter_Logo.ico')) {
    Copy-Item -LiteralPath (Join-Path $workspace "portable_exporter\$name") -Destination (Join-Path $batFolder $name) -Force
    $packageFiles += Join-Path $batFolder $name
}
Compress-Archive -LiteralPath $packageFiles -DestinationPath (Join-Path $workspace 'dist\TVPaint_CMD_Installer.zip') -Force
$compiler = $env:INNO_SETUP_COMPILER
if (-not $compiler) {
    $candidates = @(
        (Join-Path $source 'tools\InnoSetup\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )
    $compiler = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $compiler -or -not (Test-Path -LiteralPath $compiler)) { throw 'Install Inno Setup 6 or set INNO_SETUP_COMPILER to its ISCC.exe path.' }
& $compiler (Join-Path $source 'conventional.iss')
if ($LASTEXITCODE -ne 0) { throw 'Conventional installer compilation failed.' }
Compress-Archive -LiteralPath (Join-Path $workspace 'dist\conventional\TVPaintLayerExporterSetup.exe'),(Join-Path $source 'User Guide.html'),(Join-Path $source 'Freelancer Guide.pdf') -DestinationPath (Join-Path $workspace 'dist\TVPaint_Conventional_Installer.zip') -Force
