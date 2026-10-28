$ErrorActionPreference='Stop'
$zip='C:\xiaoqian\setup\v33-dsh-napcat-candidate.zip'; $target='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social\node_modules\dsh-napcat-v33-candidate'
if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne '78FDF4BEEF7B73922A69F786E5ABAB327A540FA3A9E2990BD96EA9A0F7DCAF95') { throw 'candidate_digest_mismatch' }
if (Test-Path -LiteralPath $target) { throw 'candidate_directory_exists' }
Expand-Archive -LiteralPath $zip -DestinationPath $target
Write-Output 'candidate_extracted_separately_original_retained'
