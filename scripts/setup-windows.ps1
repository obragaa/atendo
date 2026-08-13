# setup-windows.ps1 — instala WSL2 + Docker Desktop e sobe o Atendo completo.
#
# Como usar: clique com o botão direito neste arquivo > "Executar com o
# PowerShell" e aceite o aviso de administrador (UAC). Ou, num PowerShell
# aberto como administrador:
#     .\scripts\setup-windows.ps1
#
# Se o Windows pedir reinicialização (comum na primeira instalação do WSL),
# reinicie e rode este script de novo — ele continua de onde parou.

$ErrorActionPreference = "Continue"

# Reexecuta elevado, se preciso.
$identidade = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identidade.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`""
    exit
}

$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz
Write-Host ""
Write-Host "=== Atendo — setup do Windows ===" -ForegroundColor Green

# --- 1/4: WSL2 -------------------------------------------------------------
$wslOk = $false
try { wsl --status *> $null; $wslOk = ($LASTEXITCODE -eq 0) } catch { }
if (-not $wslOk) {
    Write-Host "[1/4] Instalando o WSL2 (pode pedir reinicialização ao final)..."
    wsl --install --no-distribution
} else {
    Write-Host "[1/4] WSL2 já presente."
}

# --- 2/4: Docker Desktop ---------------------------------------------------
$dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (-not (Test-Path $dockerExe)) {
    Write-Host "[2/4] Instalando o Docker Desktop (5–10 minutos)..."
    $cache = Get-ChildItem "$env:LOCALAPPDATA\Temp\WinGet" -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*Docker*" -and $_.Length -gt 100MB } |
        Select-Object -First 1
    if ($cache) {
        $instalador = $cache.FullName
        Write-Host "       (usando instalador já baixado)"
    } else {
        $instalador = "$env:TEMP\DockerDesktopInstaller.exe"
        Write-Host "       (baixando ~600 MB...)"
        Invoke-WebRequest "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" -OutFile $instalador
    }
    & $instalador install --quiet --accept-license --backend=wsl-2 | Out-Null
} else {
    Write-Host "[2/4] Docker Desktop já instalado."
}

if (-not (Test-Path $dockerExe)) {
    Write-Host "ERRO: a instalação não concluiu. Reinicie o computador e rode este script de novo." -ForegroundColor Red
    Read-Host "Enter para fechar"
    exit 1
}

# --- 3/4: engine no ar -----------------------------------------------------
Write-Host "[3/4] Iniciando o Docker (a primeira vez demora alguns minutos)..."
Start-Process $dockerExe
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$prazo = (Get-Date).AddMinutes(7)
$engineOk = $false
while ((Get-Date) -lt $prazo) {
    Start-Sleep -Seconds 5
    & $docker info *> $null
    if ($LASTEXITCODE -eq 0) { $engineOk = $true; break }
}
if (-not $engineOk) {
    Write-Host "AVISO: o engine não subiu ainda. Se o Windows pediu reinicialização (WSL)," -ForegroundColor Yellow
    Write-Host "reinicie o computador e rode este script de novo — ele continua daqui." -ForegroundColor Yellow
    Read-Host "Enter para fechar"
    exit 1
}

# --- 4/4: sobe o Atendo ----------------------------------------------------
Write-Host "[4/4] Subindo o Atendo (API + Postgres + Redis + Jaeger)..."
& $docker compose up -d --build
& $docker compose exec api python -m scripts.seed
Start-Process "http://localhost:8000"
Write-Host ""
Write-Host "Pronto!" -ForegroundColor Green
Write-Host "  Console do chat:  http://localhost:8000"
Write-Host "  API documentada:  http://localhost:8000/docs"
Write-Host "  Traces (Jaeger):  http://localhost:16686"
Write-Host ""
Write-Host "Para o chat responder com o modelo real, cole sua ANTHROPIC_API_KEY no arquivo .env"
Write-Host "e rode:  docker compose up -d"
Read-Host "Enter para fechar"
