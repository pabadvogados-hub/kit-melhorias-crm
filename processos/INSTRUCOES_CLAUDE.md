# Roteiro para o Claude Code aplicar o módulo Processos no sistema Braga & Braz

Você vai acrescentar um módulo novo: cadastro de **clientes** e **processos** (fase do caso, partes, responsável, histórico), ligado ao que o sistema já tem: o Calendário de prazos, o índice das pastas da REDE e os cards do CRM.

O módulo só **acrescenta**. Não altera nenhuma tabela, rota ou tela existente, exceto três pontos de encaixe no `main.py` e dois no front (menu e rota), listados abaixo.

## Antes de começar

1. **Confira a versão que está no ar.** Se a cópia local estiver atrás da VPS, puxe antes de mexer.
2. **Leia `backend/app/main.py` inteiro** antes de editar. Os trechos abaixo mostram *onde* entram; confira o texto real antes de colar.
3. **Backup do banco** antes do primeiro start com o módulo: `cp sistema_bragabraz.db sistema_bragabraz.db.bak_$(date +%Y%m%d_%H%M)`.
4. **Não mande WhatsApp para lead real em teste.** Este módulo não envia mensagem nenhuma. Ainda assim, confira o básico (chat e CRM) depois de subir.

## Regras durante o trabalho

- **Uma etapa por vez.** Copiou, testou, subiu, conferiu. Só então a próxima.
- **Só acrescente.** Não apague nem renomeie rota, coluna ou função existente.
- **Nada de credencial no repositório.** O módulo não usa chave nova.
- **O que não é decisão técnica está marcado com `DECIDIR` no código e neste roteiro.** Pergunte ao escritório antes de fechar esses pontos.

## Passo 1: copiar o backend

| Origem (kit) | Destino (sistema) |
|---|---|
| `processos/backend/app/processos_models.py` | `backend/app/processos_models.py` |
| `processos/backend/app/processos_nucleo.py` | `backend/app/processos_nucleo.py` |
| `processos/backend/app/routers/processos.py` | `backend/app/routers/processos.py` |
| `processos/backend/carregar_processos_inicial.py` | `backend/carregar_processos_inicial.py` |
| `processos/backend/teste_processos.py` | `backend/teste_processos.py` |

Confira se `backend/app/whatsapp/origem.py` existe no sistema: `routers/relatorios.py` o importa. Se não existir na sua cópia, a falta é anterior a este módulo e não deve ser resolvida aqui.

Compile:

```
python -m py_compile backend/app/processos_models.py backend/app/processos_nucleo.py backend/app/routers/processos.py
```

## Passo 2: registrar no `main.py`

Três encaixes em `backend/app/main.py`:

**a)** Junto dos outros imports de routers (depois de `from .routers.prazos import router as prazos_router`):

```python
from .routers.processos import router as processos_router
from .processos_nucleo import garantir_catalogo
from .database import AsyncSessionLocal
```

**b)** Dentro do `lifespan`, logo depois de `await init_db()`:

```python
    await init_db()
    async with AsyncSessionLocal() as _db:
        await garantir_catalogo(_db)   # modulo Processos: fases padrao na 1a subida
```

**c)** Junto dos outros `include_router`, depois de `app.include_router(relatorios_router)`:

```python
app.include_router(processos_router)
```

Confira: `python -m py_compile backend/app/main.py`.

## Passo 3: tabelas

Não há `ALTER TABLE`. As cinco tabelas novas (`proc_fases`, `proc_clientes`, `proc_processos`, `proc_partes`, `proc_historico`) são criadas pelo `create_all` que o `init_db` já roda a cada subida. Depois de subir uma vez, confira:

```
sqlite3 sistema_bragabraz.db ".tables" | tr ' ' '\n' | grep proc_
```

Deve listar as cinco. A primeira subida também semeia o catálogo de fases (19 fases, ver `DECIDIR` abaixo). Se a tabela `proc_fases` já tiver linhas, nada é semeado de novo.

## Passo 4: testar o módulo isolado

Na pasta `backend/`, com o mesmo Python do sistema:

```
python -I teste_processos.py
```

O teste roda contra um SQLite **temporário** (não toca no banco do sistema), com o `init_db`, os modelos, o núcleo e o router reais. Tem 18 testes e deve terminar com `18 de 18 testes passaram.` e código de saída 0. Se falhar, não siga: a mensagem diz qual teste e por quê.

