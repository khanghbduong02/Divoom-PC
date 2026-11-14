# One-time, administrator-only setup: run LibreHardwareMonitor at logon with the
# privileges it needs for CPU sensors, then confirm the WMI namespace answers.
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'setup-sensors.log'
try { Start-Transcript -Path $log -Force | Out-Null } catch { }
$exe = Join-Path $PSScriptRoot 'LibreHardwareMonitor\LibreHardwareMonitor.exe'
if (-not (Test-Path $exe)) { throw "LibreHardwareMonitor.exe not found at $exe" }

$user = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $user) { $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name }

$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory (Split-Path $exe)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0

Register-ScheduledTask -TaskName 'LibreHardwareMonitor' `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description 'CPU/GPU sensor helper for Gate Theme Studio' -Force | Out-Null

Start-ScheduledTask -TaskName 'LibreHardwareMonitor'
Write-Output "task registered for $user; waiting for sensors..."

$found = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        $sensors = Get-CimInstance -Namespace 'root/LibreHardwareMonitor' -ClassName Sensor -ErrorAction Stop |
            Where-Object { $_.SensorType -eq 'Temperature' }
        if ($sensors) {
            $sensors | Select-Object -First 6 Name, Identifier, Value | Format-Table -AutoSize
            $found = $true
            break
        }
    } catch { }
}
if (-not $found) { throw 'LibreHardwareMonitor started but exposed no temperature sensors' }
try { Stop-Transcript | Out-Null } catch { }
