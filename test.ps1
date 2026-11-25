$extensions = '.json', '.yaml', '.yml', '.toml', '.log', '.md', '.txt'
$pattern = 'forecast_as_of|preseason_cutoff|snapshot_date|cutoff_date|2025-03-(1[0-9]|2[0-7])'
$report = Join-Path (Get-Location).Path '2025_forecast_cutoff_search.txt'

$matchesFound = @(
    Get-ChildItem -Path . -Recurse -File |
        Where-Object {
            $_.Extension -in $extensions -and
            $_.FullName -ne $report -and
            $_.FullName -notmatch '[\\/](\.venv|\.git|\.idea|__pycache__)[\\/]'
        } |
        Select-String -Pattern $pattern
)

@(
    "Matches found: $($matchesFound.Count)"
    ''
    $matchesFound | ForEach-Object {
        '{0}:{1}: {2}' -f $_.Path, $_.LineNumber, $_.Line.Trim()
    }
) | Set-Content -LiteralPath $report -Encoding UTF8

Write-Host "Saved $($matchesFound.Count) matches to: $report"