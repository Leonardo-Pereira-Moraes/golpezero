"""Ferramentas de detecção de golpes chamadas pelo agente.

Contratos (não alterar nomes/formatos sem atualizar o agente):
    analisar_link(url: str)  -> {"url": str, "suspeito": bool, "motivos": [str]}
    buscar_padroes(texto: str) -> {"encontrados": {categoria: [termos]}, "total": int}

Fonte de dados: padroes.json (marcas e encurtadores alimentam analisar_link;
as demais categorias alimentam buscar_padroes). Somente biblioteca padrão.
"""

import ipaddress
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

CAMINHO_PADROES = Path(__file__).with_name("padroes.json")

# Categorias do JSON usadas na análise de URL, não na busca em texto.
CATEGORIAS_DE_LINK = frozenset({"marcas", "encurtadores"})

# --------------------------------------------------------------------------- #
# Dados de referência que não pertencem ao padroes.json
# --------------------------------------------------------------------------- #

TLDS_INCOMUNS = frozenset({
    "xyz", "top", "click", "link", "online", "site", "club", "info", "live",
    "icu", "buzz", "monster", "rest", "cyou", "cfd", "sbs", "lol", "work",
    "loan", "win", "bid", "gq", "tk", "ml", "cf", "ga", "zip", "mov",
    "shop", "store", "support", "help", "vip", "fun", "space",
})

# Domínios oficiais por marca. Marca do JSON sem entrada aqui cai no padrão
# <marca>.com.br / <marca>.com.
DOMINIOS_OFICIAIS = {
    "itau":          {"itau.com.br", "itau.com"},
    "caixa":         {"caixa.gov.br"},
    "bancodobrasil": {"bb.com.br"},
    "bb":            {"bb.com.br"},
    "nubank":        {"nubank.com.br", "nu.com.br"},
    "inter":         {"bancointer.com.br", "inter.co"},
    "mercadopago":   {"mercadopago.com.br", "mercadopago.com"},
    "mercadolivre":  {"mercadolivre.com.br", "mercadolivre.com"},
    "serasa":        {"serasa.com.br", "serasaexperian.com.br"},
    "magalu":        {"magalu.com", "magazineluiza.com.br"},
    "whatsapp":      {"whatsapp.com", "wa.me"},
    "gov":           {"gov.br"},
    "receita":       {"gov.br"},
    "detran":        {"gov.br"},
}

# Marcas que só contam se forem um rótulo inteiro do host
# (evita falso positivo: "inter" em "internet"). Marcas com até 3 letras
# entram automaticamente.
MARCAS_SO_TOKEN = frozenset({"inter", "gov", "receita"})

# Sufixos de segundo nível comuns (para achar o domínio registrável sem PSL).
SUFIXOS_COMPOSTOS = frozenset({
    "com.br", "net.br", "org.br", "gov.br", "edu.br", "art.br", "app.br",
    "blog.br", "eco.br", "emp.br", "ind.br", "inf.br", "log.br", "tec.br",
    "co.uk", "com.ar", "com.mx", "com.pt",
})

# Troca de caracteres usada em typosquatting (1t4u -> itau).
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s"})


