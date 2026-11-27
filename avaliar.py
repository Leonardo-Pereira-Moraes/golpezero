"""
Avalia o GolpeZero em todas as mensagens rotuladas de exemplos.txt.

Uso:
    python avaliar.py                 # usa exemplos.txt
    python avaliar.py outro_arquivo.txt

Regra: o rótulo [GOLPE] é acerto se o agente disser GOLPE ou SUSPEITO;
       o rótulo [LEGITIMA] é acerto só se o agente disser SEGURO.
"""

import argparse
import sys
import time

import agente


def cortar(texto: str, tamanho: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= tamanho else texto[: tamanho - 1] + "…"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Avalia o agente GolpeZero.")
    parser.add_argument("arquivo", nargs="?", default="exemplos.txt")
    caminho = parser.parse_args().arquivo

    exemplos = [e for e in agente.carregar_exemplos(caminho) if e["rotulo"]]
    if not exemplos:
        print(f"Nenhuma mensagem rotulada ([GOLPE]/[LEGITIMA]) encontrada em '{caminho}'.")
        return 1

    ok, status = agente.aquecer_modelo()  # aquece antes para não contar o carregamento no tempo
    print(f"Modelo: {agente.MODELO} | Ferramentas: {agente.FONTE_FERRAMENTAS} | {status}")
    if not ok:
        return 1
    print(f"Avaliando {len(exemplos)} mensagens de '{caminho}'...\n")

    linhas = []
    inicio_total = time.perf_counter()
    for i, ex in enumerate(exemplos, 1):
        resultado = agente.analisar(ex["texto"])
        veredito = resultado["veredito"]
        previsto = "LEGITIMA" if veredito["risco"] == "SEGURO" else "GOLPE"
        acertou = previsto == ex["rotulo"]
        linhas.append({**ex, **veredito, "previsto": previsto, "acertou": acertou, "tempo": resultado["tempo"]})
        marca = "✅" if acertou else "❌"
        print(
            f"{marca} {i:>3}/{len(exemplos)}  esperado={ex['rotulo']:<8}  agente={veredito['risco']:<8} "
            f"({veredito['pontuacao']:>3})  {resultado['tempo']:>5.1f}s  {cortar(ex['texto'], 50)}"
        )

    n = len(linhas)
    acertos = sum(l["acertou"] for l in linhas)
    vp = sum(l["rotulo"] == "GOLPE" and l["previsto"] == "GOLPE" for l in linhas)
    fn = sum(l["rotulo"] == "GOLPE" and l["previsto"] == "LEGITIMA" for l in linhas)
    fp = sum(l["rotulo"] == "LEGITIMA" and l["previsto"] == "GOLPE" for l in linhas)
    vn = sum(l["rotulo"] == "LEGITIMA" and l["previsto"] == "LEGITIMA" for l in linhas)
    tempos = [l["tempo"] for l in linhas]

    print("\n" + "=" * 70)
    print(f"  ACURÁCIA:      {acertos / n:.1%}  ({acertos}/{n})")
    print(f"  TEMPO MÉDIO:   {sum(tempos) / n:.1f} s por mensagem  (mín {min(tempos):.1f} s, máx {max(tempos):.1f} s)")
    if vp + fn:
        print(f"  Golpes detectados (recall):   {vp / (vp + fn):.1%}  ({vp}/{vp + fn})")
    if vn + fp:
        print(f"  Legítimas reconhecidas:       {vn / (vn + fp):.1%}  ({vn}/{vn + fp})")
    print(f"  Matriz: VP={vp}  FN={fn}  FP={fp}  VN={vn}   | tempo total {time.perf_counter() - inicio_total:.0f} s")
    print("=" * 70)

    erros = [l for l in linhas if not l["acertou"]]
    if not erros:
        print("\nNenhum erro. 🎉")
        return 0
    print(f"\nERROS ({len(erros)}):")
    print(f"{'#':>3}  {'ESPERADO':<9} {'AGENTE':<9} {'PTS':>3}  MENSAGEM")
    print("-" * 70)
    for l in erros:
        print(f"{linhas.index(l) + 1:>3}  {l['rotulo']:<9} {l['risco']:<9} {l['pontuacao']:>3}  {cortar(l['texto'], 48)}")
        print(f"{'':>3}  ↳ {cortar(l['explicacao'], 62)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