## Passo 5: front (menu, rota e tela)

Copie para o front:

| Origem (kit) | Destino (sistema) |
|---|---|
| `processos/frontend/src/pages/Processos.jsx` | `frontend/src/pages/Processos.jsx` |
| `processos/frontend/src/pages/ProcessoFicha.jsx` | `frontend/src/pages/ProcessoFicha.jsx` |
| `processos/frontend/src/pages/ProcessosClientes.jsx` | `frontend/src/pages/ProcessosClientes.jsx` |
| `processos/frontend/src/pages/processosUtil.js` | `frontend/src/pages/processosUtil.js` |
| `processos/frontend/src/pages/processos.css` | `frontend/src/pages/processos.css` |

Quatro encaixes:

**a) `frontend/src/modules.js`** — dentro do array `MODULOS`, antes da entrada `pecas`:

```js
  { id: 'processos', nome: 'Processos', desc: 'Clientes e processos: fase de cada caso, partes, prazos e histórico.', ico: '', rota: '/processos', acesso: ['advogado', 'assistente'], pronto: true },
```

O campo `ico` fica vazio de propósito: o sistema não usa emoji na interface. O ícone do menu vem do `Layout.jsx`.

**b) `frontend/src/App.jsx`** — import junto dos outros, e rota junto das outras (antes de `/pecas`):

```jsx
import Processos from './pages/Processos'
```

```jsx
      <Route path="/processos" element={<Protected><ModuloOnly id="processos"><Processos /></ModuloOnly></Protected>} />
```

**c) `frontend/src/components/Layout.jsx`** — ícone do menu, dentro do objeto `ICONES`:

```jsx
  '/processos': <><rect x="3" y="4" width="5" height="16" rx="1" /><rect x="10" y="4" width="5" height="10" rx="1" /><rect x="17" y="4" width="4" height="7" rx="1" /></>,
```

e a largura da página, trocando a linha `const larguraExtra = loc.pathname === '/usuarios'` por:

```jsx
  const larguraExtra = ['/usuarios', '/processos'].includes(loc.pathname)
```

**d) Botão no CRM** — em `frontend/src/pages/Atendimento.jsx`, dentro do `Inbox`, logo depois do bloco `{user?.acesso_contratacao && (<button ... Fechei com o cliente ...>)}` (perto da linha 1636). `irPara` já existe nesse componente:

```jsx
              {conv.tipo_contato === 'cliente' && (
                <button onClick={() => irPara(`/processos?conversa=${conv.id}`)}
                  className="btn btn-sm btn-ghost" style={{ whiteSpace: 'nowrap' }}
                  title="Cria o processo deste cliente no módulo Processos">
                  Criar processo
                </button>
              )}
```

Depois: `cd frontend && npm run build`. Tem de terminar sem erro.

## Passo 6: permissões

O backend decide. A tela só esconde o que o backend negaria.

| Quem | Entra no módulo | Vê | Muda (fase, dados, partes) |
|---|---|---|---|
| admin | sim | tudo | tudo |
| advogado | sim | os processos da sua área e os que são seus | os seus e os sem responsável |
| assistente | sim | o mesmo que advogado | o mesmo que advogado |
| usuario, sdr | não | não | não |

- **Recorte por pessoa:** se o usuário tiver lista preenchida no campo `modulos`, só entra quem tiver `processos` nela (mesma regra do Calendário). Para liberar alguém fora do padrão, acrescente `processos` na lista dele na tela de Usuários.
- **Áreas:** se o usuário tiver `areas_permitidas`, ele só vê processos dessas áreas ou em que é responsável. Sem lista, vê tudo.
- **Papéis que entram por padrão:** estão em `PAPEIS_ACESSO` em `processos_nucleo.py`. `DECIDIR`: confirme com o escritório.
- Criar catálogo de fases (rotas `/api/processos/fases`) é só admin.

## Passo 7: carga inicial (opcional, com cuidado)

Cria os processos que já existem em `pz_prazos` e `pz_pastas`: um por número CNJ distinto, clientes pelo nome. Não apaga nada. Pode ser rodada de novo sem duplicar.

**Sempre comece pelo simular:**

```
cd backend
python carregar_processos_inicial.py --simular
```

