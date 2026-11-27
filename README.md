# GolpeZero 🛡️

**Agente Inteligente contra golpes de engenharia social.**

Recebeu uma mensagem estranha no WhatsApp, por SMS ou por e-mail? Cole o texto no GolpeZero. O agente investiga a mensagem com ferramentas próprias (busca de padrões de golpe e análise de links) e responde se ela é **SEGURA**, **SUSPEITA** ou **GOLPE**. A resposta traz uma pontuação de risco, os sinais de alerta encontrados, uma explicação simples e o que fazer em seguida.

O raciocínio do agente aparece **ao vivo** na tela: cada etapa e cada ferramenta chamada são exibidas enquanto ele trabalha. Tudo roda **100% offline**, com um modelo de linguagem local via [Ollama](https://ollama.com). Nenhuma mensagem sai do computador.

Projeto do workshop de IA da disciplina **Agentes Inteligentes**.

## Arquitetura em 4 camadas

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. INTERFACE          app.py (Streamlit)                             │
│    entrada da mensagem, exemplos, raciocínio ao vivo, contador       │
├──────────────────────────────────────────────────────────────────────┤
│ 2. ORQUESTRAÇÃO       agente.py → analisar_stream()                  │
│    pré-processamento (normaliza texto, extrai URLs)                  │
│    loop de tool calling (até 4 passos) + garantia de ferramentas     │
│    ferramentas.py: buscar_padroes(texto), analisar_link(url)         │
├──────────────────────────────────────────────────────────────────────┤
│ 3. INFERÊNCIA         Ollama local + qwen2.5:3b                      │
│    decide quais ferramentas chamar e interpreta as evidências        │
├──────────────────────────────────────────────────────────────────────┤
│ 4. SAÍDA              JSON estruturado (format=schema, temperature=0)│
│    risco, pontuação 0–100, sinais de alerta, explicação, orientação  │
└──────────────────────────────────────────────────────────────────────┘
```

1. **Interface** (`app.py`): página Streamlit. Mostra a mensagem num balão no estilo WhatsApp, a linha do tempo do raciocínio do agente e o resultado: medidor de risco, selo, sinais de alerta, explicação e "O que fazer".
2. **Orquestração** (`agente.py`): normaliza o texto e extrai os links (com e sem `http`, ex.: `bit.ly/x`, `itau-seguranca.com`). Em seguida roda o loop do agente: o modelo decide quais ferramentas chamar, o agente as executa e devolve os resultados ao modelo. Se o modelo esquecer de chamar `buscar_padroes` ou de analisar algum link, o agente executa a ferramenta por conta própria e entrega o resultado como evidência extra. As ferramentas ficam em `ferramentas.py`.
3. **Inferência**: o modelo `qwen2.5:3b` roda localmente no Ollama, com prompt de sistema em português e 3 exemplos *few-shot* (falso banco com link, "oi mãe, troquei de número" e uma entrega legítima). O modelo fica carregado na memória (`keep_alive="30m"`) para responder rápido.
4. **Saída**: o veredito final é gerado em JSON validado por schema, com `temperature=0`. Se o JSON falhar, o agente responde **SUSPEITO** por segurança. Um link apontado como suspeito nunca resulta em **SEGURO**.

### Arquivos

| Arquivo | Função |
|---|---|
| `app.py` | Interface Streamlit |
| `agente.py` | Agente: pré-processamento, loop de ferramentas, síntese |
| `ferramentas.py` | Ferramentas `buscar_padroes` e `analisar_link` |
| `padroes.json` | Base de padrões de golpe usada pelas ferramentas |
| `exemplos.txt` | Mensagens de exemplo rotuladas `[GOLPE]` / `[LEGITIMA]` |
| `avaliar.py` | Mede acurácia e tempo médio do agente nos exemplos |

## Instalação

1. Instale o **Ollama**: <https://ollama.com/download>
2. Baixe o modelo:
   ```powershell
   ollama pull qwen2.5:3b
   ```
3. Instale as dependências Python (de preferência num ambiente virtual):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

> Notebook mais fraco? Troque a constante `MODELO` no topo de `agente.py` para `"qwen2.5:1.5b"` e rode `ollama pull qwen2.5:1.5b`.

## Como rodar

Com o Ollama aberto:

```powershell
streamlit run app.py
```

O app abre no navegador em `http://localhost:8501`. Na primeira abertura, o modelo é carregado na memória. Se o Ollama não estiver rodando, o app mostra um aviso.

Outros comandos:

```powershell
python agente.py                       # testa o agente no terminal com 3 mensagens
python agente.py "sua mensagem aqui"   # testa uma mensagem específica
python avaliar.py                      # acurácia e tempo médio em exemplos.txt
```

## Integrantes

- Leonardo Pereira Moraes
- Carlos Daniel Laporte Castro
