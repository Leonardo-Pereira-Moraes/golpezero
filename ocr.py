"""Leitura de prints de conversa (WhatsApp/SMS) com Tesseract, 100% offline.

Uso no app:
    from ocr import ocr_disponivel, extrair_texto
    if ocr_disponivel():
        arquivo = st.file_uploader(...)
        texto = extrair_texto(arquivo.getvalue())

Teste pela linha de comando:
    python ocr.py prints/golpe1.png
"""

import io
import logging
import os
import re
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pytesseract
except ImportError:  # dependência opcional: sem ela o OCR só fica desligado
    pytesseract = None

log = logging.getLogger(__name__)

IDIOMA = "por"
FATOR_ESCALA = 2
LIMIAR_TEMA_ESCURO = 110  # brilho médio (0-255) abaixo disso = print em tema escuro

# O instalador da UB Mannheim não coloca o Tesseract no PATH por padrão.
CAMINHOS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
)

# Linhas inteiras que são interface do app, não conteúdo da conversa.
LINHAS_DE_INTERFACE = {
    "digite uma mensagem",
    "mensagem",
    "mensagem de texto",
    "texto",
    "hoje",
    "ontem",
}

_HORARIO = re.compile(r"\b([01]?\d|2[0-3])[:h][0-5]\d\b")  # 13:28, 13h28 (não "12.90")
_TIQUES = re.compile(r"[✓✔√]+")
_TEM_LETRA_OU_NUMERO = re.compile(r"[^\W_]")


# --------------------------------------------------------------------------- #
# Disponibilidade do Tesseract
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def ocr_disponivel() -> bool:
    """True se pytesseract, o executável do Tesseract e o idioma 'por' existem.

    O app usa isto para decidir se mostra o upload de imagem.
    """
    if pytesseract is None:
        return False

    executavel = shutil.which("tesseract") or next(
        (c for c in CAMINHOS_WINDOWS if os.path.isfile(c)), None
    )
    if not executavel:
        return False
    pytesseract.pytesseract.tesseract_cmd = executavel

    try:
        idiomas = pytesseract.get_languages(config="")
    except Exception as erro:  # executável quebrado, sem permissão etc.
        log.warning("Tesseract encontrado mas não respondeu: %s", erro)
        return False
    if IDIOMA not in idiomas:
        log.warning("Tesseract sem o idioma '%s'. Reinstale marcando Portuguese.", IDIOMA)
        return False
    return True


# --------------------------------------------------------------------------- #
# Pré-processamento
# --------------------------------------------------------------------------- #

def _abrir(imagem) -> Image.Image:
    """Aceita caminho (str/Path), bytes, arquivo aberto ou PIL.Image."""
    if isinstance(imagem, Image.Image):
        return imagem
    if isinstance(imagem, (bytes, bytearray, memoryview)):
        return Image.open(io.BytesIO(bytes(imagem)))
    if isinstance(imagem, (str, Path)):
        return Image.open(imagem)
    if hasattr(imagem, "read"):  # UploadedFile do Streamlit, arquivo aberto
        return Image.open(io.BytesIO(imagem.read()))
    raise TypeError(f"Tipo de imagem não suportado: {type(imagem).__name__}")


def _limiar_otsu(cinza: Image.Image) -> int:
    """Limiar que melhor separa dois grupos de tons (método de Otsu)."""
    histograma = cinza.histogram()
    total = sum(histograma)
    soma_total = sum(i * h for i, h in enumerate(histograma))

    soma_fundo = peso_fundo = 0
    melhor_limiar, melhor_variancia = 127, -1.0
    for tom, quantidade in enumerate(histograma):
        peso_fundo += quantidade
        if peso_fundo == 0:
            continue
        peso_frente = total - peso_fundo
        if peso_frente == 0:
            break
        soma_fundo += tom * quantidade
        media_fundo = soma_fundo / peso_fundo
        media_frente = (soma_total - soma_fundo) / peso_frente
        variancia = peso_fundo * peso_frente * (media_fundo - media_frente) ** 2
        if variancia > melhor_variancia:
            melhor_limiar, melhor_variancia = tom, variancia
    return melhor_limiar


def preprocessar(imagem: Image.Image) -> Image.Image:
    """Cinza -> (inverte se tema escuro) -> aumenta 2x -> preto e branco."""
    imagem = ImageOps.exif_transpose(imagem)  # foto de celular girada
    cinza = imagem.convert("L")

    brilho_medio = sum(i * h for i, h in enumerate(cinza.histogram())) / (cinza.width * cinza.height)
    if brilho_medio < LIMIAR_TEMA_ESCURO:
        cinza = ImageOps.invert(cinza)  # texto claro em fundo escuro -> texto escuro em fundo claro

    cinza = ImageOps.autocontrast(cinza, cutoff=1)
    cinza = cinza.resize((cinza.width * FATOR_ESCALA, cinza.height * FATOR_ESCALA),
                         Image.Resampling.LANCZOS)
    limiar = _limiar_otsu(cinza)
    return cinza.point(lambda p: 255 if p > limiar else 0, mode="1")


# --------------------------------------------------------------------------- #
# Limpeza do texto
# --------------------------------------------------------------------------- #

def limpar_texto(texto: str) -> str:
    """Remove horários, tiques de leitura, textos da interface e linhas vazias."""
    linhas = []
    for linha in texto.splitlines():
        linha = _HORARIO.sub("", linha)
        linha = _TIQUES.sub("", linha)
        linha = re.sub(r"\s+", " ", linha).strip(" |-–—·•")
        if not _TEM_LETRA_OU_NUMERO.search(linha):  # vazia ou só lixo de ícone
            continue
        if linha.casefold() in LINHAS_DE_INTERFACE:
            continue
        linhas.append(linha)
    return "\n".join(linhas)


# --------------------------------------------------------------------------- #
# Função pública
# --------------------------------------------------------------------------- #

def extrair_texto(imagem) -> str:
    """Extrai o texto de um print. Retorna "" se o OCR não estiver disponível
    ou se a imagem não puder ser lida — nunca levanta exceção para o app."""
    if not ocr_disponivel():
        return ""
    try:
        pronta = preprocessar(_abrir(imagem))
        bruto = pytesseract.image_to_string(pronta, lang=IDIOMA, config="--psm 4")
    except Exception as erro:
        log.warning("Falha no OCR: %s", erro)
        return ""
    return limpar_texto(bruto)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python ocr.py <caminho-do-print>")
        sys.exit(2)
    if not ocr_disponivel():
        print("Tesseract não encontrado (ou sem o idioma Portuguese). "
              "Instale pelo instalador da UB Mannheim: github.com/UB-Mannheim/tesseract/wiki")
        sys.exit(1)
    texto = extrair_texto(sys.argv[1])
    print(texto if texto else "(nenhum texto encontrado)")
