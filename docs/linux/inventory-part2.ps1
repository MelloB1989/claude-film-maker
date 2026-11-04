# Inventory of the Windows UE workstation, run as SYSTEM over SSM (AWS-RunPowerShellScript).
# Prints JSON-ish sections; the engine install is found from the project's EngineAssociation.
$ErrorActionPreference = 'Continue'
$proj = 'C:\UEProjects\HostStudio'
function Size($p) { if (Test-Path $p) { $f = Get-ChildItem $p -Recurse -File -Force -ErrorAction SilentlyContinue
  '{0,-60} {1,10:N1} MB {2,8} files' -f $p, (($f | Measure-Object Length -Sum).Sum / 1MB), $f.Count } else { "$p (absent)" } }

& {
"== engine registration in user hives"
foreach ($u in Get-ChildItem C:\Users -Directory) { $h = "$($u.FullName)\NTUSER.DAT"; if (Test-Path $h) {
  reg load "HKU\inv_$($u.Name)" $h 2>$null | Out-Null
  $k = "Registry::HKEY_USERS\inv_$($u.Name)\Software\Epic Games\Unreal Engine\Builds"
  if (Test-Path $k) { "$($u.Name):"; (Get-ItemProperty $k | Format-List | Out-String) }
  [gc]::Collect(); reg unload "HKU\inv_$($u.Name)" 2>$null | Out-Null } }
Get-ChildItem 'Registry::HKEY_USERS' | ForEach-Object { $k = "$($_.PSPath)\Software\Epic Games\Unreal Engine\Builds"; if (Test-Path $k) { "$($_.Name):"; Get-ItemProperty $k | Format-List | Out-String } }
"== engine top"; Get-ChildItem 'C:\Program Files\Epic Games' -Force | ForEach-Object FullName
Get-ChildItem 'C:\Program Files\Epic Games\UE_5.8' -Force | ForEach-Object Name
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

} *> C:\fleet-inv2.txt
Write-S3Object -BucketName rf-render-788655295054-aps1 -Key ue-linux/inventory/inv2.txt -File C:\fleet-inv2.txt -Region ap-south-1
"uploaded $((Get-Item C:\fleet-inv2.txt).Length) bytes"
