$ErrorActionPreference='Stop'
$profile='C:\xiaoqian\data\qq\dsh-home\profiles\qq-social'
$patch=Join-Path $profile 'cordis.patch.yml'
if (Test-Path -LiteralPath $patch) { throw 'profile_patch_exists' }
& icacls.exe $profile /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'profile_acl_failed' }
$files=@(Get-ChildItem 'C:\xiaoqian\app\napcat\config' -Filter 'onebot11_*.json' -File)
if ($files.Count -ne 1) { throw 'onebot_config_not_unique' }
$onebot=Get-Content -LiteralPath $files[0].FullName -Raw -Encoding UTF8 | ConvertFrom-Json
$token=$onebot.network.websocketServers[0].token
if ($token.Length -ne 64) { throw 'onebot_token_invalid' }
$persona=[IO.File]::ReadAllText('C:\xiaoqian\data\shared\persona-social.txt',[Text.Encoding]::UTF8)
if ([string]::IsNullOrWhiteSpace($persona) -or $persona.Length -gt 12000) { throw 'persona_invalid' }
$tokenJson=ConvertTo-Json -InputObject $token -Compress
$personaJson=ConvertTo-Json -InputObject $persona -Compress
$yaml=@'
- id: preset-standard
  disabled: true
- id: preset-minimal
  disabled: true
- id: preset-cordis
  disabled: true
- id: preset-ptc
  disabled: true
- id: agent-preset-registry
  config:
    default: xiaoqian-social
- id: tool-working-directory
  disabled: true
- id: session-telemetry-otel
  disabled: true
- id: message-feedback
  disabled: true
- id: ui-message-feedback
  disabled: true
- id: session-log-download
  disabled: true
- id: agent-default-model
  config:
    provider: deepseek-official
    model: deepseek-flash
- id: llm-deepseek
  config:
    baseURL: https://api.deepseek.com
    apiKeyEnv: XQ_DEEPSEEK_API_KEY
- id: dsh-napcat
  config:
    enabled: true
    mode: forward
    url: ws://127.0.0.1:3001
    accessToken: __ONEBOT_TOKEN_JSON__
    dmPolicy: allowlist
    allowFrom: []
    groupPolicy: allowlist
    groupAllowFrom: []
    triggerKeywords: ['小千']
    agentPreset: xiaoqian-social
    provider: deepseek-official
    model: deepseek-flash
    workspacePath: 'C:/xiaoqian/data/qq/workspace'
    memoryEnabled: false
    memoryAutoCapture: false
    imageCache: 'off'
    proactiveEnabled: true
    proactiveCooldownMinutes: 10
    proactiveMaxPerHour: 4
    proactiveQuietHours: '01:00-08:00'
    socialTimezone: Asia/Shanghai
- insert:
  - id: preset-xiaoqian-social
    name: '@deepseek-ai/dsh-agent-preset'
    config:
      id: xiaoqian-social
      order: 1
      plugins:
        - id: persona
          name: '@deepseek-ai/dsh-persona'
          config:
            prefix: __PERSONA_JSON__
            complete: true
            includeRuntimeContext: false
        - id: time-context
          name: '@deepseek-ai/dsh-time-context'
        - id: compaction
          name: cordis:group
          group: true
          isolate:
            compaction: true
          config:
            - id: compaction-basic
              name: '@deepseek-ai/dsh-compaction-basic'
            - id: command-compact
              name: '@deepseek-ai/dsh-command-compact'
'@
$yaml=$yaml.Replace('__ONEBOT_TOKEN_JSON__',$tokenJson).Replace('__PERSONA_JSON__',$personaJson)
[IO.File]::WriteAllText($patch,$yaml,(New-Object Text.UTF8Encoding($false)))
Write-Output 'qq_profile_patch_written_secrets_redacted'
