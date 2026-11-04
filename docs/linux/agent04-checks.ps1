# Follow-up checks for the engine report: RigLogicEditor dependants, Speech2Face module, NNE ONNX runtime on Linux.
$e = 'C:\Program Files\Epic Games\UE_5.8\Engine'
"== RigLogicEditor references"; Get-ChildItem "$e\Plugins" -Recurse -Include *.Build.cs,*.uplugin -ErrorAction SilentlyContinue | Select-String 'RigLogicEditor' | ForEach-Object { "$($_.Path.Substring($e.Length + 1)):$($_.LineNumber): $($_.Line.Trim())" }
"== MetaHuman.uplugin Speech2Face/AudioDriven"; Select-String -Path "$e\Plugins\MetaHuman\MetaHumanAnimator\MetaHuman.uplugin" -Pattern 'Speech2Face|AudioDriven' -Context 0,4 | ForEach-Object { $_.Line; $_.Context.PostContext }
"== Speech2Face Build.cs"; Get-Content "$e\Plugins\MetaHuman\MetaHumanAnimator\Source\MetaHumanSpeech2Face\MetaHumanSpeech2Face.Build.cs"
"== uplugins naming Speech2Face/AudioDriven"; Get-ChildItem "$e\Plugins" -Recurse -Filter *.uplugin | Select-String 'Speech2Face|AudioDriven' | ForEach-Object { "$($_.Path.Substring($e.Length + 1)):$($_.LineNumber): $($_.Line.Trim())" }
"== NNERuntimeORT"; $n = Get-ChildItem "$e\Plugins" -Recurse -Filter NNERuntimeORT.uplugin | Select-Object -First 1; $n.FullName; Get-Content $n.FullName -Raw
$d = $n.Directory.FullName; "ThirdParty dirs:"; Get-ChildItem $d -Recurse -Directory -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match 'Onnxruntime' } | ForEach-Object { $_.FullName.Substring($d.Length + 1) }
"Build.cs files with Linux:"; Get-ChildItem $d -Recurse -Filter *.Build.cs | Select-String 'Linux|Onnxruntime.*dll|\.so' | ForEach-Object { "$($_.Path.Substring($d.Length + 1)):$($_.LineNumber): $($_.Line.Trim())" }
