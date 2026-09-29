param(
    [int]$Count = 3,
    [int]$Rate = 5,
    [string]$Python = 'python',
    [string]$Ffmpeg = 'ffmpeg'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $root 'fixtures\sources'
$wavRoot = Join-Path $root 'tmp\tts'
$ffmpegCommand = Get-Command $Ffmpeg -ErrorAction Stop
$ffmpegPath = $ffmpegCommand.Source
$pythonCommand = Get-Command $Python -ErrorAction Stop
$pythonPath = $pythonCommand.Source

Add-Type -AssemblyName System.Speech
$voices = @('Microsoft David Desktop', 'Microsoft Zira Desktop', 'Microsoft Mark')
$sources = @(Get-ChildItem -LiteralPath $sourceDir -Filter '*.json' | Sort-Object Name | Select-Object -First $Count)
if ($sources.Count -ne $Count) { throw "Expected $Count transcript fixtures" }

for ($sourceIndex = 0; $sourceIndex -lt $sources.Count; $sourceIndex++) {
    $sourceFile = $sources[$sourceIndex]
    $source = Get-Content -LiteralPath $sourceFile.FullName -Raw | ConvertFrom-Json
    $voice = $voices[$sourceIndex % $voices.Count]
    $wavDir = Join-Path $wavRoot $source.source_key
    New-Item -ItemType Directory -Path $wavDir -Force | Out-Null
    $speaker = [System.Speech.Synthesis.SpeechSynthesizer]::new()
    try {
        $speaker.SelectVoice($voice)
        $speaker.Rate = $Rate
        for ($index = 0; $index -lt $source.segments.Count; $index++) {
            $wavPath = Join-Path $wavDir ('segment-{0:D2}.wav' -f $index)
            $speaker.SetOutputToWaveFile($wavPath)
            $speaker.Speak([string]$source.segments[$index].text)
            $speaker.SetOutputToNull()
        }
    } finally {
        $speaker.Dispose()
    }
    & $pythonPath (Join-Path $PSScriptRoot 'assemble_demo_media.py') --source $sourceFile.FullName --wav-dir $wavDir --ffmpeg $ffmpegPath --voice $voice --rate $Rate
    if ($LASTEXITCODE -ne 0) { throw "Presentation assembly failed for $($source.source_key)" }
}
