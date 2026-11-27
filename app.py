"""
GolpeZero — interface Streamlit com identidade de "laudo de perícia digital".
Rode com:  streamlit run app.py
"""

import base64
import difflib
import html
import io
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import streamlit as st

import agente

try:  # OCR é opcional: sem pytesseract/Tesseract o app funciona só com texto
    import ocr
except Exception:
    ocr = None

BASE = Path(__file__).parent
ARQ_CONTADOR = BASE / "contador.json"
ARQ_EXEMPLOS = BASE / "exemplos.txt"

COR_RISCO = {"SEGURO": "#2F6B3A", "SUSPEITO": "#B7791F", "GOLPE": "#B3261E"}

st.set_page_config(page_title="GolpeZero — Laudo de análise", layout="wide", initial_sidebar_state="collapsed")

# ---------------------------------------------------------------------------
# CSS — só fontes do sistema (offline), cantos retos, sem degradês
# ---------------------------------------------------------------------------
CSS = """
<style>
:root {
  --papel:#F4F1EA; --papel2:#FAF8F3; --tinta:#1A1A1A; --cinza:#6B665C; --linha:#CFC8B8;
  --serif: Georgia, "Times New Roman", serif;
  --sans: "Segoe UI", system-ui, -apple-system, Arial, sans-serif;
  --mono: Consolas, "Courier New", monospace;
}
.stApp { background: var(--papel); color: var(--tinta); }
.stApp, .stApp p, .stApp li, .stApp textarea, .stApp button { font-family: var(--sans); }

/* Esconde o cromo padrão do Streamlit */
header[data-testid="stHeader"], #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stDeployButton"], [data-testid="stAppDeployButton"] { display:none !important; }
[data-testid="stMainBlockContainer"], .block-container { padding-top:1.3rem !important; padding-bottom:1.2rem !important; max-width:1360px; }

/* Cabeçalho de documento */
.doc-cab { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; flex-wrap:wrap;
  border-bottom:1px solid var(--tinta); padding-bottom:.55rem; margin-bottom:1.5rem; }
.doc-marca { font-family:var(--serif); font-size:1.9rem; font-weight:700; letter-spacing:.32em; line-height:1; }
.doc-sub { font-family:var(--mono); font-size:.72rem; letter-spacing:.08em; color:var(--cinza); margin-left:1.1rem; }
.doc-cont { font-family:var(--mono); font-size:.8rem; color:var(--cinza); }
.doc-cont b { color:var(--tinta); font-weight:700; }

/* Títulos de seção */
.sec { font-family:var(--serif); font-size:.92rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
  border-bottom:1px solid var(--linha); padding-bottom:.35rem; margin:0 0 .8rem 0; }
.sub { font-family:var(--mono); font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color:var(--cinza); margin:1.3rem 0 .2rem 0; }
.cinza { font-family:var(--mono); font-size:.84rem; color:var(--cinza); }
.aviso { font-family:var(--mono); font-size:.8rem; border-left:3px solid var(--tinta); padding:.35rem .7rem; margin:.4rem 0 .8rem 0; }

/* Campo de texto */
.stTextArea [data-baseweb="textarea"], .stTextArea [data-baseweb="base-input"] {
  border-radius:0 !important; border-color:var(--tinta) !important; border-width:1px !important; background:var(--papel2) !important; }
.stTextArea textarea { background:var(--papel2) !important; color:var(--tinta) !important; font-size:.97rem !important; line-height:1.45 !important; }

/* Botões */
.stButton > button { border-radius:0 !important; box-shadow:none !important; }
[data-testid="stBaseButton-primary"] { background:var(--tinta) !important; border:1px solid var(--tinta) !important; padding:.5rem 1.2rem !important; }
[data-testid="stBaseButton-primary"]:hover { background:#000 !important; }
[data-testid="stBaseButton-primary"] p { color:var(--papel) !important; font-weight:600; letter-spacing:.04em; }
.st-key-caixa_limpar button { background:none !important; border:none !important; padding:.5rem 0 !important; min-height:0 !important; justify-content:flex-start !important; }
.st-key-caixa_limpar button p { color:var(--cinza) !important; text-decoration:underline; font-size:.9rem; }
.st-key-caixa_limpar button:hover p { color:var(--tinta) !important; }
.st-key-caixa_exemplos [data-testid="stVerticalBlock"] { gap:0 !important; }
.st-key-caixa_exemplos button { background:none !important; border:none !important; border-bottom:1px dotted var(--linha) !important;
  padding:.38rem 0 !important; min-height:0 !important; justify-content:flex-start !important; width:100%; }
.st-key-caixa_exemplos button > div, .st-key-caixa_exemplos button [data-testid="stMarkdownContainer"] { width:100%; min-width:0; }
.st-key-caixa_exemplos button p { font-size:.88rem; text-align:left; color:var(--tinta);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.st-key-caixa_exemplos button:hover p { text-decoration:underline; }

/* Registro da investigação (log) */
.log { font-family:var(--mono); font-size:.82rem; line-height:1.55; }
.log .l { display:flex; gap:1rem; padding:.08rem 0; }
.log .t { color:var(--cinza); flex:none; }
.log .m { white-space:pre-wrap; word-break:break-word; }
.log .f { font-weight:700; }
.log .s { color:var(--cinza); }

/* Laudo */
.laudo { border:1px solid var(--tinta); background:var(--papel2); }
.laudo-cab { display:flex; justify-content:space-between; flex-wrap:wrap; gap:.4rem 1.2rem; font-family:var(--mono); font-size:.78rem;
  letter-spacing:.04em; border-bottom:1px solid var(--tinta); padding:.55rem 1.2rem; }
.laudo-cab b { letter-spacing:.1em; }
.laudo-corpo { display:grid; grid-template-columns:320px 1fr; gap:2.4rem; padding:1.5rem 1.4rem 1.2rem 1.4rem; }
.carimbo { display:inline-block; transform:rotate(-4deg); border:5px double currentColor; padding:.5rem 1.2rem .45rem 1.2rem;
  text-align:center; margin:.7rem 0 1.6rem .5rem; }
.carimbo .v { font-family:var(--sans); font-weight:800; font-size:2.3rem; letter-spacing:.14em; line-height:1; }
.carimbo .p { font-family:var(--mono); font-size:.82rem; letter-spacing:.2em; margin-top:.4rem; border-top:1px solid currentColor; padding-top:.3rem; }
.laudo ol { margin:.2rem 0 0 1.3rem; padding:0; }
.laudo li { margin:.15rem 0; line-height:1.45; }
.parag { font-size:1rem; line-height:1.55; margin:.2rem 0 0 0; }
.laudo .sub:first-child { margin-top:0; }
.obs { font-family:var(--mono); font-size:.76rem; color:var(--cinza); margin-top:1rem; }

/* Escala 0–100 */
.escala { position:relative; margin:1.4rem .3rem 0 .3rem; }
.trilho { position:relative; height:1px; background:var(--tinta); }
.corte { position:absolute; top:-4px; width:1px; height:9px; background:var(--tinta); }
.marca { position:absolute; top:-8px; width:3px; height:17px; transform:translateX(-50%); }
.marca-v { position:absolute; top:-1.6rem; transform:translateX(-50%); font-family:var(--mono); font-size:.75rem; font-weight:700; }
.rotulos { position:relative; height:1rem; font-family:var(--mono); font-size:.66rem; color:var(--cinza); margin-top:.45rem; }
.rotulos span { position:absolute; transform:translateX(-50%); white-space:nowrap; }
.rotulos.faixas span { transform:none; text-align:center; }

/* Material analisado: balão do WhatsApp (única exceção à paleta) */
.material { border-top:1px solid var(--linha); padding:.9rem 1.4rem 1.2rem 1.4rem; }
.wa { display:inline-block; position:relative; max-width:520px; background:#DCF8C6; color:#111; border-radius:2px;
  padding:.45rem .65rem 1.15rem .65rem; font-size:.86rem; line-height:1.4; white-space:pre-wrap; word-wrap:break-word;
  box-shadow:0 1px 0 rgba(0,0,0,.12); margin-top:.4rem; }
.wa .h { position:absolute; right:.5rem; bottom:.2rem; font-size:.66rem; color:#667781; }

/* Material analisado vindo de print: miniatura + texto lido por OCR */
.mat-print { display:flex; gap:1.4rem; align-items:flex-start; flex-wrap:wrap; margin-top:.4rem; }
.print { margin:0; flex:none; max-width:260px; }
.print img { display:block; width:100%; max-width:260px; height:auto; border:1px solid var(--tinta); border-radius:0; box-shadow:none; }
.print figcaption { font-family:var(--mono); font-size:.68rem; letter-spacing:.04em; color:var(--cinza); margin-top:.35rem; }
.mat-texto { flex:1; min-width:240px; }
.ocr-txt { white-space:pre-wrap; word-wrap:break-word; font-size:.9rem; line-height:1.45;
  border-left:2px solid var(--linha); padding:.1rem 0 .1rem .8rem; }

/* Upload de print (OCR) */
.st-key-caixa_print [data-testid="stFileUploaderDropzone"] { border-radius:0 !important; border:1px dashed var(--linha) !important;
  background:var(--papel2) !important; padding:.55rem .8rem !important; }
.st-key-caixa_print [data-testid="stFileUploaderDropzone"] button { border-radius:0 !important; }
.st-key-caixa_print small, .st-key-caixa_print [data-testid="stFileUploaderDropzoneInstructions"] span { font-family:var(--mono); font-size:.72rem; color:var(--cinza); }

.rodape { font-family:var(--mono); font-size:.72rem; color:var(--cinza); border-top:1px solid var(--linha); margin-top:2rem; padding-top:.6rem; }

@media (max-width: 900px) { .laudo-corpo { grid-template-columns:1fr; } }
</style>
"""

