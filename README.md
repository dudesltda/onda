# Onda

Conversor de áudio do YouTube para **MP3** ou **WAV**, com uma interface clara que roda no seu próprio computador.

![Tela do Onda](docs/tela.jpg)

Cole o link de um vídeo ou de uma playlist, escolha o formato e clique em converter. A forma de onda se enche enquanto o áudio é baixado e convertido, e o arquivo vai direto para a sua pasta de músicas.

## O que ele faz

- MP3 em 320, 192 ou 128 kbps, ou WAV sem perdas
- Mostra capa, título, canal e duração antes de converter
- Baixa playlists inteiras
- Grava título e artista nas tags do arquivo
- Guarda um histórico das faixas, com botões para tocar e abrir a pasta
- Abre numa janela própria, sem barra de navegador, e fecha sozinho quando você fecha a janela

## Instalação

Precisa de Windows 10 ou 11. Para o passo a passo com imagens, veja o **[guia Como instalar o Onda](https://claude.ai/artifact/UFR129RWcceJXzw8eM8ajM)**.

1. Baixe o **[Onda.zip](https://github.com/dudesltda/onda/releases/latest/download/Onda.zip)**.
2. Clique com o botão direito no arquivo baixado e escolha **Extrair Tudo**.
3. Abra a pasta extraída e dê dois cliques em **Instalar Onda**.

O instalador baixa o que faltar (Python, ffmpeg e yt-dlp), instala o Onda e cria o atalho **Onda** na Área de Trabalho e no menu Iniciar. Depois disso, a pasta extraída e o ZIP podem ser apagados.

Se o Windows mostrar um aviso de segurança ao abrir o instalador, clique em **Mais informações** e depois em **Executar assim mesmo**. O código do instalador está em [`instalar.ps1`](instalar.ps1).

### Instalação manual

Para quem prefere fazer na mão, é preciso ter [Python 3.10+](https://www.python.org/downloads/), [ffmpeg](https://ffmpeg.org/) e [yt-dlp](https://github.com/yt-dlp/yt-dlp):

```bash
git clone https://github.com/dudesltda/onda.git
cd onda
python -m pip install -U yt-dlp
winget install Gyan.FFmpeg
pythonw conversor.py
```

## Uso

Os áudios vão para `Músicas\Conversor YouTube` por padrão. Dá para trocar a pasta em **Alterar**. O histórico e as preferências ficam em `%APPDATA%\ConversorYouTube`.

Para atualizar o Onda, baixe o ZIP de novo e rode o **Instalar Onda** outra vez. O histórico e as preferências são mantidos.

Se algum vídeo parar de baixar, quase sempre o YouTube mudou algo. Atualizar o yt-dlp resolve:

```bash
python -m pip install -U yt-dlp
```

## Como funciona

`conversor.py` sobe um pequeno servidor local (só a biblioteca padrão do Python mais o yt-dlp) em `127.0.0.1:8765` e abre `interface.html` numa janela do Edge em modo aplicativo. O yt-dlp baixa a melhor faixa de áudio e o ffmpeg converte para o formato escolhido.

## Uso responsável

Use apenas com conteúdo que você tem direito de baixar: suas próprias músicas, obras em domínio público ou com licença Creative Commons. Baixar conteúdo protegido sem permissão pode violar direitos autorais e os Termos de Serviço do YouTube.

## Licença

[MIT](LICENSE)
