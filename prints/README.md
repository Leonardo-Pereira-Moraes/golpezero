# Prints de teste do OCR

Prints feitos pela própria equipe, trocando entre nós as mensagens do `exemplos.txt`.
**Não usar imagens da internet nem conversas com dados de terceiros.**
Antes de salvar, confira se não aparece nome, foto ou número de telefone de ninguém de fora da equipe.

| Arquivo | Mensagem (`exemplos.txt`) | Tema |
|---|---|---|
| `golpe1.png` | [GOLPE] Parente pedindo dinheiro | claro |
| `golpe2.png` | [GOLPE] Falso banco | escuro |
| `golpe3.png` | [GOLPE] Código do WhatsApp | claro |
| `golpe4.png` | [GOLPE] Correios / taxa (SMS) | claro ou escuro |
| `legitima1.png` | [LEGITIMA] Código de acesso (2FA) | escuro |

Testar cada um com:

```
python ocr.py prints/golpe1.png
```
