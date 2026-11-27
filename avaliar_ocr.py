"""
Avalia o caminho completo "print -> OCR -> agente" com as imagens da pasta prints/.

O rótulo vem do nome do arquivo: golpe_*.png é [GOLPE] e legitima_*.png é [LEGITIMA].

Uso:
    python avaliar_ocr.py              # OCR + agente (precisa do Ollama rodando)
    python avaliar_ocr.py --so-ocr     # só mostra o texto extraído de cada print
    python avaliar_ocr.py outra_pasta

Regra (a mesma do avaliar.py): [GOLPE] é acerto se o agente disser GOLPE ou SUSPEITO;
[LEGITIMA] é acerto só se o agente disser SEGURO.
"""

import argparse
import sys
import time
from pathlib import Path

import ocr

EXTENSOES = {".png", ".jpg", ".jpeg", ".webp"}


def rotulo_do_arquivo(caminho: Path) -> str | None:
    nome = caminho.stem.lower()
    if nome.startswith("golpe"):
        return "GOLPE"
    if nome.startswith(("legitima", "legítima")):
        return "LEGITIMA"
    return None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Avalia OCR + agente com os prints de teste.")
    parser.add_argument("pasta", nargs="?", default="prints")
    parser.add_argument("--so-ocr", action="store_true", help="só extrai e mostra o texto, sem chamar o agente")
    args = parser.parse_args()

    pasta = Path(args.pasta)
    if not pasta.is_absolute() and not pasta.exists():
        pasta = Path(__file__).parent / pasta
    prints = sorted(p for p in pasta.glob("*") if p.suffix.lower() in EXTENSOES and rotulo_do_arquivo(p))
    if not prints:
        print(f"Nenhum print golpe_*/legitima_* encontrado em '{pasta}'.")
        return 1
    if not ocr.ocr_disponivel():
        print("Tesseract não encontrado (ou sem o idioma Portuguese). Veja a instalação no README.")
        return 1

    if args.so_ocr:
        for p in prints:
            inicio = time.perf_counter()
            texto = ocr.extrair_texto(p)
            print(f"=== {p.name}  ({time.perf_counter() - inicio:.1f} s)\n{texto or '(nenhum texto encontrado)'}\n")
        return 0

    import agente  # só importa o agente (e o Ollama) quando for analisar

    ok, status = agente.aquecer_modelo()
    print(f"Modelo: {agente.MODELO} | {status}")
    if not ok:
        return 1
    print(f"Avaliando {len(prints)} prints de '{pasta}'...\n")

    linhas = []
    for i, p in enumerate(prints, 1):
        inicio = time.perf_counter()
        texto = ocr.extrair_texto(p)
        tempo_ocr = time.perf_counter() - inicio
        if not texto:
            linhas.append({"arquivo": p.name, "rotulo": rotulo_do_arquivo(p), "risco": "SEM TEXTO", "acertou": False,
                           "tempo_ocr": tempo_ocr, "tempo_agente": 0.0})
            print(f"❌ {i:>2}/{len(prints)}  {p.name}: o OCR não extraiu texto")
            continue
        veredito_completo = agente.analisar(texto)
        veredito = veredito_completo["veredito"]
        previsto = "LEGITIMA" if veredito["risco"] == "SEGURO" else "GOLPE"
        rotulo = rotulo_do_arquivo(p)
        acertou = previsto == rotulo
        linhas.append({"arquivo": p.name, "rotulo": rotulo, "risco": veredito["risco"], "acertou": acertou,
                       "tempo_ocr": tempo_ocr, "tempo_agente": veredito_completo["tempo"]})
        print(f"{'✅' if acertou else '❌'} {i:>2}/{len(prints)}  esperado={rotulo:<8} agente={veredito['risco']:<8} "
              f"({veredito['pontuacao']:>3})  OCR {tempo_ocr:.1f} s + agente {veredito_completo['tempo']:.1f} s  {p.name}")

    n = len(linhas)
    acertos = sum(l["acertou"] for l in linhas)
    print("\n" + "=" * 70)
    print(f"  ACURÁCIA (print -> OCR -> agente): {acertos / n:.1%}  ({acertos}/{n})")
    print(f"  TEMPO MÉDIO: OCR {sum(l['tempo_ocr'] for l in linhas) / n:.1f} s + "
          f"agente {sum(l['tempo_agente'] for l in linhas) / n:.1f} s por print")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
