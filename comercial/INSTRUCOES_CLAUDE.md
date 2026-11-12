# Roteiro para o Claude Code aplicar o Painel Comercial no sistema Braga & Braz

Você vai acrescentar um painel comercial ao vivo: leads, contratos assinados, mesa de cada pessoa, funil por coluna, perdas e parados. Ele só **lê** o CRM. Não cria tabela, não altera coluna, não grava nada no banco e não manda WhatsApp. Para desfazer, basta tirar as linhas que você acrescentar (ver o fim).

## Antes de começar

1. **Confira se você está na versão que está no ar.** Se a cópia local estiver atrás da VPS, puxe antes de mexer.
2. **Leia `routers/relatorios.py` (Análise de leads) e o `index.css`.** O painel usa a mesma regra de lead da Análise e o mesmo visual. Não duplique a Análise: ela continua existindo e continua sendo a fonte do relatório de 15 dias.
3. **Confirme os nomes dos quadros.** Rode `SELECT id, nome FROM wa_pipelines;` e anote os nomes exatos dos quadros que ficam fora do funil (clientes e contatos gerais).

## Arquivos do kit e para onde vão

| Arquivo do kit | Destino no sistema |
|---|---|
| `comercial/backend/comercial.py` | `backend/app/routers/comercial.py` |
| `comercial/backend/comercial_metas.json` | `backend/comercial_metas.json` (ao lado de `app/`, não dentro) |
| `comercial/frontend/Comercial.jsx` | `frontend/src/pages/Comercial.jsx` |

## Regras durante o trabalho

- **Só acrescente.** Não apague nem renomeie rota, campo ou coluna. O kit não altera nenhum arquivo existente além dos quatro pontos abaixo (`main.py`, `modules.js`, `App.jsx`, `Layout.jsx`).
- **Nomes que precisam bater com o banco estão marcados com `AJUSTAR`:** os nomes dos quadros em `comercial_metas.json` e as expressões de coluna e de nota de assinatura no topo de `comercial.py`.
- **Não ligue fluxo nem envio por causa deste painel.** Ele é só tela.
- **Nada de credencial no repositório.** O painel não usa chave nova.

## Passo a passo

### 1. Copiar os três arquivos
Copie os arquivos da tabela acima. Não crie pasta nova além das que já existem.

### 2. Registrar o router em `backend/app/main.py`
Junto dos outros imports de router:

```python
from .routers.comercial import router as comercial_router
```

E junto dos outros `app.include_router(...)`:

```python
app.include_router(comercial_router)
```

### 3. Menu e rotas no frontend

**`frontend/src/modules.js`**: dentro da lista `MODULOS`, logo depois da linha do `relatorios`:

```js
  { id: 'comercial', nome: 'Comercial', desc: 'Painel ao vivo: leads, contratos assinados, mesa de cada pessoa e funil.', ico: '', rota: '/comercial', acesso: 'admin', pronto: true },
  { id: 'minha-mesa', nome: 'Minha mesa', desc: 'Seus leads, respostas, contratos e o que está parado com você.', ico: '', rota: '/minha-mesa', acesso: 'todos', pronto: true },
```

**`frontend/src/App.jsx`**: junto dos outros imports de página:

```js
import Comercial from './pages/Comercial'
```

E dentro de `<Routes>`, junto das outras rotas:

```jsx
      <Route path="/comercial" element={<Protected><AdminOnly><Comercial /></AdminOnly></Protected>} />
      <Route path="/minha-mesa" element={<Protected><Comercial modo="mesa" /></Protected>} />
```

**`frontend/src/components/Layout.jsx`**: no objeto `ICONES`, acrescente duas entradas (qualquer SVG de linha serve; este é o padrão do menu):

```jsx
  '/comercial': <><path d="M3 3v18h18" /><path d="M7 15l4-4 3 3 5-6" /></>,
  '/minha-mesa': <><circle cx="12" cy="8" r="4" /><path d="M4 21v-1a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v1" /></>,
```

O menu mostra "Comercial" só para administrador. "Minha mesa" aparece para todos, e cada pessoa vê só a própria mesa (o backend garante isso; a tela não é a barreira).

### 4. Metas e premissas em `backend/comercial_metas.json`
Preencha só o que o escritório decidiu. Tudo em branco fica de fora das contas.