Confira a lista. Se estiver certo:

```
python carregar_processos_inicial.py --aplicar
```

O `--aplicar` faz uma cópia do banco antes (`sistema_bragabraz.db.bak_carga_AAAAMMDD-HHMMSS`) e roda uma segunda leitura para conferir: deve dizer `novos em uma segunda leitura = 0`.

Regras da carga:
- Um processo por CNJ. Prazo sem CNJ vira processo pela pasta.
- Pasta da REDE sem CNJ só entra com `--incluir-sem-processo`. `DECIDIR`: são muitas pastas sem número.
- Área fica **vazia**. Ninguém chuta área; o escritório classifica depois.
- Responsável só é preenchido quando há um único responsável nos prazos daquele processo e ele é usuário ativo.
- Fase inicial: `A classificar`.

## Como testar na prática (depois de subir)

1. Abra `/processos` com um usuário advogado. O quadro mostra as fases.
2. `+ Processo`: crie um processo de teste com uma pasta que exista na REDE. Confira se o cliente e o número foram preenchidos sozinhos.
3. Arraste o cartão para outra fase. Abra a ficha e confira a aba Histórico.
4. Abra a aba Prazos: deve listar os prazos do Calendário com aquele número ou pasta.
5. Encerre e reabra. Confira o filtro Encerrados.
6. Exporte a lista em CSV.
7. No CRM, abra um card de cliente: deve aparecer "Criar processo".
8. Confira o básico: chat abre, CRM abre, Calendário abre, mensagem nova chega.

## Como desfazer

**Melhor caminho:** restaurar o backup do banco feito antes (`sistema_bragabraz.db.bak_...`) e remover as linhas dos passos 1, 2 e 5.

**Desfazer só a carga inicial** (se a equipe ainda não mexeu nos processos carregados):

```sql
DELETE FROM proc_historico WHERE processo_id IN (SELECT id FROM proc_processos WHERE criado_por = 'carga-inicial');
DELETE FROM proc_partes    WHERE processo_id IN (SELECT id FROM proc_processos WHERE criado_por = 'carga-inicial');
DELETE FROM proc_processos WHERE criado_por = 'carga-inicial';
DELETE FROM proc_clientes  WHERE criado_por = 'carga-inicial';
```

**Remover o módulo por completo:** tire as três linhas do `main.py`, apague os arquivos copiados e, só se não quiser mais os dados, `DROP TABLE` nas cinco tabelas `proc_*`. Nenhuma tabela existente depende delas.

## Decisões para o escritório (`DECIDIR`)

1. **Quem entra no módulo:** o padrão é admin, advogado e assistente (`PAPEIS_ACESSO`).
2. **Catálogo de fases:** o inicial é genérico de processo cível (19 fases em 7 grupos; a primeira é "A classificar"). Ajuste nomes e grupos na tela (só admin) antes da carga.
3. **Quem move a fase:** hoje, só o responsável ou quem vê o processo sem responsável. Confirme.
4. **Encerrar:** muda só o status, não a fase. A fase final diz como terminou (ex.: "Acordo homologado"). Confirme se prefere que encerrar mude a fase.
5. **Área obrigatória:** hoje é opcional. Processo sem área só aparece para o responsável e para o admin, quando há restrição de área.
6. **Carga:** incluir ou não as pastas sem CNJ (`--incluir-sem-processo`).
7. **Validação de CPF/CNPJ:** o módulo só confere a quantidade de dígitos (11 ou 14), não o dígito verificador.

## Integrações que este módulo deixa prontas

- **Intimações (outro módulo):** `from .processos_nucleo import achar_processo` e `await achar_processo(db, numero)` devolve o processo pelo CNJ, em qualquer formato, mesmo que esteja encerrado. Quem chama decide o que fazer com ele.
- **Índice da REDE:** o módulo só lê `pz_pastas`. Para atualizar a leitura da REDE, use o `POST /api/prazos/pastas/reindexar` que já existe (admin).
- **CRM:** um processo criado a partir de um card guarda `conversa_id`. Se o card ainda não tiver processo e número na ficha, o módulo preenche esses campos no próprio card, sem sobrescrever nada.
- **Calendário:** a aba Prazos do processo só lê `pz_prazos`. Para mudar um prazo, continua sendo no Calendário.
