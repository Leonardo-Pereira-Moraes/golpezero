"""
GolpeZero — agente que analisa mensagens suspeitas (WhatsApp/SMS/e-mail)
e diz se são golpe de engenharia social.

Fluxo do agente (analisar_stream):
  1. Pré-processamento: normaliza o texto e extrai URLs com regex.
  2. Loop de tool calling com o Ollama (no máximo MAX_PASSOS chamadas ao modelo).
  3. Garantia: executa automaticamente as ferramentas que o modelo não chamou.
  4. Síntese final em JSON estruturado (format=schema, temperature=0).

Tudo roda localmente com Ollama — 100% offline.
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Iterator

import ollama

# ---------------------------------------------------------------------------
# Ferramentas: usa ferramentas.py (do colega) e cai para o mock se não existir
# ---------------------------------------------------------------------------
try:
    from ferramentas import analisar_link, buscar_padroes

    FONTE_FERRAMENTAS = "ferramentas.py"
except ImportError as _erro_original:
    try:
        from ferramentas_mock import analisar_link, buscar_padroes

        FONTE_FERRAMENTAS = "ferramentas_mock.py"
    except ImportError:
        raise _erro_original

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
MODELO = "qwen2.5:3b"  # troque por "qwen2.5:1.5b" se o notebook estiver lento
KEEP_ALIVE = "30m"  # mantém o modelo carregado na memória durante o evento
MAX_PASSOS = 4  # máximo de chamadas ao modelo no loop de ferramentas
MAX_CARACTERES = 4000  # mensagens maiores são cortadas (protege a demo)

# Mesmas opções em TODAS as chamadas: mudar num_ctx força o Ollama a recarregar o modelo.
OPCOES = {"temperature": 0, "seed": 42, "num_ctx": 4096}
OPCOES_LOOP = {**OPCOES, "num_predict": 300}
OPCOES_SINTESE = {**OPCOES, "num_predict": 600}

_cliente = ollama.Client(timeout=180)

RISCOS = ("SEGURO", "SUSPEITO", "GOLPE")
FAIXAS = {"SEGURO": (0, 30), "SUSPEITO": (31, 69), "GOLPE": (70, 100)}

ORIENTACAO_PADRAO = {
    "SEGURO": "A mensagem não apresenta sinais claros de golpe. Mesmo assim, nunca "
    "compartilhe senhas ou códigos e, na dúvida, confirme pelo canal oficial.",
    "SUSPEITO": "Não clique em links nem envie dinheiro ou dados. Confirme a informação "
    "diretamente pelo app ou telefone oficial da empresa ou da pessoa.",
    "GOLPE": "Não responda, não clique em links e não faça pagamentos. Bloqueie o contato, "
    "denuncie como spam e, se já passou dados, avise seu banco imediatamente.",
}

# ---------------------------------------------------------------------------
# Prompt de sistema (papel, regras e 3 exemplos few-shot)
# ---------------------------------------------------------------------------
PROMPT_SISTEMA = """Você é o GolpeZero, analista especialista em golpes de engenharia social no Brasil \
(WhatsApp, SMS e e-mail). Sua tarefa é investigar uma mensagem recebida por um usuário e decidir se é golpe.

FERRAMENTAS
- buscar_padroes(texto): procura padrões típicos de golpe (urgência, Pix, pedido de dados, falsa autoridade, prêmio, falso parente).
- analisar_link(url): verifica se um link é suspeito (domínio falso, encurtador, imitação de marca).

REGRAS
1. Sempre chame buscar_padroes com o TEXTO COMPLETO da mensagem.
2. Chame analisar_link para CADA link da mensagem (um link por chamada). Não invente links.
3. Baseie-se apenas em evidências: o texto da mensagem e os resultados das ferramentas. Não acuse golpe sem evidência concreta.
4. Sinais fortes de golpe: pedido de Pix, transferência ou pagamento com pressa; pedido de senha, código, token ou dados de cartão; \
link que imita banco, órgão público ou loja; "troquei de número"; prêmio ou dinheiro fácil; ameaça de bloqueio ou multa com prazo curto.
5. Mensagens apenas informativas, sem pedido de dinheiro ou dados e sem links suspeitos, costumam ser legítimas.
6. Escala de risco: SEGURO (0 a 30), SUSPEITO (31 a 69), GOLPE (70 a 100).

