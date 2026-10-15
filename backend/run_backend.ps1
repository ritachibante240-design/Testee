param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8001
)

$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Ambiente Python não encontrado em '$python'. Crie o ambiente virtual e instale requirements.txt."
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    $projectPath = (Resolve-Path $PSScriptRoot).Path.TrimEnd("\")
    $isThisBackend = $false
    $hasActiveListener = $false

    foreach ($processId in ($listeners.OwningProcess | Sort-Object -Unique)) {
        if (-not (Get-Process -Id $processId -ErrorAction SilentlyContinue)) {
            Write-Host "Ignorando registro desatualizado da porta $Port (PID $processId não está em execução)."
            continue
        }

        $hasActiveListener = $true
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        $isProjectProcess = (
            $process.CommandLine -and
            $process.CommandLine.IndexOf($projectPath, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $process.CommandLine.Contains("app.main:app")
        )

        if ($isProjectProcess) {
            $isThisBackend = $true
            Write-Host "O backend deste projeto já está escutando na porta $Port (PID $processId)."
        }
        else {
            Write-Host "A porta $Port já está ocupada pelo processo PID $processId."
        }
    }

    if ($hasActiveListener) {
        if ($isThisBackend) {
            Write-Host "Para reiniciá-lo com h11, pressione Ctrl+C no terminal antigo e execute este script novamente."
        }
        else {
            Write-Host "Nenhum processo foi encerrado. Libere a porta ou escolha outra com: .\run_backend.ps1 -Port <porta>"
        }

        exit 1
    }
}

Set-Location $PSScriptRoot
& $python -m uvicorn app.main:app --host 0.0.0.0 --port $Port --http h11
exit $LASTEXITCODE
