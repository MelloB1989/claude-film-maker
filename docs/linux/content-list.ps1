# Levels, speech assets and MetaHuman character assets in the project, plus the editor's default map.
$p = 'C:\UEProjects\HostStudio'
"== maps"; Get-ChildItem "$p\Content" -Recurse -Filter *.umap | ForEach-Object { '{0,10} {1}' -f $_.Length, $_.FullName.Substring($p.Length + 1) }
"== Speech"; Get-ChildItem "$p\Content\Speech" -Recurse -File | ForEach-Object { '{0,10} {1}' -f $_.Length, $_.FullName.Substring($p.Length + 1) }
"== Host (dirs + largest)"; Get-ChildItem "$p\Content\Host" -Directory | ForEach-Object { $_.Name }
Get-ChildItem "$p\Content\Host" -Recurse -File | Sort-Object Length -Descending | Select-Object -First 12 | ForEach-Object { '{0,10} {1}' -f $_.Length, $_.FullName.Substring($p.Length + 1) }
"== Saved\Import"; Get-ChildItem "$p\Saved\Import" -Directory | ForEach-Object Name; Get-ChildItem "$p\Saved\Import" -Recurse -Include *.wav | Select-Object -First 8 | ForEach-Object { '{0,10} {1}' -f $_.Length, $_.FullName.Substring($p.Length + 1) }
"== EditorStartupMap / last level"; Select-String -Path "$p\Saved\Config\WindowsEditor\EditorPerProjectUserSettings.ini" -Pattern 'LastOpened|EditorStartup|LevelEditor.*Map' | Select-Object -First 5 | ForEach-Object Line
