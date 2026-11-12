# Roteiro para o Claude Code aplicar o módulo de intimações (Braga & Braz)

Você vai acrescentar um módulo novo: captura das publicações do DJEN (CNJ) para as OABs do escritório, tela para conferir e criar as providências no Calendário. O sistema está em produção, com dados reais. Por isso o módulo só **acrescenta**: não renomeia nem apaga nada que já existe. A única mudança em código existente é a lista de "origens" do Calendário (passo 4), e ela precisa ser feita com cuidado.

## Antes de começar

1. **Confira que a sua cópia é a que está no ar.** O código de produção fica na VPS. Se a cópia local estiver atrás, puxe antes de mexer.
2. **Backup do banco.** O arquivo padrão é `sistema_bragabraz.db` (`DATABASE_URL` no `.env`):
   `cp sistema_bragabraz.db sistema_bragabraz.db.bak_$(date +%Y%m%d_%H%M)`
3. **Leia antes de editar.** Os trechos abaixo dizem *onde* entram. Ache o ponto no arquivo real antes de colar.
4. **Ferramentas:** o teste usa SQLAlchemy 2 e aiosqlite, que o sistema já tem no `requirements.txt`.

## Passo 1: copiar os arquivos

Copie o conteúdo de `intimacoes/backend/app/` para dentro de `backend/app/` (sem sobrescrever nada que já existe):

| Arquivo do kit | Destino no sistema |
|---|---|
| `backend/app/intimacoes/` (pasta inteira) | `backend/app/intimacoes/` |
| `backend/app/routers/intimacoes.py` | `backend/app/routers/intimacoes.py` |
| `frontend/src/pages/Intimacoes.jsx` | `frontend/src/pages/Intimacoes.jsx` |
| `teste_intimacoes.py` | `intimacoes/teste_intimacoes.py` (fora de `backend/`, só para teste) |

Não há arquivo com o mesmo nome no sistema: se houver, pare e pergunte.

## Passo 2: configuração

Em `backend/app/config.py`, dentro de `class Settings`, acrescente:

```python
    # ===== Intimacoes (DJEN/CNJ) =====
    INT_OABS: str = ''                       # ex.: 123456/SP;654321/RJ. Vazio = so as cadastradas na tela
    INT_PROVEDOR_ALTERNATIVO: bool = False   # ponto de extensao (provedor pago). Desligado. Nao implementado
```

No `backend/.env`, deixe as OABs **vazias** até o Renato informar as dele:

```
INT_OABS=
# exemplo de formato (NAO e' a OAB do escritorio): INT_OABS=000000/SP
```

A API do DJEN é pública e gratuita. Não há token para configurar.

## Passo 3: registrar no `backend/app/main.py`

1. Em `from .routers.prazos import prazos_router`, acrescente a linha:
   ```python
   from .routers.intimacoes import router as intimacoes_router
   ```
2. Em `app.include_router(prazos_router)` (e vizinhos), acrescente:
   ```python
   app.include_router(intimacoes_router)
   ```
3. Dentro de `lifespan`, logo depois de `await init_db()`, acrescente:
   ```python
   # tabelas do modulo de intimacoes (int_intimacoes, int_capturas, int_oabs). Idempotente.
   try:
       from .intimacoes.schema import garantir_tabelas as _int_tabelas
       async with AsyncSessionLocal() as _db:
           await _int_tabelas(_db)
   except Exception as e:
       print(f'[intimacoes] tabelas nao criadas: {type(e).__name__}: {e}', flush=True)
   ```

Nada precisa de `ALTER TABLE`: as três tabelas são novas. A tabela `pz_prazos` só ganha linhas com `origem = 'intimacao'`.

## Passo 4: Calendário passa a aceitar a origem `intimacao`

Hoje o sistema trata `origem == 'manual'` como "criado aqui, editável". Uma providência criada pela conferência também é do escritório e precisa ser editável, baixável e aparecer no `.ics`. Por isso, `prazos.py` ganha uma constante e cinco checagens trocam para ela.

**4a. `backend/app/routers/prazos.py`.** Logo depois de `TIPOS = (...)`, acrescente:

```python
# origens que o escritorio mantem: manual (criado aqui) e intimacao (conferido a partir de uma intimacao)
ORIGENS_DA_EQUIPE = ('manual', 'intimacao')
```

**4b. Troque estas linhas, uma a uma** (confira que o trecho existe antes de trocar):

| Onde (busca pelo texto) | Antes | Depois |
|---|---|---|
| `'editavel': self.origem == 'manual',` | `self.origem == 'manual'` | `self.origem in ORIGENS_DA_EQUIPE` |
| todas as ocorrências de `if p.origem != 'manual':` (são 5: em `decidir`, `apagar`, `editar`) | `p.origem != 'manual'` | `p.origem not in ORIGENS_DA_EQUIPE` |
| `elif (estado_aprov == 'aprovado' and p.origem == 'manual' and 'tipo' in mudou_material` | `p.origem == 'manual'` | `p.origem in ORIGENS_DA_EQUIPE` |
| `if p.origem == 'manual':` (dentro do `.ics`, por volta da linha 1580) | `p.origem == 'manual'` | `p.origem in ORIGENS_DA_EQUIPE` |

