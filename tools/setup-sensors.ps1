# One-time, administrator-only setup for the CPU/GPU sensor helper.
# Installs LibreHardwareMonitor's signed PawnIO driver, switches on its local
# sensor server, and registers it to start (hidden) at every logon.
$ErrorActionPreference = 'Stop'

# The exe runs from a temporary bundle folder, which disappears on exit. Keep the
# helper in LocalAppData so the logon task has a stable executable to start.
$stateDir = Join-Path $env:LOCALAPPDATA 'GateThemeStudio'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$log = Join-Path $stateDir 'setup-sensors.log'
try { Start-Transcript -Path $log -Force | Out-Null } catch { }

$source = Join-Path $PSScriptRoot 'LibreHardwareMonitor'
$dir = Join-Path $stateDir 'LibreHardwareMonitor'
$exe = Join-Path $dir 'LibreHardwareMonitor.exe'
if (-not (Test-Path (Join-Path $source 'LibreHardwareMonitor.exe'))) {
    # A source checkout does not keep the ignored tools/LibreHardwareMonitor
    # folder, so fetch the same official release the exe bundles.
    $source = Join-Path $stateDir 'LibreHardwareMonitor-download'
    if (-not (Test-Path (Join-Path $source 'LibreHardwareMonitor.exe'))) {
        $zip = Join-Path $env:TEMP 'LibreHardwareMonitor.zip'
        Write-Output 'Downloading LibreHardwareMonitor…'
        Invoke-WebRequest -UseBasicParsing `
            -Uri 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest/download/LibreHardwareMonitor.zip' `
            -OutFile $zip
        New-Item -ItemType Directory -Force -Path $source | Out-Null
        Expand-Archive -Path $zip -DestinationPath $source -Force
    }
    if (-not (Test-Path (Join-Path $source 'LibreHardwareMonitor.exe'))) {
        throw "LibreHardwareMonitor.exe could not be downloaded to $source"
    }
}

# Stop the old instance before replacing files it has open.
if (Get-ScheduledTask -TaskName 'LibreHardwareMonitor' -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName 'LibreHardwareMonitor' -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}
if ($source -ne $dir) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Copy-Item -Path (Join-Path $source '*') -Destination $dir -Recurse -Force
}
if (-not (Test-Path $exe)) { throw "LibreHardwareMonitor.exe not copied to $exe" }

# LibreHardwareMonitor 0.9.5+ publishes sensors only through its web server.
$config = @'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <appSettings>
    <add key="runWebServerMenuItem" value="true" />
    <add key="startMinMenuItem" value="true" />
    <add key="minTrayMenuItem" value="true" />
    <add key="minCloseMenuItem" value="true" />
  </appSettings>
</configuration>
'@
Set-Content -Path (Join-Path $dir 'LibreHardwareMonitor.config') -Value $config -Encoding UTF8

# PawnIO is the signed low-level driver LHM needs to read CPU registers.
# Prefer winget, then fall back to the official signed installer so a fresh PC
# does not need winget (or any manual download) to get CPU temperature.
function Get-PawnIODriver {
    return Get-Service -Name PawnIO -ErrorAction SilentlyContinue
}

$driver = Get-PawnIODriver
if (-not $driver -or $driver.Status -ne 'Running') {
    $installed = $false
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install --id namazso.PawnIO --exact `
            --accept-package-agreements --accept-source-agreements `
            --disable-interactivity --silent
        if ($LASTEXITCODE -eq 0) { $installed = $true }
    }
    if (-not $installed) {
        $pawn = Join-Path $env:TEMP 'PawnIO_setup.exe'
        Write-Output 'Downloading the PawnIO driver…'
        Invoke-WebRequest -UseBasicParsing `
            -Uri 'https://github.com/namazso/PawnIO.Setup/releases/latest/download/PawnIO_setup.exe' `
            -OutFile $pawn
        $signature = Get-AuthenticodeSignature -FilePath $pawn
        if (-not $signature -or $signature.Status -ne 'Valid' `
            -or $signature.SignerCertificate.Subject -notmatch 'namazso') {
            throw 'The downloaded PawnIO installer did not have a valid namazso signature.'
        }
        $proc = Start-Process -FilePath $pawn -ArgumentList '-install','-silent' `
            -Wait -PassThru
        if ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010) {
            throw "PawnIO installation failed (exit $($proc.ExitCode))."
        }
    }
}
$driver = Get-PawnIODriver
if ($driver -and $driver.Status -ne 'Running') {
    Start-Service PawnIO -ErrorAction SilentlyContinue
}

$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0

Register-ScheduledTask -TaskName 'LibreHardwareMonitor' `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description 'CPU/GPU sensor helper for Gate Theme Studio' -Force | Out-Null

Start-ScheduledTask -TaskName 'LibreHardwareMonitor'
Write-Output "task registered for $user; waiting for the sensor server..."

function Find-CpuTemperature($node) {
    if ($node.SensorId -match '^/(intelcpu|amdcpu)' -and
        $node.Type -eq 'Temperature' -and $node.Value) {
        return "$($node.Text) = $($node.Value)"
    }
    foreach ($child in $node.Children) {
        $hit = Find-CpuTemperature $child
        if ($hit) { return $hit }
    }
    return $null
}

$found = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 1
    try {
        $data = Invoke-RestMethod -Uri 'http://127.0.0.1:8085/data.json' -TimeoutSec 2
        $found = Find-CpuTemperature $data
        if ($found) { break }
    } catch { }
}
if (-not $found) { throw 'LibreHardwareMonitor is running but its sensor server reported no CPU temperature' }
Write-Output "CPU sensor: $found"
try { Stop-Transcript | Out-Null } catch { }
