# Minimal read-only ASAR extractor (Electron asar format: Pickle header + JSON dir tree).
# Used purely for research: extracts selected packages so they can be read with normal tools.
param(
  [Parameter(Mandatory = $true)][string]$Asar,
  [Parameter(Mandatory = $true)][string]$OutDir,
  [Parameter(Mandatory = $true)][string[]]$Match,   # wildcard patterns matched against archive-relative paths
  [switch]$ListOnly
)

$ErrorActionPreference = 'Stop'

$fs = [System.IO.File]::OpenRead($Asar)
try {
  $br = New-Object System.IO.BinaryReader($fs)
  $b8 = $br.ReadBytes(8)
  if ($b8.Length -ne 8) { throw "not an asar: too short" }
  $headerSize = [BitConverter]::ToUInt32($b8, 4)
  $hb = $br.ReadBytes([int]$headerSize)
  if ($hb.Length -ne $headerSize) { throw "truncated asar header" }
  $jsonLen = [BitConverter]::ToUInt32($hb, 4)
  $json = [System.Text.Encoding]::UTF8.GetString($hb, 8, [int]$jsonLen)
  $dataBase = 8 + $headerSize

  Write-Host ("asar header: {0} bytes JSON, data starts at {1}" -f $jsonLen, $dataBase)

  $tree = $json | ConvertFrom-Json -AsHashtable -Depth 200

  $found = New-Object System.Collections.Generic.List[object]
  $walk = $null
  $walk = {
    param($node, $prefix)
    if ($node.ContainsKey('files')) {
      foreach ($name in $node['files'].Keys) {
        $child = $node['files'][$name]
        $path = if ($prefix) { "$prefix/$name" } else { $name }
        if ($child.ContainsKey('files')) { & $walk $child $path }
        else { $found.Add([pscustomobject]@{ Path = $path; Size = [int64]$child['size']; Offset = [int64]$child['offset']; Unpacked = [bool]($child.ContainsKey('unpacked') -and $child['unpacked']) }) }
      }
    }
  }
  & $walk $tree ''

  Write-Host ("archive contains {0} files" -f $found.Count)

  $hits = $found | Where-Object { $p = $_.Path; ($Match | Where-Object { $p -like $_ }).Count -gt 0 }
  Write-Host ("matched {0} files" -f $hits.Count)

  if ($ListOnly) { $hits | Sort-Object Path | ForEach-Object { $_.Path }; return }

  $bytes = 0
  foreach ($h in $hits) {
    if ($h.Unpacked) { Write-Host ("skip (unpacked): {0}" -f $h.Path); continue }
    $dest = Join-Path $OutDir ($h.Path -replace '/', '\')
    $dir = Split-Path -Parent $dest
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $fs.Position = $dataBase + $h.Offset
    $buf = New-Object byte[] $h.Size
    $read = 0
    while ($read -lt $h.Size) {
      $n = $fs.Read($buf, $read, [int]($h.Size - $read))
      if ($n -le 0) { throw ("short read on {0}" -f $h.Path) }
      $read += $n
    }
    [System.IO.File]::WriteAllBytes($dest, $buf)
    $bytes += $h.Size
  }
  Write-Host ("extracted {0} files, {1:N1} KB -> {2}" -f $hits.Count, ($bytes / 1KB), $OutDir)
}
finally { $fs.Dispose() }
