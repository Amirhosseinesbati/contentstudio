param([Parameter(Mandatory = $true)][string]$PreviousWebRoot)
$ErrorActionPreference = 'Stop'
# A copied/renamed pnpm checkout can retain absolute Windows junction targets.
# Repair existing local dependencies without downloading or changing the lockfile.
$taskWebRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../apps/web'))
$taskNodeRoot = Join-Path $taskWebRoot 'node_modules'
$taskPrevious = [IO.Path]::GetFullPath($PreviousWebRoot).TrimEnd('\')
$taskRepairs = @()
foreach ($taskLink in Get-ChildItem -LiteralPath $taskNodeRoot -Recurse -Attributes ReparsePoint) {
    $taskTarget = [string]$taskLink.LinkTarget
    if (!$taskTarget.StartsWith($taskPrevious + '\', [StringComparison]::OrdinalIgnoreCase)) { continue }
    $taskReplacement = [IO.Path]::GetFullPath($taskWebRoot + $taskTarget.Substring($taskPrevious.Length))
    $taskLinkPath = [IO.Path]::GetFullPath($taskLink.FullName)
    if (!$taskReplacement.StartsWith($taskNodeRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
        !$taskLinkPath.StartsWith($taskNodeRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Repair target escaped the project dependency directory'
    }
    if (!(Test-Path -LiteralPath $taskReplacement -PathType Container)) { throw "Local package missing: $taskReplacement" }
    if ($taskLink.LinkType -ne 'Junction') { throw "Expected junction: $taskLinkPath" }
    $taskRepairs += @{ Path = $taskLinkPath; Target = $taskReplacement }
}
foreach ($taskRepair in $taskRepairs) {
    Remove-Item -LiteralPath $taskRepair.Path -Force
    New-Item -ItemType Junction -Path $taskRepair.Path -Value $taskRepair.Target | Out-Null
}
Write-Output "Repaired $($taskRepairs.Count) existing junctions inside $taskNodeRoot"