EXEMPLOS

Exemplo 1 — falso banco com link
Mensagem: "ITAU: Seu cartao foi BLOQUEADO por suspeita de fraude. Regularize em ate 24h em itau-seguranca.com/desbloqueio"
Ações: buscar_padroes(texto=<mensagem completa>) -> urgência ("bloqueado", "24h") e autoridade ("Itaú"); \
analisar_link(url="itau-seguranca.com/desbloqueio") -> suspeito: domínio imita o banco e não é o oficial.
Veredito: {"risco": "GOLPE", "pontuacao": 95, "sinais_de_alerta": ["Ameaça de bloqueio com prazo de 24h", "Link falso imitando o Itaú"], \
"explicacao": "A mensagem usa medo e pressa para levar você a um site falso que imita o banco e rouba seus dados.", \
"orientacao": "Não clique no link. Abra o app oficial do banco ou ligue para o número no verso do cartão."}

Exemplo 2 — "oi mãe, troquei de número"
Mensagem: "Oi mãe, troquei de número, salva esse. Tô precisando de um Pix de R$ 850 pra pagar um boleto hoje, amanhã te devolvo"
Ações: buscar_padroes(texto=<mensagem completa>) -> falso parente ("troquei de número", "mãe"), dinheiro ("Pix", "R$"), urgência ("hoje"). Não há links.
Veredito: {"risco": "GOLPE", "pontuacao": 92, "sinais_de_alerta": ["Número novo de suposto parente", "Pedido de Pix urgente"], \
"explicacao": "É o golpe do falso parente: alguém finge ser seu filho com um número novo para pedir dinheiro com pressa.", \
"orientacao": "Não faça o Pix. Ligue para o número antigo do seu filho ou confirme por chamada de vídeo."}

