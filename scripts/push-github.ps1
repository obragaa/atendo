# push-github.ps1 - envia os commits locais para github.com/obragaa/atendo.
#
# Por que existe: esta maquina nao tem o gh CLI nem credencial salva no Git
# Credential Manager. O caminho que funciona e o device flow do GitHub, com
# escopo "repo workflow" (so "repo" e recusado por causa de
# .github/workflows/ci.yml). O token e lido de arquivo e apagado no fim -
# nunca passe token na linha de comando.
#
# Uso:  .\scripts\push-github.ps1
#       (o script mostra um codigo; digite-o em https://github.com/login/device)

$ErrorActionPreference = "Continue"
$CLIENT_ID = "178c6fc778ccc68e1d6a"   # client_id publico do GitHub CLI
$REPO = "https://github.com/obragaa/atendo.git"
$tokenPath = "$env:TEMP\gh-token.txt"

# O caminho do projeto tem acento; resolver por curinga evita corrupcao.
$pasta = (Resolve-Path "$env:USERPROFILE\Desktop\Portf*lio\atendo").Path
Set-Location $pasta

# 1) Pede o codigo de dispositivo.
$device = Invoke-RestMethod -Method Post -Uri "https://github.com/login/device/code" `
    -Headers @{ Accept = "application/json" } `
    -Body @{ client_id = $CLIENT_ID; scope = "repo workflow" }

Write-Host ""
Write-Host "  CODIGO: $($device.user_code)" -ForegroundColor Green
Write-Host "  Digite-o em https://github.com/login/device (vale 15 minutos)"
Write-Host ""
Start-Process "https://github.com/login/device"

# 2) Aguarda a autorizacao.
$prazo = (Get-Date).AddSeconds($device.expires_in - 10)
$token = $null
while ((Get-Date) -lt $prazo) {
    Start-Sleep -Seconds ([int]$device.interval + 1)
    try {
        $r = Invoke-RestMethod -Method Post -Uri "https://github.com/login/oauth/access_token" `
            -Headers @{ Accept = "application/json" } `
            -Body @{ client_id = $CLIENT_ID; device_code = $device.device_code
                     grant_type = "urn:ietf:params:oauth:grant-type:device_code" }
    } catch { continue }
    if ($r.access_token) { $token = $r.access_token; break }
    if ($r.error -eq "slow_down") { Start-Sleep -Seconds 5 }
    if ($r.error -and $r.error -ne "authorization_pending" -and $r.error -ne "slow_down") {
        Write-Host "ERRO: $($r.error)" -ForegroundColor Red
        exit 1
    }
}
if (-not $token) { Write-Host "Codigo expirou sem autorizacao." -ForegroundColor Red; exit 2 }
$token | Out-File $tokenPath -Encoding ascii -NoNewline

# 3) Push com autenticacao pontual (nada persistido em disco).
$remotes = @(git remote)
if ($remotes -notcontains "origin") { git remote add origin $REPO }
git branch -M main
$basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("x-access-token:$token"))
git -c credential.helper= -c http.extraheader="Authorization: Basic $basic" push -u origin main
$codigo = $LASTEXITCODE

Remove-Item $tokenPath -Force -ErrorAction SilentlyContinue

if ($codigo -eq 0) {
    Write-Host "PUSH OK -> https://github.com/obragaa/atendo" -ForegroundColor Green
} else {
    Write-Host "PUSH FALHOU (codigo $codigo)" -ForegroundColor Red
}
exit $codigo
