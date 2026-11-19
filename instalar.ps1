# Instalador do Onda: prepara Python, ffmpeg e yt-dlp, copia o app
# para %LOCALAPPDATA%\Onda e cria atalhos na Área de Trabalho e no menu Iniciar.
param(
    [string]$Destino = (Join-Path $env:LOCALAPPDATA 'Onda'),
    [switch]$SemAtalhos,
    [switch]$NaoAbrir
)

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Instalando o Onda'
$origem = $PSScriptRoot

function Passo($texto) { Write-Host "`n  $texto" -ForegroundColor Cyan }
function Ok($texto) { Write-Host "    $texto" -ForegroundColor Green }
function Falha($texto) {
    Write-Host "`n  $texto" -ForegroundColor Red
    Read-Host "`n  Aperte Enter para fechar"
    exit 1
}

function Atualizar-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User')
}

function Achar-Python {
    # o "python" da Microsoft Store é só um atalho que abre a loja: ignoramos
    $tentativas = @(@('py', '-3'), @('python'))
    foreach ($t in $tentativas) {
        if (-not (Get-Command $t[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $argumentos = @($t | Select-Object -Skip 1) + @('-c', 'import sys; print(sys.executable if sys.version_info >= (3, 10) else "")')
            $exe = (& $t[0] @argumentos 2>$null | Select-Object -Last 1)
            if ($exe -and (Test-Path $exe) -and ($exe -notlike '*WindowsApps*')) { return $exe }
        } catch { }
    }
    $instalados = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python3*\python.exe') -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($instalados) { return $instalados[0].FullName }
    return $null
}

function Tem-Winget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Falha ("O winget não está disponível neste Windows.`n  Instale o 'Instalador de Aplicativo' pela Microsoft Store e rode este instalador de novo.")
    }
}

Write-Host ''
Write-Host '  Onda: conversor do YouTube para MP3 ou WAV' -ForegroundColor White
Write-Host '  ------------------------------------------'

# 1. Python
Passo 'Procurando o Python...'
$python = Achar-Python
if (-not $python) {
    Tem-Winget
    Write-Host '    Não encontrei. Instalando o Python 3.13 (pode levar alguns minutos)...'
    winget install -e --id Python.Python.3.13 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Atualizar-Path
    $python = Achar-Python
    if (-not $python) { Falha 'Não consegui instalar o Python. Instale pelo site python.org e rode este instalador de novo.' }
}
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
Ok "Python pronto: $python"

# 2. ffmpeg
Passo 'Procurando o ffmpeg...'
$ffmpegWinget = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffmpeg.exe') -ErrorAction SilentlyContinue
if ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -or $ffmpegWinget) {
    Ok 'ffmpeg já instalado.'
} else {
    Tem-Winget
    Write-Host '    Não encontrei. Instalando o ffmpeg...'
    winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Atualizar-Path
    $ffmpegWinget = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\*FFmpeg*\*\bin\ffmpeg.exe') -ErrorAction SilentlyContinue
    if (-not ((Get-Command ffmpeg -ErrorAction SilentlyContinue) -or $ffmpegWinget)) {
        Falha 'Não consegui instalar o ffmpeg. Tente rodar no Terminal: winget install Gyan.FFmpeg'
    }
    Ok 'ffmpeg instalado.'
}

# 3. yt-dlp
Passo 'Instalando/atualizando o yt-dlp...'
& $python -m pip install -U --disable-pip-version-check --quiet yt-dlp
if ($LASTEXITCODE -ne 0) { Falha 'Não consegui instalar o yt-dlp. Confira sua conexão com a internet e tente de novo.' }
Ok 'yt-dlp pronto.'

# 4. Arquivos do app
Passo "Copiando o Onda para $Destino..."
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
foreach ($arquivo in 'conversor.py', 'interface.html', 'icone.ico') {
    $de = Join-Path $origem $arquivo
    if (-not (Test-Path $de)) { Falha "Arquivo $arquivo não encontrado. Extraia o ZIP inteiro antes de instalar." }
    Copy-Item $de $Destino -Force
}
Ok 'Arquivos copiados.'

# 5. Atalhos
$script = Join-Path $Destino 'conversor.py'
if (-not $SemAtalhos) {
    Passo 'Criando atalhos...'
    $shell = New-Object -ComObject WScript.Shell
    $locais = @(
        [Environment]::GetFolderPath('Desktop'),
        (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs')
    )
    foreach ($pasta in $locais) {
        $atalho = $shell.CreateShortcut((Join-Path $pasta 'Onda.lnk'))
        $atalho.TargetPath = $pythonw
        $atalho.Arguments = '"' + $script + '"'
        $atalho.WorkingDirectory = $Destino
        $atalho.IconLocation = (Join-Path $Destino 'icone.ico') + ',0'
        $atalho.Description = 'Converter vídeos do YouTube para MP3 ou WAV'
        $atalho.Save()
    }
    Ok 'Atalho "Onda" criado na Área de Trabalho e no menu Iniciar.'
}

Write-Host "`n  Tudo pronto!" -ForegroundColor Green
if (-not $NaoAbrir) {
    Write-Host '  Abrindo o Onda...'
    Start-Process $pythonw -ArgumentList ('"' + $script + '"') -WorkingDirectory $Destino
    Start-Sleep -Seconds 3
}
