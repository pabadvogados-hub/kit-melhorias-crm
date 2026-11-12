import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { AREAS_NEGOCIO } from '../areas'
import ProcessoFicha from './ProcessoFicha'
import ProcessosClientes from './ProcessosClientes'
import { nomeCurto, baixarCSV, mensagemErro } from './processosUtil'
import './processos.css'

// Modulo Processos: quadro por fase, lista, clientes e ficha do processo.
// Regras de acesso ficam no backend. Aqui so se esconde o que o backend nega.

const ABAS = [
  { id: 'quadro', nome: 'Quadro' },
  { id: 'lista', nome: 'Lista' },
  { id: 'clientes', nome: 'Clientes' },
]

export default function Processos() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const [aba, setAba] = useState('quadro')
  const [fases, setFases] = useState([])
  const [itens, setItens] = useState([])
  const [responsaveis, setResponsaveis] = useState([])
  const [filtros, setFiltros] = useState({ q: '', area: '', responsavel: '', status: 'ativo' })
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [novo, setNovo] = useState(null)   // null fechado | { conversaId } | {}
  const [arrastando, setArrastando] = useState(null)
  const [sobre, setSobre] = useState('')   // fase sob o cursor no arrasto
  const idAberto = params.get('processo') ? Number(params.get('processo')) : null

  function abrir(id) {
    const p = new URLSearchParams(params)
    p.set('processo', String(id))
    setParams(p, { replace: true })
  }
  function fechar() {
    const p = new URLSearchParams(params)
    p.delete('processo')
    setParams(p, { replace: true })
  }

  async function carregarFases() {
    try { setFases((await api('/api/processos/fases')).items) } catch (e) { setErro(mensagemErro(e)) }
  }
  async function carregarResponsaveis() {
    try { setResponsaveis((await api('/api/processos/responsaveis')).items) } catch { /* sem lista: campo fica vazio */ }
  }
  async function carregarItens() {
    setErro('')
    const qs = new URLSearchParams()
    Object.entries(filtros).forEach(([k, v]) => { if (v) qs.set(k, v) })
    try {
      const r = await api(`/api/processos?${qs.toString()}`)
      setItens(r.items)
    } catch (e) {
      setErro(mensagemErro(e))
    } finally {
      setCarregando(false)
    }
  }

  useEffect(() => { carregarFases(); carregarResponsaveis() }, [])
  // filtro de texto espera a pessoa parar de digitar
  useEffect(() => {
    const t = setTimeout(carregarItens, filtros.q ? 300 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtros])

  // link do CRM: /processos?conversa=ID abre o formulario ja com os dados do card
  useEffect(() => {
    const c = params.get('conversa')
    if (c) setNovo({ conversaId: Number(c) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const porFase = useMemo(() => {
    const m = {}
    itens.forEach((x) => { (m[x.fase] = m[x.fase] || []).push(x) })
    return m
  }, [itens])

  async function mover(processo, nomeFase) {
    if (processo.fase === nomeFase) return
    const antes = itens
    setItens(itens.map((x) => (x.id === processo.id ? { ...x, fase: nomeFase, dias_na_fase: 0 } : x)))
    try {
      await api(`/api/processos/${processo.id}/mover`, { method: 'POST', body: { fase: nomeFase } })
    } catch (e) {
      setItens(antes)
      setErro(mensagemErro(e))
    }
  }

  function exportarCSV() {
    baixarCSV('processos.csv',
      ['Número', 'Cliente', 'Área', 'Fase', 'Responsável', 'Pasta', 'Dias na fase', 'Status', 'Comarca', 'Vara', 'Tribunal', 'Parte contrária', 'Valor da causa'],
      itens.map((x) => [x.numero, x.cliente_nome, x.area, x.fase, x.responsavel_email, x.pasta,
        x.dias_na_fase, x.status === 'ativo' ? 'Ativo' : 'Encerrado', x.comarca, x.vara, x.tribunal,
        x.parte_contraria, x.valor_causa ? String(x.valor_causa).replace('.', ',') : '']))
  }

  const temFiltro = filtros.q || filtros.area || filtros.responsavel || filtros.status !== 'ativo'

  return (
    <div className="pr-pagina">
      <div className="pr-barra">
        <div className="pr-abas-topo" role="tablist">
          {ABAS.map((a) => (
            <button key={a.id} role="tab" aria-selected={aba === a.id}
              className={`pr-aba-topo ${aba === a.id ? 'on' : ''}`} onClick={() => setAba(a.id)}>{a.nome}</button>
          ))}
        </div>
        {aba !== 'clientes' && (
          <div className="pr-filtros">
            <input placeholder="Buscar: número, cliente, pasta, parte" value={filtros.q}
              onChange={(e) => setFiltros({ ...filtros, q: e.target.value })} aria-label="Buscar" />
            <select value={filtros.area} onChange={(e) => setFiltros({ ...filtros, area: e.target.value })} aria-label="Área">
              <option value="">Todas as áreas</option>
              {AREAS_NEGOCIO.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
            <select value={filtros.responsavel} onChange={(e) => setFiltros({ ...filtros, responsavel: e.target.value })} aria-label="Responsável">
              <option value="">Todos os responsáveis</option>
              {responsaveis.map((r) => <option key={r.email} value={r.email}>{r.nome || r.email}</option>)}
            </select>
            <select value={filtros.status} onChange={(e) => setFiltros({ ...filtros, status: e.target.value })} aria-label="Status">
              <option value="ativo">Ativos</option>
              <option value="encerrado">Encerrados</option>
              <option value="todos">Todos</option>
            </select>
            {temFiltro && (
              <button className="btn btn-ghost btn-sm" onClick={() => setFiltros({ q: '', area: '', responsavel: '', status: 'ativo' })}>Limpar</button>
            )}
            <button className="btn btn-gold btn-sm" onClick={() => setNovo({})}>+ Processo</button>
          </div>
        )}
      </div>

      {erro && <div className="alert alert-error">{erro}</div>}

      {aba === 'quadro' && (
        <>
          <p className="muted pr-pequeno">
            {carregando ? 'Carregando…' : `${itens.length} processo(s) ${filtros.status === 'encerrado' ? 'encerrado(s)' : 'ativo(s)'}.`}
            {' '}Arraste o cartão para outra fase. No celular, abra o processo e use "Mover".
          </p>
          <div className="pr-board" role="list">
            {fases.map((f) => {
              const lista = porFase[f.nome] || []
              return (
                <section key={f.id} role="listitem"
                  className={`pr-coluna ${sobre === f.nome ? 'sobre' : ''}`}
                  onDragOver={(e) => { if (arrastando) { e.preventDefault(); setSobre(f.nome) } }}
                  onDragLeave={() => setSobre('')}
                  onDrop={(e) => {
                    e.preventDefault(); setSobre('')
                    if (arrastando) mover(arrastando, f.nome)
                    setArrastando(null)
                  }}>
                  <header className="pr-coluna-topo">
                    <div className="pr-coluna-grupo">{f.grupo}</div>
                    <div className="pr-coluna-nome">{f.nome} <span className="pr-contagem">{lista.length}</span></div>
                  </header>
                  <div className="pr-coluna-corpo">
                    {lista.map((x) => (
                      <article key={x.id} className="pr-cartao" draggable
                        onDragStart={() => setArrastando(x)} onDragEnd={() => { setArrastando(null); setSobre('') }}
                        onClick={() => abrir(x.id)} tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter') abrir(x.id) }}>
                        <div className="pr-cartao-num">{x.numero || 'Sem número'}</div>
                        <div className="pr-cartao-cli">{x.cliente_nome || 'Sem cliente'}</div>
                        <div className="pr-cartao-rodape">
                          {x.area && <span className="pr-chip">{x.area}</span>}
                          <span className="muted">{nomeCurto(x.responsavel_email)} · {x.dias_na_fase}d</span>
                        </div>
                      </article>
                    ))}
                    {!lista.length && !carregando && <div className="pr-vazio">Nenhum processo</div>}
                  </div>
                </section>
              )
            })}
          </div>
        </>
      )}

      {aba === 'lista' && (
        <div className="pr-lista-wrap">
          <div className="pr-lista-topo">
            <span className="muted pr-pequeno">{itens.length} resultado(s)</span>
            <button className="btn btn-ghost btn-sm" onClick={exportarCSV} disabled={!itens.length}>Exportar CSV</button>
          </div>
          <div className="pr-tabela-scroll">
            <table className="pr-tabela">
              <thead>
                <tr>
                  <th>Número</th><th>Cliente</th><th>Área</th><th>Fase</th>
                  <th>Responsável</th><th>Pasta</th><th>Dias</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((x) => (
                  <tr key={x.id} onClick={() => abrir(x.id)} className="pr-linha-clicavel">
                    <td>{x.numero || <span className="muted">Sem número</span>}</td>
                    <td>{x.cliente_nome || <span className="muted">—</span>}</td>
                    <td>{x.area || <span className="muted">—</span>}</td>
                    <td>{x.fase}</td>
                    <td>{nomeCurto(x.responsavel_email)}</td>
                    <td>{x.pasta || <span className="muted">—</span>}</td>
                    <td>{x.dias_na_fase}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!itens.length && !carregando && <p className="muted pr-vazio">Nenhum processo com este filtro.</p>}
          </div>
        </div>
      )}

      {aba === 'clientes' && (
        <ProcessosClientes onAbrirProcesso={abrir} />
      )}

      {idAberto && (
        <ProcessoFicha id={idAberto} fases={fases} responsaveis={responsaveis}
          onFechar={fechar} onMudou={carregarItens} />
      )}

      {novo && (
        <NovoProcesso
          conversaId={novo.conversaId}
          fases={fases}
          responsaveis={responsaveis}
          emailPadrao={user?.email || ''}
          onFechar={() => {
            setNovo(null)
            if (params.get('conversa')) { const p = new URLSearchParams(params); p.delete('conversa'); setParams(p, { replace: true }) }
          }}
          onCriado={(ficha) => {
            setNovo(null)
            carregarItens()
            if (params.get('conversa')) { const p = new URLSearchParams(params); p.delete('conversa'); p.set('processo', String(ficha.processo.id)); setParams(p, { replace: true }) }
            else abrir(ficha.processo.id)
          }}
        />
      )}
    </div>
  )
}

// Formulario de novo processo. Com conversaId, vem do CRM: o backend diz se o card pode virar
// processo e ja traz cliente, area e responsavel sugeridos.
function NovoProcesso({ conversaId, fases, responsaveis, emailPadrao, onFechar, onCriado }) {
  const [f, setF] = useState({
    numero: '', cliente_nome: '', area: '', fase: 'A classificar', pasta: '', comarca: '', vara: '',
    tribunal: '', parte_contraria: '', valor_causa: '', responsavel_email: emailPadrao, observacao: '',
  })
  const [previa, setPrevia] = useState(conversaId ? null : { elegivel: true })
  const [erro, setErro] = useState('')
  const [dica, setDica] = useState('')
  const [salvando, setSalvando] = useState(false)
  const pastaUsada = useRef('')

  useEffect(() => {
    if (!conversaId) return
    api(`/api/processos/conversa/${conversaId}/elegivel`).then((r) => {
      setPrevia(r)
      if (r.sugestao) {
        setF((x) => ({ ...x, cliente_nome: r.sugestao.cliente_nome || '', area: r.sugestao.area || '',
          responsavel_email: r.sugestao.responsavel_email || emailPadrao }))
      }
    }).catch((e) => { setErro(mensagemErro(e)); setPrevia({ elegivel: false, motivo: '' }) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversaId])

  // pasta preenche processo e cliente (mesma regra do backend, aqui so para mostrar)
  async function aoSairDaPasta() {
    const pasta = f.pasta.trim()
    if (!pasta || pasta === pastaUsada.current) return
    pastaUsada.current = pasta
    try {
      const r = await api(`/api/processos/pasta?pasta=${encodeURIComponent(pasta)}`)
      if (!r.pasta) { setDica('Pasta não está no índice da REDE. Confira o número.'); return }
      const unico = r.processos.length === 1
      setDica(`Pasta encontrada: ${r.cliente || 'sem nome'}${r.processos.length ? ` · ${r.processos.length} processo(s)` : ''}`)
      setF((x) => ({
        ...x,
        cliente_nome: x.cliente_nome || r.cliente || '',
        numero: x.numero || (unico ? r.processos[0] : ''),
      }))
    } catch { setDica('') }
  }

  async function salvar(ev) {
    ev.preventDefault()
    setErro(''); setSalvando(true)
    const corpo = { ...f, valor_causa: Number(f.valor_causa) || 0 }
    try {
      const r = conversaId
        ? await api(`/api/processos/conversa/${conversaId}`, { method: 'POST', body: corpo })
        : await api('/api/processos', { method: 'POST', body: corpo })
      onCriado(r)
    } catch (e) {
      setErro(mensagemErro(e))
    } finally {
      setSalvando(false)
    }
  }

  const bloqueado = conversaId && previa && !previa.elegivel

  return (
    <div className="pr-drawer-fundo" onClick={onFechar}>
      <div className="pr-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Novo processo">
        <div className="pr-ficha-topo">
          <div className="pr-ficha-titulo">Novo processo</div>
          <button className="pr-fechar" onClick={onFechar} aria-label="Fechar">Fechar</button>
        </div>

        {conversaId && !previa && <p className="muted">Carregando dados da conversa…</p>}
        {bloqueado && (
          <div className="alert alert-error">
            {previa.motivo || 'Este contato não pode virar processo agora.'}
            {previa.processo_existente && (
              <div style={{ marginTop: 8 }}>
                <a href={`/processos?processo=${previa.processo_existente}`}>Abrir o processo existente</a>
              </div>
            )}
          </div>
        )}
        {erro && <div className="alert alert-error">{erro}</div>}

        {(!conversaId || (previa && previa.elegivel)) && (
          <form onSubmit={salvar} className="pr-form">
            {conversaId && <p className="muted pr-pequeno">Criado a partir de uma conversa do CRM. Confira os dados antes de salvar.</p>}
            <label className="pr-campo"><span>Número CNJ (opcional)</span>
              <input value={f.numero} onChange={(e) => setF({ ...f, numero: e.target.value })} placeholder="NNNNNNN-DD.AAAA.J.TR.OOOO" />
            </label>
            <label className="pr-campo"><span>Pasta na REDE (ex.: 250 ou 383/K74)</span>
              <input value={f.pasta} onChange={(e) => setF({ ...f, pasta: e.target.value })} onBlur={aoSairDaPasta} />
            </label>
            {dica && <p className="muted pr-pequeno">{dica}</p>}
            <label className="pr-campo"><span>Cliente</span>
              <input value={f.cliente_nome} onChange={(e) => setF({ ...f, cliente_nome: e.target.value })} required />
              <small className="muted pr-pequeno">Se o nome ainda não estiver em Clientes, ele é cadastrado agora.</small>
            </label>
            <label className="pr-campo"><span>Área</span>
              <select value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })}>
                <option value="">Sem área</option>
                {AREAS_NEGOCIO.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </label>
            <label className="pr-campo"><span>Fase</span>
              <select value={f.fase} onChange={(e) => setF({ ...f, fase: e.target.value })}>
                {fases.map((x) => <option key={x.id} value={x.nome}>{x.nome}</option>)}
              </select>
            </label>
            <label className="pr-campo"><span>Responsável</span>
              <select value={f.responsavel_email} onChange={(e) => setF({ ...f, responsavel_email: e.target.value })}>
                <option value="">Sem responsável</option>
                {responsaveis.map((r) => <option key={r.email} value={r.email}>{r.nome || r.email}</option>)}
              </select>
            </label>
            <label className="pr-campo"><span>Parte contrária</span>
              <input value={f.parte_contraria} onChange={(e) => setF({ ...f, parte_contraria: e.target.value })} />
            </label>
            <div className="pr-linha-2">
              <label className="pr-campo"><span>Comarca</span>
                <input value={f.comarca} onChange={(e) => setF({ ...f, comarca: e.target.value })} />
              </label>
              <label className="pr-campo"><span>Vara</span>
                <input value={f.vara} onChange={(e) => setF({ ...f, vara: e.target.value })} />
              </label>
            </div>
            <div className="pr-linha-2">
              <label className="pr-campo"><span>Tribunal</span>
                <input value={f.tribunal} onChange={(e) => setF({ ...f, tribunal: e.target.value })} />
              </label>
              <label className="pr-campo"><span>Valor da causa (R$)</span>
                <input type="number" min="0" step="0.01" value={f.valor_causa} onChange={(e) => setF({ ...f, valor_causa: e.target.value })} />
              </label>
            </div>
            <label className="pr-campo"><span>Observação</span>
              <textarea rows={3} value={f.observacao} onChange={(e) => setF({ ...f, observacao: e.target.value })} />
            </label>
            <div className="pr-acoes">
              <button type="submit" className="btn btn-gold" disabled={salvando || !f.cliente_nome.trim()}>
                {salvando ? 'Salvando…' : 'Criar processo'}
              </button>
              <button type="button" className="btn btn-ghost" onClick={onFechar}>Cancelar</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

