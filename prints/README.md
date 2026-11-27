# Prints de teste do OCR

Prints de conversas **fictícias**, gerados pela equipe: nomes, números de telefone e links são inventados
(números terminados em `0000`/`1234`, domínios que não pertencem a nenhuma empresa).
**Não usar imagens da internet nem conversas com dados de terceiros.**
Se for acrescentar um print real, tampe nome, foto e número de quem não é da equipe e registre a fonte.

O rótulo vem do nome do arquivo: `golpe_*` é golpe e `legitima_*` é mensagem legítima.

| Arquivo | Golpe / mensagem | Formato |
|---|---|---|
| `golpe_01_falso_banco_sms.png` | Falso banco com link imitando o Nubank | SMS, claro |
| `golpe_02_falso_parente_whatsapp.png` | Falso parente com número novo pedindo Pix | WhatsApp, claro |
| `golpe_03_correios_taxa_sms.png` | Taxa dos Correios com link encurtado | SMS, claro |
| `golpe_04_codigo_whatsapp_escuro.png` | Pedido do código de verificação | WhatsApp, escuro |
| `golpe_05_emprego_falso_escuro.png` | Emprego falso pedindo CPF e chave Pix | WhatsApp, escuro |
| `golpe_06_valor_a_receber_sms.png` | Valor a receber pedindo CPF e senha | SMS, claro |
| `legitima_01_pedido_entrega_whatsapp.png` | Aviso de entrega de loja | WhatsApp, claro |
| `legitima_02_churrasco_escuro.png` | Conversa entre amigos citando "pix" | WhatsApp, escuro |

Testar:

```
python ocr.py prints/golpe_01_falso_banco_sms.png   # um print
python avaliar_ocr.py --so-ocr                       # texto extraído de todos
python avaliar_ocr.py                                # print -> OCR -> agente, com acurácia
```