**Não mexa** em `origem='manual'` dentro de `criar` (é a criação manual) nem no `default='manual'` da coluna.

Verificação depois da troca:
```
grep -n "'manual'" backend/app/routers/prazos.py
```
As únicas linhas com `'manual'` devem ser a constante, a criação em `criar`, o `default` da coluna e o comentário do cabeçalho.

**4c. `frontend/src/pages/Calendario.jsx`** (são três trocas de texto; a da elaboração **não** entra):

- Na função `apagar` (por volta da linha 641): `const aviso = p.origem === 'manual'` → `const aviso = ['manual', 'intimacao'].includes(p.origem)`.
- Por volta da linha 964: `{p.origem !== 'manual' && (` → `{!['manual', 'intimacao'].includes(p.origem) && (`.
- Por volta da linha 1057: troque o rótulo de origem por:
  ```jsx
  {p.origem === 'manual' ? 'criado no CRM'
    : p.origem === 'intimacao' ? 'conferido de intimação (DJEN)'
    : p.origem === 'google' ? 'Google Agenda · só você vê' : 'rastreador'}
  ```

**Não troque** a linha 66 (`if (p.origem === 'manual' || ...) return p.data`): para intimação, a elaboração deve vir do cálculo do backend a partir da data fatal.

## Passo 5: tela, menu e permissões

**5a. `frontend/src/modules.js`.** Dentro de `MODULOS`, depois da entrada `aprovar-prazos`, acrescente:

```js
  // Intimações do DJEN (CNJ): conferir e criar as providências no Calendário.
  { id: 'intimacoes', nome: 'Intimações', desc: 'Publicações do DJEN das OABs do escritório: conferir e virar prazo no Calendário.', ico: '', rota: '/intimacoes', acesso: ['advogado'], pronto: true },
```
Quem acessa: administrador e advogado (igual ao Calendário). Assistente e demais papéis não veem. Para liberar a alguém, use o recorte de abas (`modulos`) como já é feito com o Calendário.

**5b. `frontend/src/App.jsx`.** Acrescente o import com os outros:
```jsx
import Intimacoes from './pages/Intimacoes'
```
E a rota, junto das outras:
```jsx
<Route path="/intimacoes" element={<Protected><ModuloOnly id="intimacoes"><Intimacoes /></ModuloOnly></Protected>} />
```

**5c. `frontend/src/components/Layout.jsx`.** Três mudanças:

1. Em `ICONES`, acrescente:
   ```jsx
   '/intimacoes': <><rect x="4" y="3" width="16" height="18" rx="2" /><line x1="8" y1="8" x2="16" y2="8" /><line x1="8" y1="12" x2="16" y2="12" /><line x1="8" y1="16" x2="13" y2="16" /></>,
   ```
2. Logo depois do bloco de `viab` (selo "Validar viabilidade"), acrescente o selo de novas intimações:
   ```jsx
   // selo do menu "Intimações": novas aguardando conferência (advogado e administrador)
   const [intim, setIntim] = useState(0)
   useEffect(() => {
     if (!['admin', 'advogado'].includes(user?.papel)) return undefined
     let vivo = true
     const buscar = () => api('/api/intimacoes/contagem')
       .then((r) => { if (vivo) setIntim(r.novas || 0) }).catch(() => {})
     buscar()
     const t = setInterval(buscar, 60000)
     window.addEventListener('intimacoes-contagem', buscar)
     return () => { vivo = false; clearInterval(t); window.removeEventListener('intimacoes-contagem', buscar) }
   }, [user?.papel, loc.pathname])
   ```
3. Troque a linha `const selos = { 'aprovar-prazos': aguardam, viabilidade: viab }` por:
   ```jsx
   const selos = { 'aprovar-prazos': aguardam, viabilidade: viab, intimacoes: intim }
   ```

Depois: `cd frontend && npm run build`. Se o build mudar a tela de alguém em produção, siga o processo de deploy do escritório, não suba `dist/` à mão.

## Passo 6: cadastrar as OABs (decisão do Renato)

Só depois que o Renato informar a OAB dele (número e UF). Duas formas, use uma:

- pela tela **Intimações > OABs monitoradas** (só administrador), ou
- no `.env`: `INT_OABS=NUMERO/UF` (vários separados por `;`).

Não grave a OAB em código nem em arquivo versionado.

## Passo 7: testar antes de qualquer gravação

Local, sem rede e sem banco de produção:
```
cd intimacoes && python -I teste_intimacoes.py
```
Deve terminar com `11 de 11 testes passaram.`

Depois, com o banco de desenvolvimento ou uma cópia do banco, dentro de `backend/`:

1. **Simulação (não grava nada):**
   `python -m app.intimacoes.captura --simular`
   Mostra por OAB: resultado, quantas chegaram, quantas seriam novas e uma prévia (número, tipo do ato, prazo, fatal sugerida). Nenhuma linha é gravada, nem em `int_capturas`.