Exemplo 3 — mensagem legítima de entrega
Mensagem: "Olá, Ana! Seu pedido #48213 foi enviado e deve chegar até sexta-feira. Você pode acompanhar a entrega pelo app da loja."
Ações: buscar_padroes(texto=<mensagem completa>) -> nenhum padrão relevante. Não há links.
Veredito: {"risco": "SEGURO", "pontuacao": 8, "sinais_de_alerta": [], \
"explicacao": "Mensagem apenas informativa: não pede dinheiro, senha nem dados e não contém links.", \
"orientacao": "Pode acompanhar o pedido pelo app oficial da loja normalmente."}
"""

FERRAMENTAS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "buscar_padroes",
            "description": "Procura na mensagem padrões típicos de golpe (urgência, Pix, pedido de dados, "
            "falsa autoridade, prêmio, falso parente). Use sempre com o texto completo da mensagem.",
            "parameters": {
                "type": "object",
                "properties": {"texto": {"type": "string", "description": "Texto completo da mensagem"}},
                "required": ["texto"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analisar_link",
            "description": "Verifica se um link (URL) é suspeito: domínio falso, encurtador, imitação de marca. "
            "Chame uma vez para cada link da mensagem.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "O link exatamente como aparece na mensagem"}},
                "required": ["url"],
            },
        },
    },
]

SCHEMA_VEREDITO = {
    "type": "object",
    "properties": {
        "risco": {"type": "string", "enum": list(RISCOS)},
        "pontuacao": {"type": "integer", "minimum": 0, "maximum": 100},
        "sinais_de_alerta": {"type": "array", "items": {"type": "string"}},
        "explicacao": {"type": "string"},
        "orientacao": {"type": "string"},
    },
    "required": ["risco", "pontuacao", "sinais_de_alerta", "explicacao", "orientacao"],
}

INSTRUCAO_SINTESE = """Agora dê o VEREDITO FINAL com base em todas as evidências acima \
(texto da mensagem e resultados das ferramentas). Responda SOMENTE com um JSON contendo:
- "risco": "SEGURO", "SUSPEITO" ou "GOLPE"
- "pontuacao": inteiro de 0 a 100 coerente com o risco (SEGURO 0-30, SUSPEITO 31-69, GOLPE 70-100)
- "sinais_de_alerta": lista de 2 a 5 frases curtas (3 a 8 palavras) que DESCREVEM cada sinal, \
por exemplo "Ameaça de cancelamento no mesmo dia" ou "Link falso imitando a Caixa" — nunca palavras soltas \
como "URGENTE" ou "R$". Lista vazia se for seguro.
- "explicacao": 1 a 3 frases simples, para uma pessoa leiga, explicando o porquê
- "orientacao": 1 a 2 frases dizendo o que a pessoa deve fazer agora
Escreva em português do Brasil."""

# ---------------------------------------------------------------------------
# Pré-processamento
# ---------------------------------------------------------------------------
_TLDS = (
    "com|br|net|org|gov|edu|io|ly|me|co|info|biz|xyz|top|site|online|app|link|click|shop|store|"
    "live|tk|ml|ga|cf|gq|ru|cn|cc|in|us|vip|club|icu|fun|pro|tech|page|digital|tv|ws|to|gl|gd|"
    "is|su|work|life|website|space|buzz|rest|bond|cfd|sbs|pw|net\\.br|com\\.br"
)
_URL_RE = re.compile(
    rf"""(?<![@\w.-])(?:
        https?://[^\s<>"'()]+                                   # com esquema: http(s)://...
      | (?:www\.)?(?:[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?\.)+ # sem esquema: dominio.tld/caminho
        (?:{_TLDS})\b(?::\d{{2,5}})?(?:/[^\s<>"'()]*)?
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_INVISIVEIS = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)


def normalizar_texto(texto: str) -> str:
    """Unicode NFKC, remove caracteres invisíveis e espaços extras (mantém quebras de linha)."""
    texto = unicodedata.normalize("NFKC", texto or "").translate(_INVISIVEIS)
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    linhas = [re.sub(r"[ \t ]+", " ", linha).strip() for linha in texto.split("\n")]
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    return texto[:MAX_CARACTERES]


def extrair_urls(texto: str) -> list[str]:
    """Extrai links com e sem http (ex.: bit.ly/x, itau-seguranca.com), sem repetição."""
    urls: list[str] = []
    for bruto in _URL_RE.findall(texto):
        url = bruto.rstrip(".,;:!?'\"")
        if url and _chave_url(url) not in {_chave_url(u) for u in urls}:
            urls.append(url)
    return urls


def _chave_url(url: str) -> str:
    """Forma canônica para comparar links: sem esquema, sem www, sem barra final."""
    chave = re.sub(r"^[a-z]+://", "", url.strip().lower())
    return re.sub(r"^www\.", "", chave).rstrip("/")


def _chave_texto(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").lower()).strip()


# ---------------------------------------------------------------------------
# Execução das ferramentas
# ---------------------------------------------------------------------------
def _executar_ferramenta(nome: str, args: dict, texto_mensagem: str) -> tuple[dict, dict]:
    """Executa uma ferramenta de forma robusta. Devolve (argumentos_usados, resultado)."""
    args = args if isinstance(args, dict) else {}
    try:
        if nome == "buscar_padroes":
            texto = args.get("texto")
            if not isinstance(texto, str) or not texto.strip():
                texto = texto_mensagem
            return {"texto": texto}, buscar_padroes(texto)
        if nome == "analisar_link":
            url = args.get("url") or next((v for v in args.values() if isinstance(v, str)), "")
            if not url.strip():
                return args, {"erro": "nenhuma URL informada"}
            return {"url": url.strip()}, analisar_link(url.strip())
        return args, {"erro": f"a ferramenta '{nome}' não existe"}
    except Exception as erro:  # ferramenta com bug não pode derrubar a demo
        return args, {"erro": f"falha ao executar {nome}: {erro}"}


def _chamadas_no_texto(conteudo: str) -> list[tuple[str, dict]]:
    """Modelos pequenos às vezes escrevem a chamada como JSON no texto em vez de usar tool_calls."""
    nomes = {f["function"]["name"] for f in FERRAMENTAS_SCHEMA}
    chamadas, decoder, i = [], json.JSONDecoder(), 0
    while (i := conteudo.find("{", i)) != -1:
        try:
            obj, fim = decoder.raw_decode(conteudo, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict) and obj.get("name") in nomes:
            argumentos = obj.get("arguments") or obj.get("parameters") or {}
            chamadas.append((obj["name"], argumentos if isinstance(argumentos, dict) else {}))
        i = fim
    return chamadas


def _cobertura(texto: str, urls: list[str], registro: list[dict]) -> tuple[bool, list[str]]:
    """Verifica se buscar_padroes rodou no texto completo e quais links ficaram sem análise."""
    alvo = _chave_texto(texto)
    buscou = any(
        r["nome"] == "buscar_padroes"
        and "erro" not in r["resultado"]
        and len(_chave_texto(r["argumentos"].get("texto", ""))) >= 0.8 * len(alvo)
        for r in registro
    )
    analisados = {_chave_url(r["argumentos"].get("url", "")) for r in registro if r["nome"] == "analisar_link"}
    faltando = [
        u for u in urls if not any(_chave_url(u) == a or _chave_url(u) in a or (a and a in _chave_url(u)) for a in analisados)
    ]
    return buscou, faltando


# ---------------------------------------------------------------------------
# Síntese e validação do veredito
# ---------------------------------------------------------------------------
def _validar_veredito(bruto: Any) -> dict:
    """Garante tipos, faixas e coerência entre risco e pontuação."""
    if not isinstance(bruto, dict):
        raise ValueError("veredito não é um objeto JSON")
    risco = str(bruto.get("risco", "")).strip().upper()
    try:
        pontuacao = int(round(float(bruto.get("pontuacao"))))
    except (TypeError, ValueError):
        pontuacao = None
    if risco not in RISCOS:
        if pontuacao is None:
            raise ValueError("veredito sem risco e sem pontuação")
        risco = "GOLPE" if pontuacao >= 70 else "SUSPEITO" if pontuacao > 30 else "SEGURO"
    minimo, maximo = FAIXAS[risco]
    pontuacao = min(max(pontuacao if pontuacao is not None else (minimo + maximo) // 2, minimo), maximo)

    sinais = bruto.get("sinais_de_alerta") or []
    if isinstance(sinais, str):
        sinais = [sinais]
    sinais = [str(s).strip() for s in sinais if str(s).strip()][:6]

    return {
        "risco": risco,
        "pontuacao": pontuacao,
        "sinais_de_alerta": sinais,
        "explicacao": str(bruto.get("explicacao") or "").strip() or "O agente não detalhou a explicação.",
        "orientacao": str(bruto.get("orientacao") or "").strip() or ORIENTACAO_PADRAO[risco],
    }


def _veredito_fallback(registro: list[dict], motivo: str) -> dict:
    """Usado quando o modelo falha: SUSPEITO, com os sinais que as ferramentas encontraram."""
    sinais = []
    for r in registro:
        res = r["resultado"]
        if r["nome"] == "analisar_link" and res.get("suspeito"):
            sinais.append(f"Link suspeito: {res.get('url') or r['argumentos'].get('url', '')}")
        elif r["nome"] == "buscar_padroes":
            for categoria, palavras in (res.get("encontrados") or {}).items():
                if palavras:
                    sinais.append(f"Padrão de {categoria}: {', '.join(map(str, palavras[:3]))}")
    return {
        "risco": "SUSPEITO",
        "pontuacao": 50,
        "sinais_de_alerta": sinais[:6],
        "explicacao": f"Não foi possível concluir a análise com o modelo ({motivo}). "
        "Por segurança, trate a mensagem com cautela.",
        "orientacao": ORIENTACAO_PADRAO["SUSPEITO"],
    }


def _chat(**kwargs):
    return _cliente.chat(model=MODELO, keep_alive=KEEP_ALIVE, **kwargs)


# ---------------------------------------------------------------------------
# Agente
# ---------------------------------------------------------------------------
def analisar_stream(mensagem: str) -> Iterator[dict]:
    """
    Analisa a mensagem e vai emitindo eventos do raciocínio, para a interface mostrar ao vivo:
      {"tipo": "etapa", "texto": str}
      {"tipo": "pensamento", "texto": str}               # texto livre que o modelo escreveu
      {"tipo": "ferramenta", "nome", "argumentos", "resultado", "automatica": bool}
      {"tipo": "final", "veredito": {...}, "tempo": float, "modelo", "ferramentas", "automaticas", "fallback"}
    """
    inicio = time.perf_counter()
    registro: list[dict] = []  # todas as ferramentas executadas

    def evento_ferramenta(nome, args, automatica):
        argumentos, resultado = _executar_ferramenta(nome, args, texto)
        if not isinstance(resultado, dict):
            resultado = {"resultado": resultado}
        item = {"nome": nome, "argumentos": argumentos, "resultado": resultado, "automatica": automatica}
        registro.append(item)
        return {"tipo": "ferramenta", **item}

    def evento_final(veredito, fallback=False):
        return {
            "tipo": "final",
            "veredito": veredito,
            "tempo": round(time.perf_counter() - inicio, 1),
            "modelo": MODELO,
            "ferramentas": len(registro),
            "automaticas": sum(r["automatica"] for r in registro),
            "fallback": fallback,
        }

    # 1) Pré-processamento -------------------------------------------------
    yield {"tipo": "etapa", "texto": "🧹 Normalizando o texto da mensagem..."}
    texto = normalizar_texto(mensagem)
    if not texto:
        yield evento_final(_veredito_fallback([], "mensagem vazia"), fallback=True)
        return

    yield {"tipo": "etapa", "texto": "🔎 Extraindo links..."}
    urls = extrair_urls(texto)
    yield {
        "tipo": "etapa",
        "texto": f"🔗 {len(urls)} link(s) encontrado(s): {', '.join(urls)}" if urls else "🔗 Nenhum link encontrado.",
    }

    mensagens: list[Any] = [
        {"role": "system", "content": PROMPT_SISTEMA},
        {
            "role": "user",
            "content": "Analise a mensagem abaixo usando as ferramentas.\n"
            f"Links extraídos automaticamente: {', '.join(urls) if urls else 'nenhum'}\n\n"
            f'MENSAGEM:\n"""\n{texto}\n"""',
        },
    ]

    # 2) Loop de tool calling ----------------------------------------------
    for passo in range(1, MAX_PASSOS + 1):
        yield {"tipo": "etapa", "texto": f"🤖 Passo {passo}: o agente está decidindo o que investigar..."}
        t0 = time.perf_counter()
        try:
            resposta = _chat(messages=mensagens, tools=FERRAMENTAS_SCHEMA, options=OPCOES_LOOP)
        except Exception as erro:
            yield {"tipo": "etapa", "texto": f"⚠️ Falha ao consultar o modelo: {erro}"}
            break
        msg = resposta.message
        conteudo = (msg.content or "").strip()

        chamadas = [(c.function.name, dict(c.function.arguments or {})) for c in (msg.tool_calls or [])]
        if chamadas:
            mensagens.append(msg)
        elif conteudo and (chamadas := _chamadas_no_texto(conteudo)):
            mensagens.append({"role": "assistant", "content": conteudo})
        elif conteudo:
            yield {"tipo": "pensamento", "texto": conteudo}

        if not chamadas:
            yield {"tipo": "etapa", "texto": f"💭 O agente encerrou a investigação ({time.perf_counter() - t0:.1f} s)."}
            break

        nomes = ", ".join(nome for nome, _ in chamadas)
        yield {"tipo": "etapa", "texto": f"🛠️ O agente decidiu chamar: {nomes} ({time.perf_counter() - t0:.1f} s)"}
        for nome, args in chamadas:
            evento = evento_ferramenta(nome, args, automatica=False)
            yield evento
            mensagens.append(
                {"role": "tool", "tool_name": nome, "content": json.dumps(evento["resultado"], ensure_ascii=False)}
            )

        buscou, faltando = _cobertura(texto, urls, registro)
        if buscou and not faltando:
            yield {"tipo": "etapa", "texto": "✅ Todas as evidências necessárias foram coletadas."}
            break

    # 3) Garantia: ferramentas que o modelo não chamou --------------------
    buscou, faltando = _cobertura(texto, urls, registro)
    extras = []
    if not buscou or faltando:
        yield {"tipo": "etapa", "texto": "🛡️ Garantia: executando automaticamente as verificações que faltaram..."}
    if not buscou:
        evento = evento_ferramenta("buscar_padroes", {"texto": texto}, automatica=True)
        extras.append(evento)
        yield evento
    for url in faltando:
        evento = evento_ferramenta("analisar_link", {"url": url}, automatica=True)
        extras.append(evento)
        yield evento

    # 4) Síntese final em JSON ---------------------------------------------
    yield {"tipo": "etapa", "texto": "🧾 Gerando o veredito final..."}
    instrucao = INSTRUCAO_SINTESE
    if extras:
        evidencias = "\n".join(
            f"- {e['nome']}({json.dumps(e['argumentos'], ensure_ascii=False)}) -> "
            f"{json.dumps(e['resultado'], ensure_ascii=False)}"
            for e in extras
        )
        instrucao = f"EVIDÊNCIAS EXTRAS (coletadas automaticamente pelo sistema):\n{evidencias}\n\n{instrucao}"
    mensagens.append({"role": "user", "content": instrucao})

    fallback = False
    t0 = time.perf_counter()
    try:
        resposta = _chat(messages=mensagens, format=SCHEMA_VEREDITO, options=OPCOES_SINTESE)
        veredito = _validar_veredito(json.loads(resposta.message.content))
        yield {"tipo": "etapa", "texto": f"📋 Veredito gerado ({time.perf_counter() - t0:.1f} s)."}
    except Exception as erro:
        fallback = True
        veredito = _veredito_fallback(registro, type(erro).__name__)
        yield {"tipo": "etapa", "texto": f"⚠️ Não consegui gerar o JSON do veredito ({erro}). Usando resposta de segurança."}

    # Regra de segurança: link apontado como suspeito nunca resulta em SEGURO
    links_suspeitos = [r for r in registro if r["nome"] == "analisar_link" and r["resultado"].get("suspeito")]
    if veredito["risco"] == "SEGURO" and links_suspeitos:
        url = links_suspeitos[0]["resultado"].get("url") or links_suspeitos[0]["argumentos"].get("url", "")
        veredito["risco"], veredito["pontuacao"] = "SUSPEITO", max(veredito["pontuacao"], 50)
        veredito["sinais_de_alerta"].insert(0, f"Link suspeito: {url}")
        veredito["orientacao"] = ORIENTACAO_PADRAO["SUSPEITO"]
        yield {"tipo": "etapa", "texto": "🛡️ Regra de segurança: há link suspeito, então o risco foi elevado para SUSPEITO."}

    yield evento_final(veredito, fallback)


def analisar(mensagem: str) -> dict:
    """Consome o gerador e devolve só o resultado final (evento 'final', sem a chave 'tipo')."""
    final: dict = {}
    for evento in analisar_stream(mensagem):
        if evento["tipo"] == "final":
            final = {k: v for k, v in evento.items() if k != "tipo"}
    return final


def aquecer_modelo() -> tuple[bool, str]:
    """
    Faz uma chamada curta para carregar o modelo na memória (e já deixar o prompt de sistema
    em cache no Ollama). Devolve (ok, mensagem) — nunca levanta exceção.
    """
    inicio = time.perf_counter()
    try:
        _chat(
            messages=[{"role": "system", "content": PROMPT_SISTEMA}, {"role": "user", "content": "ok"}],
            tools=FERRAMENTAS_SCHEMA,
            options={**OPCOES, "num_predict": 1},
        )
    except ollama.ResponseError as erro:
        if erro.status_code == 404:
            return False, f"O modelo {MODELO} não está instalado. Rode no terminal: ollama pull {MODELO}"
        return False, f"O Ollama respondeu com erro: {erro.error}"
    except Exception:
        return False, "Não consegui falar com o Ollama. Abra o aplicativo Ollama (ou rode `ollama serve`) e recarregue a página."
    return True, f"Modelo {MODELO} pronto em {time.perf_counter() - inicio:.1f} s"


# ---------------------------------------------------------------------------
# Exemplos (exemplos.txt) — usado pelo app e pelo avaliar.py
# ---------------------------------------------------------------------------
def carregar_exemplos(caminho: str | Path = "exemplos.txt") -> list[dict]:
    """
    Lê mensagens separadas por '---', cada uma começando com [GOLPE] ou [LEGITIMA].
    Devolve [{"rotulo": "GOLPE"|"LEGITIMA"|None, "texto": str}]. Arquivo ausente -> [].
    """
    arquivo = Path(caminho)
    if not arquivo.is_absolute() and not arquivo.exists():
        arquivo = Path(__file__).parent / arquivo
    conteudo = None
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            conteudo = arquivo.read_text(encoding=codificacao)
            break
        except UnicodeDecodeError:
            continue
        except OSError:
            return []
    if conteudo is None:
        return []

    exemplos = []
    for bloco in re.split(r"^\s*-{3,}\s*$", conteudo, flags=re.MULTILINE):
        bloco = bloco.strip()
        marcacao = re.match(r"^\[\s*(GOLPE|LEG[IÍ]TIMA)\s*\]\s*", bloco, re.IGNORECASE)
        rotulo = None
        if marcacao:
            rotulo = "GOLPE" if marcacao.group(1).upper() == "GOLPE" else "LEGITIMA"
            bloco = bloco[marcacao.end():].strip()
        if bloco:
            exemplos.append({"rotulo": rotulo, "texto": bloco})
    return exemplos


# ---------------------------------------------------------------------------
# Teste pelo terminal:  python agente.py            (3 mensagens de teste)
#                       python agente.py "mensagem"  (sua mensagem)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    testes = sys.argv[1:] or [
        "URGENTE Caixa: seu FGTS de R$ 1.890,00 sera cancelado hoje. Confirme seus dados em "
        "http://caixa-fgts-liberacao.xyz/saque e informe o codigo recebido por SMS.",
        "Filho? É a mamãe, perdi meu celular e esse é meu número novo. Consegue me mandar um Pix de "
        "R$ 600 agora? Depois te explico.",
        "Oi Leonardo, a reunião do grupo do workshop ficou para quinta às 14h na sala 204. "
        "Leva o notebook com o projeto. Abraço!",
    ]

    print(f"Ferramentas: {FONTE_FERRAMENTAS} | Modelo: {MODELO}")
    ok, status = aquecer_modelo()
    print(("✅ " if ok else "❌ ") + status)
    if not ok:
        sys.exit(1)

    for n, mensagem in enumerate(testes, 1):
        print("\n" + "=" * 78 + f"\nTESTE {n}: {mensagem}\n" + "=" * 78)
        for ev in analisar_stream(mensagem):
            if ev["tipo"] in ("etapa", "pensamento"):
                print("  " + ev["texto"])
            elif ev["tipo"] == "ferramenta":
                marca = " [AUTOMÁTICA]" if ev["automatica"] else ""
                args = json.dumps(ev["argumentos"], ensure_ascii=False)
                print(f"  🔧 {ev['nome']}{marca} {args[:90]}")
                print(f"     → {json.dumps(ev['resultado'], ensure_ascii=False)[:200]}")
            elif ev["tipo"] == "final":
                v = ev["veredito"]
                print(f"\n  >>> {v['risco']} ({v['pontuacao']}/100) em {ev['tempo']} s")
                print(json.dumps(v, ensure_ascii=False, indent=2))
