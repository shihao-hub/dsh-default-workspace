param([string]$OutFile, [int]$Seconds = 8)
$ErrorActionPreference = 'SilentlyContinue'
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$seen = @{}
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
  $ts = [Math]::Round($sw.Elapsed.TotalMilliseconds)
  $procs = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 }
  foreach ($p in $procs) {
    $key = "$($p.Id)"
    if (-not $seen.ContainsKey($key)) {
      $seen[$key] = $true
      $title = ''
      try { $title = $p.MainWindowTitle } catch { }
      $path = ''
      try { $path = $p.Path } catch { }
      Add-Content -LiteralPath $OutFile -Value "NEW ${ts}ms pid=$($p.Id) name=$($p.ProcessName) title=[$title] path=[$path]"
    }
  }
  Start-Sleep -Milliseconds 60
}
Add-Content -LiteralPath $OutFile -Value 'POLLER DONE'
