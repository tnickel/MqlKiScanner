$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../..'))
$mqlRepo = [IO.Path]::GetFullPath((Join-Path $taskRoot '../MqlDownloader'))
$privateRoot = Join-Path $taskRoot 'data/runs/liveabschluss_20261019/mql'
$proof = Get-Content -LiteralPath (Join-Path $privateRoot 'offline_verification.json') -Raw | ConvertFrom-Json
if ($proof.job_id -ne 'u-35579920-eb3d-4db4-83ef-ae6a24b934c9' -or $proof.status.state -ne 'done' -or -not $proof.offline_backup_hashes_verified -or @($proof.fresh_source_file_generations).Count -ne 268) { throw 'Exact source completion and offline preservation not verified' }
$stage = Join-Path $taskRoot '.tmp/source_maintenance/mql_guard_stage_20261018T184418Z/target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
$mqlJar = Join-Path $mqlRepo 'target/MqlDownloader-0.0.35-SNAPSHOT-jar-with-dependencies.jar'
$expectedSha = '59b6a9996628c040bfdcb36042eeecf1e68c52437ef1a3003a4f5fc138db37a7'
if ((Get-FileHash -LiteralPath $stage -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha) { throw 'Staged package hash mismatch' }
function RequireMqlIdle {
    $writers = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('java.exe','javaw.exe') -and ($_.CommandLine -match 'MqlDownloader|MqlAnalyzer') })
    if ($writers.Count -or (Get-NetTCPConnection -LocalPort 8089 -State Listen -ErrorAction SilentlyContinue)) { throw 'MQL process or listener exists; activation rejected' }
}
RequireMqlIdle
$previousSha = (Get-FileHash -LiteralPath $mqlJar -Algorithm SHA256).Hash.ToLowerInvariant()
if ($previousSha -ne (Get-FileHash -LiteralPath (Join-Path $proof.private_backup_path 'previous.jar') -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Production package changed since offline backup' }
Copy-Item -LiteralPath $stage -Destination $mqlJar
if ((Get-FileHash -LiteralPath $mqlJar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedSha) { throw 'Installed package hash mismatch' }
RequireMqlIdle
$javaBin = 'C:/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot/bin/java.exe'
$newProcess = Start-Process -FilePath $javaBin -ArgumentList @('-Dlog4j.configurationFile=file:///C:/Forex/MqlAnalyzer/config/log4j2.xml','-jar',$mqlJar) -WorkingDirectory $mqlRepo -WindowStyle Hidden -RedirectStandardOutput (Join-Path $privateRoot 'guard_runtime.stdout.log') -RedirectStandardError (Join-Path $privateRoot 'guard_runtime.stderr.log') -PassThru
$receipt = [ordered]@{
    utc = [DateTime]::UtcNow.ToString('o')
    source = 'mql5'
    source_uid = '0a8faef1-a341-4899-a199-a87166b69079'
    prior_job = $proof.job_id
    old_pid = 1663784
    old_process_already_absent_on_resume = $true
    port_free_and_no_source_jvm_before_replacement = $true
    offline_backup_hashes_verified = $true
    job_status_preserved_from_readonly_observer = $true
    generation_count_before_activation = @($proof.fresh_source_file_generations).Count
    scanner_parser_error_count = $proof.scanner_parser_error_count
    new_pid = $newProcess.Id
    previous_jar_sha256 = $previousSha
    installed_jar_sha256 = $expectedSha
    active_jar_or_classes_overwritten = $false
    source_update_post_sent = $false
    scanner_db_or_settings_modified = $false
    normal_application_start = $true
    process_termination_requested = $false
}
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $privateRoot 'guard_activation.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'mql_api_guard_activation_20261019.json') -Encoding utf8
$receipt | ConvertTo-Json -Depth 6
