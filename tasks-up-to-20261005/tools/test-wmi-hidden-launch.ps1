param(
  [Parameter(Mandatory = $true)][int]$MainPid,
  [switch]$NoRelaunch
)
$ErrorActionPreference = 'Stop'
$switches = ' -TreeKill'
if ($NoRelaunch) { $switches = ' -TreeKill -NoRelaunch' }
$cl = @'
powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\29580\AppData\Local\Temp\dsh-app-restart-helper.ps1" -ExePath "C:\Windows\System32\cmd.exe" -MainPid REPLACE_ME -HostPid 0 -DelayMs 400REPLACED_SWITCHES
'@
$cl = $cl.Replace('REPLACE_ME', [string]$MainPid).Replace('REPLACED_SWITCHES', $switches)
$startup = ([WMIClass]"Win32_ProcessStartup").CreateInstance()
$startup.ShowWindow = 0
$r = ([WMIClass]"Win32_Process").Create($cl, $null, $startup)
[Console]::Out.Write([string]$r.ReturnValue + ' ' + [string]$r.ProcessId)