- `metas_mensais`: por mês (`"AAAA-MM"`), a meta de contratos do time (`fechados`) e, se quiser, por pessoa (`por_pessoa_fechados`, com o e-mail do usuário).
- `ticket_medio_por_area`: valor **estimado** por quadro, com o nome exato do quadro. Sem isto, a receita não aparece. O CRM não grava valor de contrato.
- `comissao_fixa_por_fechamento`: `ativa` começa `false`. Só ligue se o escritório quiser ver a comissão estimada; `valor` é um número fixo por contrato assinado.
- `quadros_fora_do_funil`: nomes exatos dos quadros que não são funil de venda (passo 0).
- `parado_dias_padrao`: quantos dias sem mudar de coluna contam como parado. Padrão 7.
- `fechado_conta_etapa`: `false` (padrão) conta como fechado só o contrato **assinado**, que é a regra que a Análise de leads usa. `true` soma também quem está em elaboração ou assinatura de contrato sem assinatura confirmada. **Decisão do Renato.**
- `feriados`: datas `"AAAA-MM-DD"` que não contam como dia útil no ritmo da meta.
- `marca_ligacao`: vazio por padrão. Veja a seção de ligações no `README.md` antes de preencher.

Depois de salvar, a tela usa o arquivo novo na próxima consulta. Não precisa reiniciar o backend.

### 5. Testar

1. **Compilar:** `python -m py_compile app/routers/comercial.py` na pasta `backend`.
2. **Teste automatizado do kit:** na pasta `comercial/`, com o Python do backend (ele já tem SQLAlchemy com greenlet, aiosqlite e FastAPI). Gere o esquema a partir de uma cópia do banco, sem dados:
   ```
   python -c "import sqlite3; c=sqlite3.connect('file:sistema_bragabraz.db?mode=ro', uri=True); print(';\n'.join(r[0] for r in c.execute('select sql from sqlite_master where sql is not null'))+';')" > schema_crm.sql
   python -I teste_comercial.py --schema schema_crm.sql
   ```
   Tem que terminar com `TODOS OS TESTES PASSARAM`. O teste usa conversas fictícias num banco temporário e não toca no banco de verdade.
3. **Build da tela:** `npm run build` na pasta `frontend`.
4. **Backend local:** `uvicorn app.main:app --reload --port 8010`. Entre como administrador e abra `http://localhost:8010/api/comercial/painel?periodo=mes` com o token do login (não cole o token em arquivo nenhum). Confira que a resposta tem `resumo`, `mesa` e `funil`.
5. **Conferir contra a Análise de leads.** Compare `resumo.leads` do painel (`periodo=15dias`) com `/api/relatorios/leads?dias=15`. Os números **podem diferir um ou dois leads** nas bordas: a Análise de leads usa o dia em UTC, e este painel usa o dia de Brasília (UTC-3). Se a diferença for maior que isso, pare e reporte.
6. **Tela:** abra `/comercial` como administrador e `/minha-mesa` com um usuário comum. Teste um período, toque em um número e confira a lista. Teste no celular (a tela quebra em uma coluna).
7. **Confira que o básico continua de pé:** Chat abre, CRM abre, Análise de leads abre, `/minha-mesa` mostra só a pessoa logada.

### 6. Deploy
Pelo processo do escritório (`deploy/deploy.py`). Antes, confirme que o que vai subir é só o que você acrescentou.

### 7. Desfazer
- Tire as duas linhas `include_router` e o `import` do `main.py`.
- Tire as duas entradas de `modules.js`, a importação, as duas rotas de `App.jsx` e as duas entradas de `ICONES` em `Layout.jsx`.
- Apague `routers/comercial.py`, `comercial_metas.json` e `pages/Comercial.jsx`.

Nada disso mexe no banco, então não há reversão de dados.

## Decisões que precisam ser do Renato

1. **O que conta como fechado:** só assinado (padrão, igual à Análise de leads) ou também quem está na etapa de contrato sem assinatura (`fechado_conta_etapa`).
2. **Meta mensal do time e por pessoa.** Sem meta, o painel mostra o realizado e não projeta ritmo.
3. **Ticket por área.** Estimativa. Se não quiser estimativa, deixe vazio e a receita não aparece.
4. **Comissão fixa por contrato:** ligar ou não, e o valor.
5. **Ligações:** adotar uma nota padrão de ligação (ver `README.md`) ou deixar a seção como "não medido".
6. **Quadros fora do funil e dias para considerar parado.**

## Quando terminar

Liste para quem pediu: o que foi aplicado, o resultado do teste e do build, a diferença observada entre o painel e a Análise de leads (se houver), e as decisões acima que ainda estão em aberto.
