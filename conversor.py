"""Conversor YouTube -> MP3 / WAV.

Servidor local (só stdlib + yt-dlp) que serve a interface em interface.html
e abre numa janela própria do Edge, sem barra de navegador.
Uso: pythonw conversor.py     (ou: python conversor.py --sem-janela)
"""

import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PASTA_APP = Path(__file__).resolve().parent
PASTA_DADOS = Path(os.environ.get("APPDATA", Path.home())) / "ConversorYouTube"
PASTA_DADOS.mkdir(parents=True, exist_ok=True)
ARQ_CONFIG = PASTA_DADOS / "config.json"
ARQ_HISTORICO = PASTA_DADOS / "historico.json"
PASTA_PADRAO = Path.home() / "Music" / "Conversor YouTube"
PORTAS = range(8765, 8776)
SEM_JANELA = 0x08000000  # CREATE_NO_WINDOW

# pythonw não tem console: manda saídas para um log em vez de quebrar
if sys.stdout is None or sys.stderr is None:
    _log = open(PASTA_DADOS / "conversor.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

try:
    import yt_dlp
except ImportError:
    subprocess.run(
        [sys.executable.replace("pythonw", "python"), "-m", "pip", "install", "-U", "yt-dlp"],
        creationflags=SEM_JANELA,
    )
    import yt_dlp


# ---------- persistência ----------
def ler_json(caminho, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(caminho, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


config = ler_json(ARQ_CONFIG, {})
config.setdefault("pasta", str(PASTA_PADRAO))
historico = ler_json(ARQ_HISTORICO, [])

trava = threading.Lock()
estado = {"fase": "parado", "pct": 0, "titulo": "", "item": 0, "total": 0, "mensagem": "", "job": 0}
atividade = {"ultimo_ping": time.time(), "sair_em": None}


# ---------- utilidades ----------
def miniatura(info):
    if info.get("thumbnail"):
        return info["thumbnail"]
    thumbs = info.get("thumbnails") or []
    return thumbs[-1]["url"] if thumbs else ""


def mensagem_amigavel(erro):
    texto = re.sub(r"\x1b\[[0-9;]*m", "", str(erro)).replace("ERROR: ", "").strip()
    casos = [
        ("Private video", "Esse vídeo é privado."),
        ("Video unavailable", "Esse vídeo não está disponível."),
        ("confirm your age", "Esse vídeo tem restrição de idade e pede login no YouTube."),
        ("is not a valid URL", "Esse link não parece ser do YouTube."),
        ("Unsupported URL", "Esse link não parece ser do YouTube."),
        ("ffmpeg", "O ffmpeg não foi encontrado. Instale com: winget install Gyan.FFmpeg"),
        ("getaddrinfo", "Sem conexão com a internet."),
    ]
    for trecho, amigavel in casos:
        if trecho.lower() in texto.lower():
            return amigavel
    return "Não deu para converter: " + texto[:220]


def localizar_ffmpeg():
    # logo após instalar pelo winget o PATH antigo ainda não tem o ffmpeg
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    candidatos = [base / "Links" / "ffmpeg.exe", *base.glob("Packages/*FFmpeg*/**/bin/ffmpeg.exe")]
    return next((str(c) for c in candidatos if c.is_file()), None)


def ler_area_transferencia():
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    if not user32.OpenClipboard(None):
        return ""
    try:
        alca = user32.GetClipboardData(13)  # CF_UNICODETEXT
        if not alca:
            return ""
        ponteiro = kernel32.GlobalLock(alca)
        try:
            return ctypes.wstring_at(ponteiro).strip()
        finally:
            kernel32.GlobalUnlock(alca)
    finally:
        user32.CloseClipboard()


def escolher_pasta(inicial):
    codigo = (
        "import sys, tkinter as tk; from tkinter import filedialog;"
        "r = tk.Tk(); r.withdraw(); r.attributes('-topmost', True);"
        "print(filedialog.askdirectory(initialdir=sys.argv[1], title='Onde salvar os áudios'))"
    )
    exe = sys.executable.replace("pythonw.exe", "python.exe")
    saida = subprocess.run(
        [exe, "-c", codigo, inicial], capture_output=True, text=True, creationflags=SEM_JANELA
    )
    return saida.stdout.strip()


# ---------- yt-dlp ----------
def obter_info(url):
    consulta = parse_qs(urlparse(url).query)
    so_playlist = "list" in consulta and "v" not in consulta and "youtu.be" not in url
    opcoes = {"quiet": True, "no_warnings": True, "skip_download": True,
              "extract_flat": "in_playlist", "noplaylist": not so_playlist}
    with yt_dlp.YoutubeDL(opcoes) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        entradas = list(info.get("entries") or [])
        return {
            "tipo": "playlist",
            "id": info.get("id", ""),
            "titulo": info.get("title") or "Playlist",
            "canal": info.get("uploader") or info.get("channel") or "",
            "faixas": len(entradas),
            "duracao": sum((e.get("duration") or 0) for e in entradas),
            "thumb": miniatura(entradas[0]) if entradas else "",
        }
    return {
        "tipo": "video",
        "id": info.get("id", ""),
        "titulo": info.get("title", ""),
        "canal": info.get("uploader") or info.get("channel") or "",
        "duracao": info.get("duration") or 0,
        "thumb": miniatura(info),
        "tem_playlist": "list" in consulta,
    }


def atualizar(**campos):
    with trava:
        estado.update(campos)


def converter(url, formato, qualidade, playlist, job):
    pasta = Path(config["pasta"])
    pasta.mkdir(parents=True, exist_ok=True)
    atual = {}

    def progresso(d):
        info = d.get("info_dict") or {}
        atual.update(titulo=info.get("title", ""), thumb=miniatura(info))
        item = info.get("playlist_index") or 1
        total = info.get("n_entries") or 1
        if d["status"] == "downloading":
            tam = d.get("total_bytes") or d.get("total_bytes_estimate")
            pct = d.get("downloaded_bytes", 0) / tam * 100 if tam else 0
            atualizar(fase="baixando", pct=round(pct, 1), titulo=atual["titulo"], item=item, total=total)
        elif d["status"] == "finished":
            atualizar(fase="convertendo", pct=100, titulo=atual["titulo"], item=item, total=total)

    def pronto(caminho):
        arquivo = Path(caminho)
        registro = {
            "titulo": atual.get("titulo") or arquivo.stem,
            "arquivo": str(arquivo),
            "formato": formato.upper(),
            "qualidade": f"{qualidade} kbps" if qualidade else "Sem perdas",
            "tamanho": arquivo.stat().st_size if arquivo.exists() else 0,
            "thumb": atual.get("thumb", ""),
            "quando": time.time(),
        }
        with trava:
            historico.insert(0, registro)
            del historico[60:]
            gravar_json(ARQ_HISTORICO, historico)

    extrair = {"key": "FFmpegExtractAudio", "preferredcodec": formato}
    if qualidade:
        extrair["preferredquality"] = qualidade
    opcoes = {
        "format": "bestaudio/best",
        "outtmpl": str(pasta / "%(title)s.%(ext)s"),
        "noplaylist": not playlist,
        "postprocessors": [extrair, {"key": "FFmpegMetadata"}],
        "progress_hooks": [progresso],
        "post_hooks": [pronto],
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "windowsfilenames": True,
    }
    if localizar_ffmpeg():
        opcoes["ffmpeg_location"] = localizar_ffmpeg()
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([url])
        atualizar(fase="concluido", pct=100, mensagem=str(pasta), job=job)
    except Exception as erro:  # yt-dlp levanta vários tipos diferentes
        atualizar(fase="erro", mensagem=mensagem_amigavel(erro), job=job)


# ---------- servidor ----------
class Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def responder(self, dados, codigo=200, tipo="application/json; charset=utf-8"):
        corpo = dados if isinstance(dados, bytes) else json.dumps(dados, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        atividade["ultimo_ping"] = time.time()
        rota = urlparse(self.path).path
        if rota == "/":
            html = (PASTA_APP / "interface.html").read_bytes()
            self.responder(html, tipo="text/html; charset=utf-8")
        elif rota == "/api/ping":
            self.responder({"app": "conversor-youtube"})
        elif rota == "/api/estado":
            with trava:
                self.responder({"estado": estado, "historico": historico, "pasta": config["pasta"],
                                "ffmpeg": bool(localizar_ffmpeg())})
        else:
            self.responder({"erro": "rota desconhecida"}, 404)

    def do_POST(self):
        atividade["ultimo_ping"] = time.time()
        rota = urlparse(self.path).path
        tamanho = int(self.headers.get("Content-Length") or 0)
        try:
            dados = json.loads(self.rfile.read(tamanho) or b"{}")
        except ValueError:
            dados = {}

        if rota == "/api/info":
            try:
                self.responder(obter_info(dados["url"]))
            except Exception as erro:
                self.responder({"erro": mensagem_amigavel(erro)}, 400)

        elif rota == "/api/converter":
            with trava:
                if estado["fase"] in ("baixando", "convertendo", "iniciando"):
                    return self.responder({"erro": "Já tem uma conversão em andamento."}, 409)
                job = estado["job"] + 1
                estado.update(fase="iniciando", pct=0, titulo="", item=0, total=0, mensagem="", job=job)
            formato = "wav" if dados.get("formato") == "wav" else "mp3"
            qualidade = None if formato == "wav" else str(dados.get("qualidade") or "320")
            threading.Thread(
                target=converter,
                args=(dados["url"], formato, qualidade, bool(dados.get("playlist")), job),
                daemon=True,
            ).start()
            self.responder({"job": job})

        elif rota == "/api/colar":
            self.responder({"texto": ler_area_transferencia()})

        elif rota == "/api/pasta":
            escolhida = escolher_pasta(config["pasta"])
            if escolhida:
                config["pasta"] = str(Path(escolhida))
                gravar_json(ARQ_CONFIG, config)
            self.responder({"pasta": config["pasta"]})

        elif rota == "/api/mostrar":
            alvo = Path(dados.get("arquivo") or config["pasta"])
            if alvo.is_file():
                subprocess.Popen(["explorer", "/select,", str(alvo)])
            else:
                Path(config["pasta"]).mkdir(parents=True, exist_ok=True)
                os.startfile(config["pasta"])
            self.responder({"ok": True})

        elif rota == "/api/abrir":
            alvo = Path(dados.get("arquivo", ""))
            if alvo.is_file():
                os.startfile(alvo)
            self.responder({"ok": alvo.is_file()})

        elif rota == "/api/sair":
            atividade["sair_em"] = time.time()
            self.responder({"ok": True})

        else:
            self.responder({"erro": "rota desconhecida"}, 404)


def ja_rodando(porta):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}/api/ping", timeout=1) as r:
            return json.load(r).get("app") == "conversor-youtube"
    except Exception:
        return False


def abrir_janela(url):
    candidatos = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    edge = next((c for c in candidatos if c.is_file()), None)
    if not edge:
        import webbrowser
        webbrowser.open(url)
        return
    subprocess.Popen([
        str(edge), f"--app={url}", f"--user-data-dir={PASTA_DADOS / 'janela'}",
        "--window-size=1060,660", "--no-first-run", "--no-default-browser-check",
        "--disable-features=Translate",
    ])


def vigia():
    # fecha o servidor quando a janela some (e nenhuma conversão está rodando)
    while True:
        time.sleep(2)
        agora = time.time()
        ocupado = estado["fase"] in ("iniciando", "baixando", "convertendo")
        saiu = atividade["sair_em"] and atividade["ultimo_ping"] <= atividade["sair_em"] + 0.5 \
            and agora - atividade["sair_em"] > 4
        sumiu = agora - atividade["ultimo_ping"] > 150
        if not ocupado and (saiu or sumiu):
            os._exit(0)


def principal():
    sem_janela = "--sem-janela" in sys.argv
    for porta in PORTAS:
        if ja_rodando(porta):
            abrir_janela(f"http://127.0.0.1:{porta}/")
            return
        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", porta), Manipulador)
            break
        except OSError:
            continue
    else:
        raise SystemExit("Nenhuma porta livre entre 8765 e 8775.")

    url = f"http://127.0.0.1:{porta}/"
    print("Conversor rodando em", url, flush=True)
    if not sem_janela:
        abrir_janela(url)
        threading.Thread(target=vigia, daemon=True).start()
    servidor.serve_forever()


if __name__ == "__main__":
    principal()
