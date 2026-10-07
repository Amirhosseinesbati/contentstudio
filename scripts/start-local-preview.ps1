param([int]$WebPort = 4319, [int]$ApiPort = 8319)
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskApi = Join-Path $taskRoot 'apps/api'
$taskWeb = Join-Path $taskRoot 'apps/web'
$taskPreview = Join-Path $taskRoot 'tmp/preview'
New-Item -ItemType Directory -Path $taskPreview -Force | Out-Null
foreach ($taskPort in @($WebPort, $ApiPort)) {
    $taskClient = [Net.Sockets.TcpClient]::new()
    try { $taskClient.Connect('127.0.0.1', $taskPort); throw "Port $taskPort already has a listener; reuse it or choose another port" }
    catch [Net.Sockets.SocketException] { }
    finally { $taskClient.Dispose() }
}
$taskDatabase = Join-Path $taskPreview 'contentstudio.db'
if (!(Test-Path -LiteralPath $taskDatabase)) {
    $taskExisting = Join-Path $taskApi 'contentstudio.db'
    if (Test-Path -LiteralPath $taskExisting) { Copy-Item -LiteralPath $taskExisting -Destination $taskDatabase }
}
# Process-scoped demo configuration. No real provider, n8n or connector call.
$env:PYTHONPATH = Join-Path $taskApi 'src'
$env:DATABASE_URL = 'sqlite:///' + $taskDatabase.Replace('\', '/')
$env:MODE = 'demo'
$env:DEMO_PASSWORD = 'DemoStudio!2026'
$env:FIXTURES_ROOT = Join-Path $taskRoot 'fixtures'
$env:MEDIA_ROOT = Join-Path $taskApi 'data/media'
$env:MODEL_PROVIDER = 'fixture'
$env:TRANSCRIPTION_PROVIDER = 'fixture'
$env:OPENAI_API_KEY = ''
$env:N8N_INTAKE_WEBHOOK = ''
$env:N8N_HEALTH_URL = ''
$env:N8N_API_KEY = ''
$env:WORDPRESS_BASE_URL = ''
$env:SERVICE_TOKEN = 'contentstudio-local-preview'
$taskPython = Join-Path $taskApi '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $taskDatabase) {
    # Reset only the copied demo login records; the original database is preserved.
    & $taskPython -c "from sqlalchemy import select; from contentstudio.db import session_factory; from contentstudio.models import User; from contentstudio.auth import hash_password; db=session_factory()(); users=db.scalars(select(User).where(User.email.in_(['admin@studio.test','editor@studio.test','viewer@studio.test','beta-admin@studio.test']))).all(); [setattr(user,'password_hash',hash_password('DemoStudio!2026')) for user in users]; db.commit(); db.close()"
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the isolated demo database snapshot' }
}
$env:CONTENTSTUDIO_FFMPEG = Join-Path $taskRoot 'tmp/ffmpeg-package/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
$env:TEMP = $taskPreview
$env:TMP = $taskPreview
$taskApiProcess = Start-Process -FilePath (Join-Path $taskApi '.venv/Scripts/python.exe') -ArgumentList @('-m', 'uvicorn', 'contentstudio.main:app', '--host', '127.0.0.1', '--port', $ApiPort) -WorkingDirectory $taskApi -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskPreview 'api.out.log') -RedirectStandardError (Join-Path $taskPreview 'api.err.log') -PassThru
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
$taskNode = (Get-Command node.exe).Source
$taskWebProcess = Start-Process -FilePath $taskNode -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', $WebPort, '--strictPort') -WorkingDirectory $taskWeb -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskPreview 'web.out.log') -RedirectStandardError (Join-Path $taskPreview 'web.err.log') -PassThru
@{ api_pid = $taskApiProcess.Id; web_pid = $taskWebProcess.Id; url = "http://127.0.0.1:$WebPort"; database = $taskDatabase } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskPreview 'processes.json')
Write-Output "Preview http://127.0.0.1:$WebPort (API $ApiPort). Demo database snapshot and process logs: $taskPreview"