_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def h(texto) -> str:
    return html.escape(str(texto))


def sem_emoji(texto: str) -> str:
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", texto)).strip()


def bloco(conteudo: str, alvo=st) -> None:
    """Renderiza HTML. Remove a indentação das linhas para o Markdown não virar bloco de código."""
    alvo.markdown(" ".join(l.strip() for l in conteudo.splitlines() if l.strip()), unsafe_allow_html=True)


def num(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Contador persistente (contador.json)
# ---------------------------------------------------------------------------
def ler_contador() -> dict:
    hoje = date.today().isoformat()
    try:
        dados = json.loads(ARQ_CONTADOR.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    if dados.get("data") != hoje:
        dados = {"data": hoje, "hoje": 0, "total": int(dados.get("total", 0) or 0)}
    return dados


def incrementar_contador() -> dict:
    dados = ler_contador()
    dados["hoje"] += 1
    dados["total"] = dados.get("total", 0) + 1
    try:
        temporario = ARQ_CONTADOR.with_name(ARQ_CONTADOR.name + ".tmp")
        temporario.write_text(json.dumps(dados), encoding="utf-8")
        os.replace(temporario, ARQ_CONTADOR)
    except OSError:
        pass  # contador nunca pode derrubar a demo
    return dados


# ---------------------------------------------------------------------------
# Componentes visuais
# ---------------------------------------------------------------------------
def html_cabecalho(contador: dict) -> str:
    modelo = agente.MODELO.upper().replace(":", "-")
    return (
        '<div class="doc-cab"><div><span class="doc-marca">GOLPEZERO</span>'
        f'<span class="doc-sub">UNIDADE DE ANÁLISE DE GOLPES · MODELO LOCAL {h(modelo)} · OFFLINE</span></div>'
        f'<div class="doc-cont">Laudos emitidos hoje: <b>{contador["hoje"]:03d}</b></div></div>'
    )


def texto_evento(ev: dict) -> tuple[str, str]:
    """Converte um evento do agente em (classe_css, linha do log)."""
    if ev["tipo"] == "etapa":
        return "", sem_emoji(ev["texto"])
    if ev["tipo"] == "pensamento":
        texto = " ".join(sem_emoji(ev["texto"]).split())
        return "s", "modelo: " + (texto if len(texto) <= 300 else texto[:300] + "…")

    nome, args, res = ev["nome"], ev.get("argumentos") or {}, ev.get("resultado") or {}
    prefixo = "[auto] " if ev.get("automatica") else ""
    if nome == "analisar_link":
        chamada = f'analisar_link("{args.get("url", "")}")'
    else:
        chamada = nome

    if "erro" in res:
        saida = f"ERRO: {res['erro']}"
    elif nome == "analisar_link":
        motivos = "; ".join(map(str, res.get("motivos") or []))
        saida = ("SUSPEITO" + (f": {motivos}" if motivos else "")) if res.get("suspeito") else "sem alertas"
    elif nome == "buscar_padroes":
        encontrados = res.get("encontrados") or {}
        total = res.get("total", sum(len(v) for v in encontrados.values() if isinstance(v, list)))
        if total:
            palavras = []
            for lista_cat in encontrados.values():
                for p in lista_cat if isinstance(lista_cat, list) else [lista_cat]:
                    if str(p) not in palavras:
                        palavras.append(str(p))
            citadas = ", ".join(f'"{p}"' for p in palavras[:5]) + (", …" if len(palavras) > 5 else "")
            saida = f"{total} ocorrência{'s' if total != 1 else ''}: {citadas}"
        else:
            saida = "nenhuma ocorrência"
    else:
        saida = json.dumps(res, ensure_ascii=False)[:200]
    return "f", f"{prefixo}{chamada} → {saida}"


def html_log(registro: list) -> str:
    linhas = []
    for hora, ev in registro:
        if ev["tipo"] == "final":
            continue
        classe, texto = texto_evento(ev)
        linhas.append(f'<div class="l"><span class="t">{h(hora)}</span><span class="m {classe}">{h(texto)}</span></div>')
    return f'<div class="log">{"".join(linhas)}</div>'


def html_escala(valor: int, cor: str) -> str:
    return (
        '<div class="escala"><div class="trilho">'
        '<span class="corte" style="left:0"></span><span class="corte" style="left:30%"></span>'
        '<span class="corte" style="left:70%"></span><span class="corte" style="left:100%"></span>'
        f'<span class="marca" style="left:{valor}%;background:{cor}"></span>'
        f'<span class="marca-v" style="left:{valor}%;color:{cor}">{valor}</span></div>'
        '<div class="rotulos"><span style="left:0">0</span><span style="left:30%">30</span>'
        '<span style="left:70%">70</span><span style="left:100%">100</span></div>'
        '<div class="rotulos faixas"><span style="left:0;width:30%">seguro</span>'
        '<span style="left:30%;width:40%">suspeito</span>'
        '<span style="left:70%;width:30%">golpe</span></div></div>'
    )


@st.cache_data(max_entries=8, show_spinner=False)
def miniatura_data_uri(imagem: bytes) -> str:
    """Reduz o print (2x a largura exibida, para ficar nítido) e devolve como data URI PNG. "" se falhar."""
    try:
        from PIL import Image, ImageOps

        original = Image.open(io.BytesIO(imagem))
        formato = (original.format or "").upper()
        if original.width <= 520 and formato in ("PNG", "JPEG", "WEBP") and not original.getexif().get(0x0112):
            # já é pequeno e não precisa girar: usa os bytes originais (reconverter só aumentaria o arquivo)
            return f"data:image/{formato.lower()};base64," + base64.b64encode(imagem).decode("ascii")
        foto = ImageOps.exif_transpose(original)
        foto = foto.convert("RGBA" if foto.mode in ("RGBA", "LA", "P") else "RGB")
        foto.thumbnail((520, 2400))
        saida = io.BytesIO()
        foto.save(saida, format="PNG", optimize=True)
    except Exception:
        return ""
    if len(saida.getvalue()) >= len(imagem) and formato in ("PNG", "JPEG", "WEBP") and not original.getexif().get(0x0112):
        # print de texto reduzido às vezes fica maior que o original: usa o menor
        return f"data:image/{formato.lower()};base64," + base64.b64encode(imagem).decode("ascii")
    return "data:image/png;base64," + base64.b64encode(saida.getvalue()).decode("ascii")


def html_material(mensagem: str, hora_msg: str, print_bytes: bytes | None) -> str:
    """Print enviado: miniatura + texto lido por OCR. Mensagem digitada: balão do WhatsApp."""
    uri = miniatura_data_uri(print_bytes) if print_bytes else ""
    if uri:
        return (
            '<div class="mat-print">'
            f'<figure class="print"><img src="{uri}" alt="Print enviado">'
            "<figcaption>Print enviado · texto lido por OCR</figcaption></figure>"
            f'<div class="mat-texto"><div class="ocr-txt">{h(mensagem)}</div></div>'
            "</div>"
        )
    return f'<div class="wa">{h(mensagem)}<span class="h">{h(hora_msg)} ✓✓</span></div>'


def mesmo_material(texto: str, texto_ocr: str) -> bool:
    """O texto do campo ainda é o do print? Correções pequenas contam como o mesmo material."""
    a, b = " ".join(texto.split()), " ".join((texto_ocr or "").split())
    return bool(b) and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6)


def html_laudo(final: dict, numero: int, emitido: str, mensagem: str, hora_msg: str, print_bytes: bytes | None = None) -> str:
    v = final["veredito"]
    cor = COR_RISCO.get(v["risco"], COR_RISCO["SUSPEITO"])
    n, auto = final.get("ferramentas", 0), final.get("automaticas", 0)
    verificacoes = f"{n} verificaç{'ões' if n != 1 else 'ão'}" + (f" ({auto} automática{'s' if auto != 1 else ''})" if auto else "")

    if v["sinais_de_alerta"]:
        indicios = "<ol>" + "".join(f"<li>{h(s)}</li>" for s in v["sinais_de_alerta"]) + "</ol>"
    else:
        indicios = '<div class="parag">Nenhum indício de golpe encontrado.</div>'
    obs = (
        '<div class="obs">Observação: o modelo não concluiu a análise; parecer emitido por regra de segurança.</div>'
        if final.get("fallback")
        else ""
    )

    return f"""
    <div class="laudo">
      <div class="laudo-cab">
        <span><b>LAUDO Nº {numero:03d}/{date.today().year}</b></span>
        <span>Emitido em {h(emitido)}</span>
        <span>Tempo de análise {num(final.get("tempo", 0))} s · {h(final.get("modelo", agente.MODELO))} · {verificacoes}</span>
      </div>
      <div class="laudo-corpo">
        <div>
          <div class="sub">Veredito</div>
          <div class="carimbo" style="color:{cor}"><div class="v">{h(v["risco"])}</div><div class="p">RISCO {v["pontuacao"]}/100</div></div>
          <div class="sub">Escala de risco</div>
          {html_escala(v["pontuacao"], cor)}
        </div>
        <div>
          <div class="sub">Indícios encontrados</div>
          {indicios}
          <div class="sub">Parecer</div>
          <div class="parag">{h(v["explicacao"])}</div>
          <div class="sub">Recomendação</div>
          <div class="parag">{h(v["orientacao"])}</div>
          {obs}
        </div>
      </div>
      <div class="material">
        <div class="sub" style="margin-top:0">Material analisado</div>
        {html_material(mensagem, hora_msg, print_bytes)}
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Estado e aquecimento do modelo
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner="Carregando o modelo local na memória...")
def aquecer() -> tuple[bool, str]:
    return agente.aquecer_modelo()


@st.cache_resource(show_spinner=False)
def ocr_ok() -> bool:
    return bool(ocr and ocr.ocr_disponivel())


@st.cache_data(ttl=30)
def exemplos() -> list[dict]:
    return agente.carregar_exemplos(ARQ_EXEMPLOS)


ESTADO_INICIAL = {"mensagem": "", "eventos": [], "final": None, "analisada": None, "hora": "", "laudo_num": 0, "emitido": "",
                  "aviso_print": "", "origem_print": "",
                  "print_bytes": None,  # bytes do último print enviado
                  "texto_ocr": "",      # texto que o OCR leu dele (para saber se o campo foi trocado)
                  "laudo_print": None}  # print exibido no laudo atual (None = mensagem digitada)
for chave, padrao in ESTADO_INICIAL.items():
    st.session_state.setdefault(chave, padrao)

SEM_PRINT = {"aviso_print": "", "origem_print": "", "print_bytes": None, "texto_ocr": "", "laudo_print": None}


def usar_exemplo(texto: str) -> None:
    st.session_state.mensagem = texto
    st.session_state.update(eventos=[], final=None, analisada=None, **SEM_PRINT)


def limpar() -> None:
    st.session_state.update(mensagem="", eventos=[], final=None, analisada=None, **SEM_PRINT)


def ler_print() -> None:
    """Callback do upload: extrai o texto do print (OCR) e coloca no campo, para o visitante conferir antes de analisar."""
    arquivo = st.session_state.get("upload_print")
    if arquivo is None:
        return
    imagem = arquivo.getvalue()
    texto = ocr.extrair_texto(imagem)
    if texto:
        st.session_state.mensagem = texto
        st.session_state.update(
            eventos=[], final=None, analisada=None, aviso_print="", origem_print=arquivo.name,
            print_bytes=imagem, texto_ocr=texto,
        )
    else:
        st.session_state.update(
            aviso_print="Não foi possível ler texto neste print. Tente uma imagem mais nítida ou cole a mensagem.",
            origem_print="", print_bytes=None, texto_ocr="",
        )


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------
bloco(CSS)
cabecalho_ph = st.empty()
cabecalho_ph.markdown(html_cabecalho(ler_contador()), unsafe_allow_html=True)

ok, status = aquecer()
if not ok:
    aquecer.clear()  # tenta de novo no próximo clique/recarregamento
    bloco(f'<div class="aviso">ATENÇÃO — Ollama indisponível. {h(status)}</div>')

esq, dir_ = st.columns([5, 6], gap="large")

with esq:
    bloco('<div class="sec">1. Material recebido</div>')
    st.text_area(
        "Mensagem",
        key="mensagem",
        height=170,
        label_visibility="collapsed",
        placeholder="Cole aqui a mensagem de WhatsApp, SMS ou e-mail a ser analisada.",
    )
    if ocr_ok():
        with st.container(key="caixa_print"):
            st.file_uploader(
                "Ou envie um print da conversa",
                type=["png", "jpg", "jpeg", "webp"],
                key="upload_print",
                on_change=ler_print,
                label_visibility="collapsed",
                help="O texto do print é lido no próprio computador (OCR) e colocado no campo acima.",
            )
        if st.session_state.origem_print:
            bloco(f'<div class="cinza">Texto extraído de <b>{h(st.session_state.origem_print)}</b> por OCR. Confira e corrija antes de analisar.</div>')
        if st.session_state.aviso_print:
            bloco(f'<div class="aviso">{h(st.session_state.aviso_print)}</div>')
    b1, b2 = st.columns([3, 2])
    clicou = b1.button("Analisar mensagem", type="primary", width="stretch")
    with b2.container(key="caixa_limpar"):
        st.button("Limpar", on_click=limpar)
    aviso_ph = st.empty()

    bloco('<div class="sub">Exemplos de material</div>')
    lista = exemplos()
    if lista:
        with st.container(key="caixa_exemplos"):
            for i, ex in enumerate(lista):
                resumo = ex.get("titulo") or " ".join(ex["texto"].split())
                resumo = resumo if len(resumo) <= 90 else resumo[:88] + "…"
                st.button(f"{i + 1:02d} — {resumo}", key=f"ex{i}", on_click=usar_exemplo, args=(ex["texto"],), help=ex["texto"])
    else:
        bloco('<div class="cinza">Nenhum exemplo disponível (exemplos.txt não encontrado).</div>')

with dir_:
    bloco('<div class="sec">2. Registro da investigação</div>')
    log_ph = st.empty()

bloco('<div class="sec sec-laudo" style="margin-top:2rem;scroll-margin-top:1rem">3. Laudo</div>')
laudo_ph = st.empty()

falhou = False
rolar_ate_laudo = False
if clicou:
    texto = st.session_state.mensagem.strip()
    if not texto:
        bloco('<div class="aviso">Cole uma mensagem antes de analisar.</div>', aviso_ph)
    else:
        if not ok:
            aquecer.clear()
            ok, status = aquecer()
        if not ok:
            bloco(f'<div class="aviso">Não é possível analisar agora. {h(status)}</div>', aviso_ph)
        else:
            s = st.session_state
            veio_do_print = bool(s.origem_print and s.print_bytes and mesmo_material(texto, s.texto_ocr))
            s.update(
                eventos=[], final=None, analisada=texto, hora=datetime.now().strftime("%H:%M"),
                laudo_print=s.print_bytes if veio_do_print else None,
            )
            bloco('<div class="cinza">Investigação em andamento. O laudo será emitido ao final.</div>', laudo_ph)
            final = None
            try:
                for evento in agente.analisar_stream(texto):
                    st.session_state.eventos.append((datetime.now().strftime("%H:%M:%S"), evento))
                    if evento["tipo"] == "final":
                        final = evento
                    else:
                        log_ph.markdown(html_log(st.session_state.eventos), unsafe_allow_html=True)
            except Exception as erro:  # nunca mostrar traceback para o visitante
                falhou = True
                bloco(f'<div class="aviso">Falha durante a análise: {h(erro)}</div>', laudo_ph)
            if final:
                contador = incrementar_contador()
                st.session_state.update(
                    final=final, laudo_num=contador["hoje"], emitido=datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
                )
                cabecalho_ph.markdown(html_cabecalho(contador), unsafe_allow_html=True)
                rolar_ate_laudo = True

# Estado atual (também re-renderiza a última análise depois de interações na página)
if st.session_state.eventos:
    log_ph.markdown(html_log(st.session_state.eventos), unsafe_allow_html=True)
else:
    bloco('<div class="cinza">Aguardando material para análise.</div>', log_ph)

if st.session_state.final:
    s = st.session_state
    bloco(html_laudo(s.final, s.laudo_num, s.emitido, s.analisada, s.hora, s.laudo_print), laudo_ph)
elif not falhou:
    bloco('<div class="cinza">Nenhum laudo emitido nesta sessão.</div>', laudo_ph)

bloco(
    '<div class="rodape">Laudo gerado automaticamente por agente local. Nenhum dado sai deste computador. · '
    "Leonardo Pereira Moraes &amp; Carlos Daniel Laporte Castro</div>"
)

# ---------------------------------------------------------------------------
# JavaScript (roda na própria página, offline)
# ---------------------------------------------------------------------------
# 1) Desliga o corretor ortográfico do campo de texto (o observer cobre re-renderizações do Streamlit)
JS_SEM_CORRETOR = """
(function () {
  function desligar() {
    document.querySelectorAll('textarea').forEach(function (t) {
      if (t.getAttribute('spellcheck') !== 'false') {
        t.setAttribute('spellcheck', 'false');
        t.setAttribute('autocorrect', 'off');
        t.setAttribute('autocapitalize', 'off');
      }
    });
  }
  desligar();
  if (!window.__gzSemCorretor) {
    window.__gzSemCorretor = new MutationObserver(desligar);
    window.__gzSemCorretor.observe(document.body, { childList: true, subtree: true });
  }
})();
"""
st.html(f"<script>{JS_SEM_CORRETOR}</script>", unsafe_allow_javascript=True)

# 2) Ao terminar uma análise, rola até "3. LAUDO" (fica abaixo da dobra no notebook).
#    O número do laudo no comentário torna o script único, então ele roda de novo a cada laudo.
if rolar_ate_laudo:
    st.html(
        f"<script>/* laudo {st.session_state.laudo_num} {st.session_state.emitido} */"
        "setTimeout(function () { var a = document.querySelector('.sec-laudo');"
        " if (a) a.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 250);</script>",
        unsafe_allow_javascript=True,
    )
