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
    throw "LibreHardwareMonitor.exe not found at $source"
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
$driver = Get-CimInstance Win32_SystemDriver -Filter "Name='PawnIO'" -ErrorAction SilentlyContinue
if (-not $driver -or $driver.State -ne 'Running') {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'PawnIO is missing and winget is unavailable. Install it from https://pawnio.eu and re-run this script.'
    }
    & winget install --id namazso.PawnIO --exact --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "winget could not install PawnIO (exit $LASTEXITCODE)" }
}
$driver = Get-CimInstance Win32_SystemDriver -Filter "Name='PawnIO'" -ErrorAction SilentlyContinue
if ($driver -and $driver.State -ne 'Running') { Start-Service PawnIO -ErrorAction SilentlyContinue }

$user = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $user) { $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name }

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
