# CRM

<a id="09"></a>
## 09. Trava do quadro

Arquivo: [09_trava_do_quadro/trava_do_quadro.py](09_trava_do_quadro/trava_do_quadro.py)

Quando alguém da equipe leva um card para outro quadro, ele fica lá: nenhuma automação traz de volta. A automação continua livre para trocar o card de coluna dentro do mesmo quadro, e o avanço normal da esteira (ex.: Leads → Contratação) continua passando.

Toda movimentação, inclusive as recusadas pela trava, fica em `wa_board_hist`. `GET /conversas/{id}/board-historico` responde "quem tirou meu card daqui".

**Aplicar:**
1. 3 colunas novas em `wa_conversas` (o `ALTER TABLE` está no arquivo) e o modelo `MoveBoard`.
2. As funções no `atendimento.py`.
3. **Daqui em diante, toda automação move card por `_mover_automatico`.**
4. O trecho do fim do arquivo vai dentro de `mover_etapa`.
5. Opcional: na tela, um cadeado no card para ligar e desligar a trava (`POST /conversas/{id}/board-trava`).

<a id="10"></a>
## 10. Régua de contatos

Arquivo: [10_regua_de_contatos/regua_de_contatos.py](10_regua_de_contatos/regua_de_contatos.py)

Responde, sem ninguém digitar nada: em que contato o lead está (1º, 2º, 3º...), quem fez cada um, por qual canal e se ele respondeu. Mensagens seguidas sem resposta, num intervalo de até 6 horas, contam como **um** contato, do jeito que a equipe conta.

**O que entrega:**
- **Capa do card:** cada card do quadro passa a trazer `contatos_total`, `aguardando_retorno` ("o lead respondeu e ninguém voltou"), `horas_aguardando` e `sem_resposta_seguidos`.
  - Na tela, mostre um selo com o número de contatos e um alerta vermelho quando `aguardando_retorno` for verdadeiro. Esse alerta é o que mais ajuda no dia a dia.
- **`GET /conversas/{id}/regua-contatos`:** a linha do tempo dos contatos de um lead.
- **`GET /regua-contatos?pipeline_id=&etapa=`:** a coluna inteira, com o lead mais parado primeiro.

<a id="11"></a>
## 11. Classificação mora no contato

Arquivo: [11_classificacao_no_contato/classificacao_contato.py](11_classificacao_no_contato/classificacao_contato.py)

Lead que volta a escrever meses depois, ou por outro número do escritório, nasce na coluna, no quadro e com a responsável de antes, em vez de cair de novo em "Novo Lead". A classificação fica guardada pelo telefone em `wa_contato_classificacao`, e a tabela nasce sozinha.

Exceção: se o último lugar dele era uma coluna de perda, o card nasce na entrada, com uma nota contando de onde veio, para alguém reavaliar.

**Encaixar em 3 pontos do `atendimento.py`:**

```python
# 1) mover_etapa (gente moveu) e _mover_automatico (automacao moveu), depois de mudar a etapa:
await classificacao_contato.lembrar(db, conv, user.email, 'ui')      # ou (db, conv, quem, origem)

# 2) webhook, logo depois de criar a conversa nova (db.add(conv); await db.flush()):
reg = await classificacao_contato.recuperar(db, tel_store)
if reg:
    herdou = classificacao_contato.pode_herdar(reg) and await _coluna_existe(db, reg['pipeline_id'], reg['etapa'])
    if herdou:
        conv.pipeline_id, conv.etapa = reg['pipeline_id'], reg['etapa']
        if reg.get('atendente_email'):
            conv.atendente_email = reg['atendente_email']
        if reg.get('tag') and not (conv.tag or '').strip():
            conv.tag = reg['tag']          # a AREA volta junto
    nome = (await db.execute(select(Pipeline.nome).where(Pipeline.id == reg['pipeline_id']))).scalar_one_or_none()
    db.add(Mensagem(conversa_id=conv.id, origem='nota', autor='sistema', tipo='texto',
                    conteudo=classificacao_contato.nota_de_volta(reg, nome, herdou)))

# 3) envolva cada chamada em try/except: se falhar, a conversa segue o caminho normal.
```

Os nomes das colunas de perda ficam na lista `PERDA`, no topo do arquivo. Ajuste para as do quadro.

<a id="12"></a>
## 12. Origem do anúncio

Arquivo: [12_origem_do_anuncio/ctwa.py](12_origem_do_anuncio/ctwa.py)

Quando o lead chega por anúncio "clique para WhatsApp" do Meta, o webhook traz o id do anúncio e o código do clique (`ctwa_clid`). O sistema guarda isso em `wa_ctwa`, e a tabela nasce sozinha. Com esses dados dá para saber qual anúncio traz lead de cada área e, no futuro, devolver ao Meta a informação de que aquele clique virou cliente.

**Encaixar no webhook**, na mensagem recebida, em melhor esforço:

```python
try:
    achado = ctwa.achar(payload)
    if achado:
        await ctwa.guardar(db, conv.id, dados['telefone'], achado)
except Exception:
    pass
```

<a id="13"></a>
## 13. Dona do lead e "Meus cards"

Arquivos:
- [13_dona_do_lead/crm_dona.py](13_dona_do_lead/crm_dona.py) (cron)
- [13_dona_do_lead/crm-meus.js](13_dona_do_lead/crm-meus.js) (referência da tela)

Cada lead do quadro de leads tem uma dona, gravada em `wa_conversas.atendente_email`. A regra é:

1. **Quem mandou a primeira mensagem ao lead é a dona.**
2. **Lead que ninguém tocou** é distribuído pela regra de horário. A de origem é: manhã para a vendedora 1, tarde alternando entre as duas. Ajuste em `regra_do_horario` para a regra do escritório.

O script tem três modos:

- `python crm_dona.py` sem argumentos só simula e grava um relatório. Rode primeiro.
- `python crm_dona.py --estoque --aplicar` divide igualmente os leads antigos que estão sem dona. Rode uma vez.
- `python crm_dona.py --novos` grava direto. É o que vai no cron, a cada minuto.

O script usa `fcntl`, então só roda em Linux (a VPS).

**Na tela:**
- A vendedora abre o CRM já em **"Meus cards"**, que usa o filtro `meus=true`. O sistema Braga & Braz já aceita esse filtro em `GET /conversas`.
- Um botão alterna para "Todos".
- O admin ganha um seletor "Todos / Vendedora 1 / Vendedora 2".

**Ajustar:** `VENDEDORAS` (e-mails e nomes), `QUADROS` (ids) e a regra de horário. Combine com o Renato antes de ligar, porque muda o que cada pessoa vê.
