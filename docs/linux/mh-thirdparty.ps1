# Which prebuilt libraries do the engine's MetaHuman/RigLogic plugins carry, and for which platforms?
$e = 'C:\Program Files\Epic Games\UE_5.8\Engine'
Get-ChildItem "$e\Plugins\MetaHuman","$e\Plugins\Animation\RigLogic","$e\Plugins\Experimental\MetaHuman" -Recurse -File -Include *.lib,*.a,*.so,*.dll,*.dylib,*.Build.cs -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch '\\Binaries\\Win64\\UnrealEditor-' } | ForEach-Object { '{0,10} {1}' -f $_.Length, $_.FullName.Substring($e.Length + 1) }
"== Linux dirs"; Get-ChildItem "$e\Plugins\MetaHuman","$e\Plugins\Animation\RigLogic" -Recurse -Directory -Filter Linux* -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($e.Length + 1) }
"== MetaHumanRuntime"; Get-ChildItem "$e\Plugins\Experimental\MetaHuman\MetaHumanRuntime" -Recurse | ForEach-Object { $_.FullName.Substring($e.Length + 1) } | Select-Object -First 20
"== egstore"; Get-ChildItem 'C:\Program Files\Epic Games\UE_5.8\.egstore' -Force | ForEach-Object Name
"== Saved\Bridge"; Get-ChildItem C:\UEProjects\HostStudio\Saved\Bridge | Select-Object -First 8 | ForEach-Object Name
"== UEClick"; Get-Content C:\ue-setup\click.ps1 -TotalCount 15; Get-ChildItem C:\ue-setup | ForEach-Object Name