# --------------------------------------------------------------------------- #
# Carga do padroes.json
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=1)
def _padroes() -> dict:
    with open(CAMINHO_PADROES, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _encurtadores() -> frozenset:
    return frozenset(e.strip().lower() for e in _padroes().get("encurtadores", []))


@lru_cache(maxsize=1)
def _marcas() -> tuple:
    return tuple(_normalizar(m).replace(" ", "") for m in _padroes().get("marcas", []))


@lru_cache(maxsize=1)
def _regex_texto() -> dict:
    """Uma regex pré-compilada por termo, só das categorias de texto."""
    compilados = {}
    for categoria, termos in _padroes().items():
        if categoria in CATEGORIAS_DE_LINK:
            continue
        lista = []
        for termo in termos:
            corpo = r"\s+".join(re.escape(p) for p in _normalizar(termo).split())
            lista.append((termo, re.compile(rf"(?<!\w){corpo}(?!\w)")))
        compilados[categoria] = lista
    return compilados


# --------------------------------------------------------------------------- #
# Utilitários
# --------------------------------------------------------------------------- #

def _normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar 'Código' com 'codigo'."""
    decomposto = unicodedata.normalize("NFKD", texto.casefold())
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def _dominio_registravel(host: str) -> str:
    partes = host.split(".")
    if len(partes) >= 3 and ".".join(partes[-2:]) in SUFIXOS_COMPOSTOS:
        return ".".join(partes[-3:])
    return ".".join(partes[-2:])


def _eh_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # IP ofuscado em decimal/hex/octal (ex: http://3232235777, 0xC0A80001)
    return bool(re.fullmatch(r"(0x[0-9a-f]+|\d+)(\.(0x[0-9a-f]+|\d+)){0,3}", host))


def _host_e_oficial(host: str, marca: str) -> bool:
    dominios = DOMINIOS_OFICIAIS.get(marca, {f"{marca}.com.br", f"{marca}.com"})
    return any(host == d or host.endswith("." + d) for d in dominios)


def _marcas_imitadas(host: str) -> list:
    """Marcas citadas no host cujo domínio real não é o oficial."""
    sem_tld = host.rsplit(".", 1)[0] if "." in host else host
    tokens = set(re.split(r"[.\-_]", sem_tld))
    tokens |= {t.translate(_LEET) for t in tokens}
    compacto = re.sub(r"[.\-_]", "", sem_tld)
    compacto_leet = compacto.translate(_LEET)

    imitadas = []
    for marca in _marcas():
        if len(marca) <= 3 or marca in MARCAS_SO_TOKEN:
            citada = marca in tokens
        else:
            citada = marca in compacto or marca in compacto_leet
        if citada and not _host_e_oficial(host, marca):
            imitadas.append(marca)
    return imitadas


# --------------------------------------------------------------------------- #
# Ferramentas
# --------------------------------------------------------------------------- #

def analisar_link(url: str) -> dict:
    """Aplica heurísticas de phishing a uma URL."""
    original = url
    motivos = []
    url = (url or "").strip()

    if not re.match(r"^[a-z][a-z0-9+.\-]*://", url, re.I):
        url = "http://" + url  # usuário colou "itau-seguranca.com/login"

    try:
        partes = urlsplit(url)
        host = (partes.hostname or "").rstrip(".")
    except ValueError:
        host = ""

    if not host:
        return {"url": original, "suspeito": True,
                "motivos": ["URL inválida ou sem domínio identificável"]}

    if partes.username or "@" in partes.netloc:
        motivos.append("URL contém '@' antes do domínio (o destino real é o que vem depois do '@')")

    if _eh_ip(host):
        motivos.append(f"Usa endereço IP ({host}) no lugar de um domínio")
    else:
        if host.startswith("xn--") or ".xn--" in host:
            motivos.append("Domínio com caracteres especiais (punycode), possível imitação visual")

        registravel = _dominio_registravel(host)
        if host in _encurtadores() or registravel in _encurtadores():
            motivos.append(f"Link encurtado ({registravel}) esconde o destino real")

        tld = host.rsplit(".", 1)[-1]
        if tld in TLDS_INCOMUNS:
            motivos.append(f"Extensão de domínio incomum (.{tld}), muito usada em golpes")

        for marca in _marcas_imitadas(host):
            motivos.append(f"Domínio cita '{marca}' mas não é um endereço oficial da marca")

    return {"url": original, "suspeito": bool(motivos), "motivos": motivos}


def buscar_padroes(texto: str) -> dict:
    """Procura no texto os termos de padroes.json, por categoria."""
    normalizado = _normalizar(texto or "")
    encontrados = {}
    total = 0
    for categoria, termos in _regex_texto().items():
        achados = [termo for termo, regex in termos if regex.search(normalizado)]
        encontrados[categoria] = achados
        total += len(achados)
    return {"encontrados": encontrados, "total": total}


if __name__ == "__main__":
    for u in ["https://www.itau.com.br/login", "itau-seguranca.com", "http://bit.ly/abc",
              "http://192.168.0.10/pix", "nubank-premio.xyz", "https://internet.com.br"]:
        print(analisar_link(u))
    print(buscar_padroes("URGENTE: sua conta será bloqueada! Pague o boleto e me passa o código de verificação e seu CPF."))
