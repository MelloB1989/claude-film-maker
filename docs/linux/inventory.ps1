# Inventory of the Windows UE workstation, run as SYSTEM over SSM (AWS-RunPowerShellScript).
# Prints JSON-ish sections; the engine install is found from the project's EngineAssociation.
$ErrorActionPreference = 'Continue'
$proj = 'C:\UEProjects\HostStudio'
function Size($p) { if (Test-Path $p) { $f = Get-ChildItem $p -Recurse -File -Force -ErrorAction SilentlyContinue
  '{0,-60} {1,10:N1} MB {2,8} files' -f $p, (($f | Measure-Object Length -Sum).Sum / 1MB), $f.Count } else { "$p (absent)" } }

"== uproject"; Get-ChildItem $proj -Filter *.uproject | ForEach-Object { $_.FullName; Get-Content $_.FullName -Raw }
"== engine installs (launcher manifest)"
$dat = 'C:\ProgramData\Epic\UnrealEngineLauncher\LauncherInstalled.dat'
if (Test-Path $dat) { Get-Content $dat -Raw } else { "no LauncherInstalled.dat" }
"== engine registry (source builds)"; Get-ItemProperty 'HKCU:\Software\Epic Games\Unreal Engine\Builds','HKLM:\SOFTWARE\EpicGames\Unreal Engine\*' -ErrorAction SilentlyContinue | Format-List | Out-String
Get-ChildItem 'Registry::HKEY_USERS\*\Software\Epic Games\Unreal Engine\Builds' -ErrorAction SilentlyContinue | ForEach-Object { $_.Name; Get-ItemProperty $_.PSPath | Format-List | Out-String }
$cands = @(Get-ChildItem 'C:\Program Files\Epic Games','D:\','C:\' -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path "$($_.FullName)\Engine\Build\Build.version" } | ForEach-Object FullName)
$cands += @(Get-ChildItem 'C:\Program Files\Epic Games' -Directory -ErrorAction SilentlyContinue | ForEach-Object FullName)
foreach ($e in ($cands | Sort-Object -Unique)) { if (Test-Path "$e\Engine\Build\Build.version") {
  "== engine at $e"; Get-Content "$e\Engine\Build\Build.version" -Raw
  "InstalledBuild.txt: $(Test-Path "$e\Engine\Build\InstalledBuild.txt")   SourceBuild marker (Engine\Source\Runtime): $(Test-Path "$e\Engine\Source\Runtime\Core")   .git: $(Test-Path "$e\.git")  Setup.bat: $(Test-Path "$e\Setup.bat")"
  "-- Marketplace/Fab plugins"
  foreach ($root in "$e\Engine\Plugins\Marketplace","$e\Engine\Plugins\Fab") { if (Test-Path $root) {
    Get-ChildItem $root -Recurse -Filter *.uplugin -ErrorAction SilentlyContinue | ForEach-Object {
      $d = $_.Directory.FullName; "### $($_.FullName)"; "Source/: $(Test-Path "$d\Source")  Binaries: $((Get-ChildItem "$d\Binaries" -Directory -ErrorAction SilentlyContinue).Name -join ',')"
      Get-Content $_.FullName -Raw; Size $d } } }
  "-- MetaHuman plugins anywhere under Engine\Plugins"
  Get-ChildItem "$e\Engine\Plugins" -Recurse -Filter *.uplugin -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'MetaHuman|RigLogic|LiveLink|MeshTracker|Hair|Groom' } | ForEach-Object {
    $d = $_.Directory.FullName; "### $($_.FullName)"; "Source/: $(Test-Path "$d\Source")  Binaries: $((Get-ChildItem "$d\Binaries" -Directory -ErrorAction SilentlyContinue).Name -join ',')"
    $j = Get-Content $_.FullName -Raw | ConvertFrom-Json
    "VersionName=$($j.VersionName) EngineVersion=$($j.EngineVersion) MarketplaceURL=$($j.MarketplaceURL) Installed=$($j.Installed) SupportedTargetPlatforms=$($j.SupportedTargetPlatforms -join ',')"
    foreach ($m in $j.Modules) { "  module $($m.Name) type=$($m.Type) PlatformAllowList=$($m.PlatformAllowList -join ',') PlatformDenyList=$($m.PlatformDenyList -join ',') TargetAllowList=$($m.TargetAllowList -join ',')" } }
  Size "$e\Engine\Plugins\Marketplace"
} }
"== project plugins"; if (Test-Path "$proj\Plugins") { Get-ChildItem "$proj\Plugins" -Recurse -Filter *.uplugin | ForEach-Object { "### $($_.FullName)  Source/: $(Test-Path "$($_.Directory.FullName)\Source")"; Get-Content $_.FullName -Raw } } else { "no Plugins folder" }
"== project Source"; if (Test-Path "$proj\Source") { Get-ChildItem "$proj\Source" -Recurse -File | ForEach-Object FullName } else { "no Source folder" }
"== Config files"; Get-ChildItem "$proj\Config" -Recurse -File | ForEach-Object { "### $($_.FullName) ($($_.Length) B)" }
foreach ($ini in 'DefaultEngine.ini','DefaultGame.ini','DefaultEditor.ini','Windows\WindowsEngine.ini','DefaultEditorPerProjectUserSettings.ini') { if (Test-Path "$proj\Config\$ini") { "##### $ini"; Get-Content "$proj\Config\$ini" -Raw } }
"== Saved\Config tree"; if (Test-Path "$proj\Saved\Config") { Get-ChildItem "$proj\Saved\Config" -Recurse -File | ForEach-Object { "$($_.FullName) $($_.Length)" } }
"== Saved top level"; Get-ChildItem "$proj\Saved" -Force -ErrorAction SilentlyContinue | ForEach-Object { Size $_.FullName }
"== sizes"; foreach ($s in 'Content','Config','Plugins','Source','Saved','Intermediate','DerivedDataCache','Binaries','Build') { Size "$proj\$s" }
Size $proj
"== Content top level"; Get-ChildItem "$proj\Content" -Directory | ForEach-Object { Size $_.FullName }
"== disks"; Get-PSDrive -PSProvider FileSystem | Format-Table Name,Used,Free -AutoSize | Out-String
"== AWS tools"; Get-Module -ListAvailable AWS.Tools.S3,AWSPowerShell* | Select-Object Name,Version | Format-Table | Out-String
"aws cli: $((Get-Command aws -ErrorAction SilentlyContinue).Source)"
"== C:\UEProjects"; Get-ChildItem 'C:\UEProjects' -Force | ForEach-Object { Size $_.FullName }
"== scheduled tasks (non-Microsoft)"; Get-ScheduledTask | Where-Object { $_.TaskPath -notlike '\Microsoft\*' } | ForEach-Object {
  "### $($_.TaskPath)$($_.TaskName) state=$($_.State)"; $_.Actions | ForEach-Object { "  exec: $($_.Execute) $($_.Arguments) (in $($_.WorkingDirectory))" }
  $_.Triggers | ForEach-Object { "  trigger: $($_.CimClass.CimClassName) user=$($_.UserId)" }; "  principal: $($_.Principal.UserId) $($_.Principal.LogonType) $($_.Principal.RunLevel)" }
"== GPU / OS"; (Get-CimInstance Win32_VideoController | ForEach-Object { "$($_.Name) driver $($_.DriverVersion)" }); (Get-CimInstance Win32_OperatingSystem).Caption