2. **Captura de verdade, uma vez:** `python -m app.intimacoes.captura`
   Se der `incompleta` numa OAB, não é erro de código: a API estava ocupada. Rode de novo depois.
3. **Rode de novo a mesma captura:** deve dar "novas 0". Se duplicar, pare e me avise.
4. Na tela: abra uma intimação, confira, crie uma providência de teste, veja no Calendário, baixe e exclua. Depois apague o item de teste (pelo Calendário, como admin) ou deixe anotado.

Conferir a tela no celular (largura de 375 px): lista, perfil e conferência.

## Passo 8: cron na VPS

A VPS roda em **UTC**. Brasília é UTC-3. Para capturar de 2 em 2 horas, em dias úteis, das 8h às 20h de Brasília (11h às 23h UTC):

```
0 11-23/2 * * 1-5 cd /opt/bragabraz/backend && flock -n /tmp/intimacoes.lock /opt/bragabraz/venv/bin/python -m app.intimacoes.captura >> /var/log/intimacoes.log 2>&1
```

Ajuste `/opt/bragabraz` ao caminho real. `flock -n` impede duas rodadas ao mesmo tempo. O código de saída é 2 quando alguma OAB ficou incompleta, então dá para alertar por e-mail se quiser.

Esse cron roda sozinho na VPS. Não depende de nenhum computador ligado.

## Passo 9: conferir o básico e publicar

1. `python -m py_compile` nos arquivos alterados e no `backend/app/intimacoes/*.py`.
2. Suba o backend local e confira: `GET /health` responde, `GET /api/intimacoes/contagem` responde 401 sem token e com token responde um objeto com a chave `novas`.
3. O Calendário ainda abre, cria e baixa prazo manual, e a Aprovação de prazos continua funcionando.
4. Deploy pelo processo do escritório (`deploy/deploy.py`).

## Desfazer

Se precisar voltar atrás (faça backup antes):
1. Tire o `include_router` e o bloco do `lifespan` do `main.py`; tire a rota, o import e o item de menu do front.
2. Os itens criados pela conferência ficam em `pz_prazos` com `origem='intimacao'`. Se quiser removê-los:
   ```sql
   DELETE FROM pz_historico WHERE prazo_id IN (SELECT id FROM pz_prazos WHERE origem = 'intimacao');
   DELETE FROM pz_prazos WHERE origem = 'intimacao';
   ```
   Só faça isso com a confirmação do Renato.
3. Tabelas próprias: `DROP TABLE int_intimacoes; DROP TABLE int_capturas; DROP TABLE int_oabs;`. Isso apaga o histórico de capturas e as intimações ainda não conferidas.
4. Retire a linha do cron.
5. Reverter a troca de `'manual'` do passo 4 é seguro depois que não houver linhas `intimacao`. Antes, deixe como está.

## Decisões que o Renato precisa tomar (não mude sozinho)

- **Feriados.** A data fatal sugerida desconta sábados, domingos e feriados nacionais (incluindo Sexta-feira Santa e 20/11). O cálculo de elaboração do Calendário (`data_elaboracao`) desconta só sábado e domingo. Os dois podem divergir numa semana com feriado. Confirme qual regra vale.
- **Carnaval e Corpus Christi** contam como dia útil (é o lado seguro: a data sugerida fica igual ou mais cedo). Se a equipe preferir outra regra, mude em `prazos_uteis.py`, `FERIADOS_FIXOS` e `feriados_nacionais`.
- **Recesso forense (20/12 a 20/01).** Não é descontado. O sistema só alerta quando o prazo atravessa o recesso. Se quiser que seja descontado, é uma regra nova a implementar e a validar.
- **Prazo em dobro** (Fazenda, Defensoria, MP, litisconsortes). Não é calculado; a tela alerta.
- **Classificador.** É por palavras-chave, com o prazo do CPC para cada ato. A equipe jurídica deve revisar o catálogo em `classificador.py` antes do uso. Tudo o que ele sugere aparece marcado como sugestão e é conferido por uma pessoa.
- **Aprovação.** Prazo e audiência criados por quem não é administrador ficam pendentes (regra que já existe). Quer manter assim?
- **Quem trata.** Padrão: administrador e advogado. Assistente fica de fora. Confirme.
- **Processos.** A intimação liga a um processo pelo número quando o módulo de processos existir: `processos_nucleo.achar_processo(db, numero)`, devolvendo objeto com `.id` ou dict com `'id'`. Se a assinatura for outra, ajuste `processo_id_para` em `intimacoes/servico.py`. Sem o módulo, funciona só com o número.
- **Provedor alternativo** (`INT_PROVEDOR_ALTERNATIVO`): ponto de extensão, não implementado. Só se o Renato tiver uma fonte paga própria.

## Quando terminar

Liste para quem pediu: o que foi aplicado, o que ficou pendente e por quê, o resultado do `teste_intimacoes.py`, a primeira captura real (resultado por OAB) e cada decisão acima que ainda esteja em aberto.
