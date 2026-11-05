# Lines in the MetaHuman/RigLogic Build.cs files that pull in external or platform-specific code.
$e = 'C:\Program Files\Epic Games\UE_5.8\Engine'
Get-ChildItem "$e\Plugins\MetaHuman","$e\Plugins\Animation\RigLogic","$e\Plugins\Experimental\MetaHuman" -Recurse -Include *.Build.cs -ErrorAction SilentlyContinue |
  Select-String -Pattern 'ThirdParty|AdditionalLibraries|RuntimeDependencies|Platform ==|Win64|Linux|DelayLoad|\.dll|\.so|Precompiled|bUsePrecompiled' |
  ForEach-Object { "$($_.Path.Substring($e.Length + 1)):$($_.LineNumber): $($_.Line.Trim())" }
"== ThirdParty dirs under MetaHuman"; Get-ChildItem "$e\Plugins\MetaHuman" -Recurse -Directory -Filter ThirdParty -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Substring($e.Length + 1); Get-ChildItem $_.FullName -Recurse -Directory -Depth 2 | ForEach-Object { '  ' + $_.FullName.Substring($e.Length + 1) } }
"== Source dirs MetaHumanCoreTechLib"; Get-ChildItem "$e\Plugins\MetaHuman\MetaHumanCoreTechLib\Source\MetaHumanCoreTechLib" -Directory -Recurse -Depth 2 | ForEach-Object { $_.FullName.Substring($e.Length + 1) } | Select-Object -First 40
