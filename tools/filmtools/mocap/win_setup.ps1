# The Windows mocap box, checked and readied for ue_solve.py (docs/MOCAP_PILOT.md). Runs as SYSTEM over SSM
# (docs/linux/runps.py) or in the box's desktop. Reads first, changes only with -Apply:
#   - the engine (Build.version), the GPU and driver, RAM
#   - the plugins on disk: MetaHuman Animator, Capture Manager, Live Link Hub, and the Fab plugin
#     "MetaHuman Animator Markerless Motion Capture" (found by its .uplugin, wherever the Fab install put it)
#   - the mocap project: C:\UEProjects\Mocap (a copy of nothing: a fresh content-only project file), with the
#     plugins enabled and DX12 the default RHI (the solve runs on DirectML; Epic: DX12 must be the default)
# Nothing here signs in, downloads from Fab or touches HostStudio.
param([switch]$Apply, [string]$Engine = "C:\Program Files\Epic Games\UE_5.8", [string]$Proj = "C:\UEProjects\Mocap")
$ErrorActionPreference = "Stop"

$bv = Get-Content "$Engine\Engine\Build\Build.version" -Raw | ConvertFrom-Json
"engine: $($bv.MajorVersion).$($bv.MinorVersion).$($bv.PatchVersion) CL $($bv.Changelist)"
Get-CimInstance Win32_VideoController | ForEach-Object { "gpu: $($_.Name) driver $($_.DriverVersion)" }
"ram GB: {0:N0}" -f ((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
"cores: $((Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum)"

# every .uplugin under the engine's and the project's Plugins whose name or friendly name says what we need
$roots = @("$Engine\Engine\Plugins", "$Proj\Plugins") | Where-Object { Test-Path $_ }
$want = "Markerless|CaptureManager|LiveLinkHub|MetaHumanAnimator|^MetaHuman$"
$found = @{}
foreach ($r in $roots) {
  Get-ChildItem $r -Recurse -Filter *.uplugin -ErrorAction SilentlyContinue | ForEach-Object {
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    $n = $_.BaseName
    if ($n -match $want -or "$($j.FriendlyName)" -match "Markerless|Capture Manager") {
      $found[$n] = $_.FullName
      "plugin: $n  [$($j.FriendlyName)]  v$($j.VersionName)  $($_.FullName)"
    }
  }
}
$markerless = $found.Keys | Where-Object { $_ -match "Markerless" -or (Get-Content $found[$_] -Raw) -match "Markerless" }
if (-not $markerless) {
  "MISSING: the Markerless Motion Capture plugin. It comes only from Fab with an Epic sign-in (the operator's step):"
  "  editor Window > Fab (or the Launcher's Fab Library) > 'MetaHuman Animator Markerless Motion Capture' > Install to Engine 5.8"
  "  then copy its folder to $Engine\Engine\Plugins\Marketplace\ if the install left it in a project."
}

if (-not $Apply) { "read only (-Apply to create/enable)"; return }

New-Item -ItemType Directory -Force "$Proj\Config", "C:\mocap\in", "C:\mocap\out" | Out-Null
$enable = @("MetaHuman", "PythonScriptPlugin", "EditorScriptingUtilities") + @($found.Keys | Where-Object { $_ -match "Markerless|CaptureManager|LiveLinkHub" })
$up = "$Proj\Mocap.uproject"
$doc = if (Test-Path $up) { Get-Content $up -Raw | ConvertFrom-Json } else {
  [pscustomobject]@{ FileVersion = 3; EngineAssociation = "5.8"; Category = ""; Description = "mocap pilot"; Plugins = @() } }
$have = @($doc.Plugins | ForEach-Object { $_.Name })
foreach ($p in ($enable | Select-Object -Unique)) {
  if ($have -notcontains $p) { $doc.Plugins += [pscustomobject]@{ Name = $p; Enabled = $true } }
}
$doc | ConvertTo-Json -Depth 5 | Set-Content $up -Encoding UTF8
$ini = "$Proj\Config\DefaultEngine.ini"
$rhi = "[/Script/WindowsTargetPlatform.WindowsTargetSettings]`r`nDefaultGraphicsRHI=DefaultGraphicsRHI_DX12`r`n"
if (-not (Test-Path $ini) -or -not (Select-String -Path $ini -Pattern "DefaultGraphicsRHI_DX12" -Quiet)) {
  Add-Content $ini $rhi
}
"project: $up  plugins: $(($doc.Plugins | ForEach-Object { $_.Name }) -join ', ')"
"note: the target skeleton (a MetaHuman body skeleton asset) must be in this project: migrate the stock MetaHuman's"
"      Common/Body folder, never a presenter's face assets (none are needed for a body solve)"
