# Copy HostStudio to s3://rf-render-788655295054-aps1/ue-linux/project/HostStudio/ and the Fab plugin to ue-linux/plugins/Fab/,
# then write a manifest (relative path, size) of exactly what was sent. Run as SYSTEM over SSM.
$ErrorActionPreference = 'Stop'
$b = 'rf-render-788655295054-aps1'; $r = 'ap-south-1'; $p = 'C:\UEProjects\HostStudio'; $pre = 'ue-linux/project/HostStudio'
$t0 = Get-Date
# kept: the .uproject, Config, Content, and from Saved only Config (minus crash-reporter folders) and Import (pipeline inputs)
$files = @(Get-Item "$p\HostStudio.uproject") + @(Get-ChildItem "$p\Config","$p\Content","$p\Saved\Import" -Recurse -File -Force) +
         @(Get-ChildItem "$p\Saved\Config" -Recurse -File -Force | Where-Object { $_.FullName -notlike '*\CrashReportClient\*' })
foreach ($d in 'Config','Content','Saved\Import') { Write-S3Object -BucketName $b -KeyPrefix "$pre/$($d.Replace('\', '/'))" -Folder "$p\$d" -Recurse -Region $r }
$man = foreach ($f in $files) { $rel = $f.FullName.Substring($p.Length + 1).Replace('\', '/')
  if ($rel -notmatch '^(Config|Content|Saved/Import)/') { Write-S3Object -BucketName $b -Key "$pre/$rel" -File $f.FullName -Region $r }
  "{0}`t{1}" -f $f.Length, $rel }
$man | Set-Content -Encoding ascii C:\fleet-manifest.tsv
Write-S3Object -BucketName $b -Key "ue-linux/project/HostStudio.manifest.tsv" -File C:\fleet-manifest.tsv -Region $r
"project: $($files.Count) files, $(($files | Measure-Object Length -Sum).Sum) bytes, $([int]((Get-Date) - $t0).TotalSeconds) s"
$e = 'C:\Program Files\Epic Games\UE_5.8\Engine\Plugins\Fab'
$ff = @(Get-ChildItem $e -Recurse -File -Force)
Write-S3Object -BucketName $b -KeyPrefix ue-linux/plugins/Fab -Folder $e -Recurse -Region $r
"fab: $($ff.Count) files, $(($ff | Measure-Object Length -Sum).Sum) bytes, total $([int]((Get-Date) - $t0).TotalSeconds) s"
