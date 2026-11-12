import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { AREAS_NEGOCIO } from '../areas'
import { PAPEIS_PARTE, ROTULO_EVENTO, fmtData, fmtDia, nomeCurto, valorBR, mensagemErro } from './processosUtil'

// Painel lateral com a ficha de UM processo. Abre pela lista, pelo quadro ou pelo link ?processo=ID.
// Quem so ve o que e seu le tudo, mas os botoes de mudar, editar e partes so aparecem se `pode_mexer`.

const ABAS = [
  { id: 'dados', nome: 'Dados' },
  { id: 'partes', nome: 'Partes' },
  { id: 'prazos', nome: 'Prazos' },
  { id: 'historico', nome: 'Histórico' },
]

export default function ProcessoFicha({ id, fases, responsaveis, onFechar, onMudou }) {
  const irPara = useNavigate()
  const [dados, setDados] = useState(null)
  const [aba, setAba] = useState('dados')
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [editando, setEditando] = useState(false)
  const [form, setForm] = useState({})
  const [faseNova, setFaseNova] = useState('')
  const [prazos, setPrazos] = useState(null)
  const [parte, setParte] = useState({ nome: '', papel: 'PARTE CONTRÁRIA', documento: '' })

  async function carregar() {
    try {
      const r = await api(`/api/processos/${id}`)
      setDados(r)
      setFaseNova(r.processo.fase)
      setErro('')
    } catch (e) {
      setErro(mensagemErro(e))
    }
  }

  useEffect(() => {
    setDados(null); setAba('dados'); setEditando(false); setPrazos(null); setAviso('')
    carregar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => {
    if (aba === 'prazos' && prazos === null) {
      api(`/api/processos/${id}/prazos`).then((r) => setPrazos(r.items)).catch((e) => setErro(mensagemErro(e)))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aba, id])

  // Executa uma acao que devolve a ficha atualizada e avisa a tela de cima.
  async function agir(fn, msgOk = '') {
    setOcupado(true); setErro(''); setAviso('')
    try {
      const r = await fn()
      if (r && r.processo) setDados(r)
      else await carregar()
      if (msgOk) setAviso(msgOk)
      onMudou && onMudou()
      return true
    } catch (e) {
      setErro(mensagemErro(e))
      return false
    } finally {
      setOcupado(false)
    }
  }

  if (erro && !dados) {
    return (
      <Painel onFechar={onFechar}>
        <div className="alert alert-error">{erro}</div>
      </Painel>
    )
  }
  if (!dados) return <Painel onFechar={onFechar}><p className="muted">Carregando…</p></Painel>

  const p = dados.processo
  const c = dados.cliente
  const mexe = dados.pode_mexer

  function abrirEdicao() {
    setForm({
      numero: p.numero || '', cliente_nome: c ? c.nome : '', area: p.area || '', pasta: p.pasta || '',
      comarca: p.comarca || '', vara: p.vara || '', tribunal: p.tribunal || '',
      parte_contraria: p.parte_contraria || '', valor_causa: p.valor_causa || 0,
      responsavel_email: p.responsavel_email || '', observacao: p.observacao || '',
    })
    setEditando(true)
  }

  async function salvarEdicao(ev) {
    ev.preventDefault()
    const ok = await agir(() => api(`/api/processos/${id}`, { method: 'PATCH', body: {
      ...form, valor_causa: Number(form.valor_causa) || 0,
    } }), 'Dados salvos.')
    if (ok) setEditando(false)
  }

  async function encerrar() {
    const motivo = prompt('Encerrar este processo.\n\nComo terminou? (ex.: acordo homologado, sentença, desistência)')
    if (motivo === null) return
    agir(() => api(`/api/processos/${id}/encerrar`, { method: 'POST', body: { motivo } }), 'Processo encerrado.')
  }

  async function reabrir() {
    if (!confirm('Reabrir este processo?')) return
    agir(() => api(`/api/processos/${id}/reabrir`, { method: 'POST' }), 'Processo reaberto.')
  }

  async function mudarFase() {
    if (faseNova === p.fase) return
    agir(() => api(`/api/processos/${id}/mover`, { method: 'POST', body: { fase: faseNova } }), 'Fase atualizada.')
  }

  async function incluirParte(ev) {
    ev.preventDefault()
    if (!parte.nome.trim()) return
    const ok = await agir(() => api(`/api/processos/${id}/partes`, { method: 'POST', body: parte }), 'Parte incluída.')
    if (ok) setParte({ nome: '', papel: 'PARTE CONTRÁRIA', documento: '' })
  }

  async function removerParte(pid) {
    if (!confirm('Remover esta parte do processo? Fica registrado no histórico.')) return
    agir(() => api(`/api/processos/${id}/partes/${pid}`, { method: 'DELETE' }), 'Parte removida.')
  }

  return (
    <Painel onFechar={onFechar}>
      <div className="pr-ficha-topo">
        <div>
          <div className="pr-ficha-titulo">{p.numero || 'Sem número de processo'}</div>
          <div className="muted pr-ficha-sub">
            {c ? c.nome : 'Sem cliente vinculado'}{p.pasta ? ` · pasta ${p.pasta}` : ''}
          </div>
        </div>
        <span className={`pill ${p.status === 'ativo' ? 'running' : 'pending'}`}>
          {p.status === 'ativo' ? 'Ativo' : 'Encerrado'}
        </span>
      </div>

      {erro && <div className="alert alert-error" style={{ marginTop: 12 }}>{erro}</div>}
      {aviso && <div className="alert alert-ok" style={{ marginTop: 12 }}>{aviso}</div>}

      <div className="pr-abas" role="tablist">
        {ABAS.map((a) => (
          <button key={a.id} role="tab" aria-selected={aba === a.id}
            className={`pr-aba ${aba === a.id ? 'on' : ''}`} onClick={() => setAba(a.id)}>{a.nome}</button>
        ))}
      </div>

      {aba === 'dados' && (
        <div className="pr-secao">
          <div className="pr-fase-box">
            <div className="muted pr-pequeno">Fase atual · {dados.processo.dias_na_fase} dia(s) nela</div>
            <div className="pr-fase-atual">{p.fase}</div>
            {mexe && p.status === 'ativo' && (
              <div className="pr-linha">
                <select value={faseNova} onChange={(e) => setFaseNova(e.target.value)} disabled={ocupado}>
                  {fases.map((f) => <option key={f.id} value={f.nome}>{f.nome}</option>)}
                </select>
                <button className="btn btn-gold btn-sm" onClick={mudarFase} disabled={ocupado || faseNova === p.fase}>
                  Mover
                </button>
              </div>
            )}
          </div>

          {!editando && (
            <dl className="pr-dl">
              <dt>Área</dt><dd>{p.area || <span className="muted">Não definida</span>}</dd>
              <dt>Responsável</dt><dd>{p.responsavel_email ? nomeCurto(p.responsavel_email) : <span className="muted">Sem responsável</span>}</dd>
              <dt>Comarca / vara</dt><dd>{[p.comarca, p.vara].filter(Boolean).join(' · ') || <span className="muted">—</span>}</dd>
              <dt>Tribunal</dt><dd>{p.tribunal || <span className="muted">—</span>}</dd>
              <dt>Parte contrária</dt><dd>{p.parte_contraria || <span className="muted">—</span>}</dd>
              <dt>Valor da causa</dt><dd>{p.valor_causa ? valorBR(p.valor_causa) : <span className="muted">—</span>}</dd>
              <dt>Pasta</dt><dd>{p.pasta || <span className="muted">—</span>}</dd>
              <dt>Aberto em</dt><dd>{fmtData(p.criado_em)} {p.criado_por ? `por ${nomeCurto(p.criado_por)}` : ''}</dd>
              {p.observacao && (<><dt>Observação</dt><dd className="pr-quebra">{p.observacao}</dd></>)}
            </dl>
          )}

          {!editando && dados.pasta_indice && (
            <div className="pr-caixa">
              <div className="pr-caixa-titulo">Pasta na REDE</div>
              <div>{dados.pasta_indice.cliente || 'Sem nome'}</div>
              <div className="muted pr-pequeno">
                {dados.pasta_indice.processos.length
                  ? `Processos na pasta: ${dados.pasta_indice.processos.join(' · ')}`
                  : 'A pasta não tem número de processo registrado.'}
              </div>
            </div>
          )}
          {!editando && p.pasta && !dados.pasta_indice && (
            <div className="pr-caixa">
              <div className="pr-caixa-titulo">Pasta na REDE</div>
              <div className="muted pr-pequeno">Esta pasta não está no índice da REDE. Verifique o número.</div>
            </div>
          )}

          {dados.conversa && (
            <div className="pr-caixa">
              <div className="pr-caixa-titulo">Veio do CRM</div>
              <div>{dados.conversa.nome || dados.conversa.telefone}</div>
              <button className="btn btn-ghost btn-sm" style={{ marginTop: 8 }}
                onClick={() => irPara(`/chat?conversa=${dados.conversa.id}`)}>Abrir a conversa</button>
            </div>
          )}

          {!editando && mexe && (
            <div className="pr-acoes">
              <button className="btn btn-ghost btn-sm" onClick={abrirEdicao} disabled={ocupado}>Editar dados</button>
              {p.status === 'ativo'
                ? <button className="btn btn-ghost btn-sm" onClick={encerrar} disabled={ocupado}>Encerrar processo</button>
                : <button className="btn btn-ghost btn-sm" onClick={reabrir} disabled={ocupado}>Reabrir processo</button>}
            </div>
          )}

          {editando && (
            <form onSubmit={salvarEdicao} className="pr-form">
              <Campo rotulo="Número CNJ (20 dígitos)">
                <input value={form.numero} onChange={(e) => setForm({ ...form, numero: e.target.value })} placeholder="NNNNNNN-DD.AAAA.J.TR.OOOO" />
              </Campo>
              <Campo rotulo="Cliente">
                <input value={form.cliente_nome} onChange={(e) => setForm({ ...form, cliente_nome: e.target.value })} />
              </Campo>
              <Campo rotulo="Área">
                <select value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })}>
                  <option value="">Sem área</option>
                  {AREAS_NEGOCIO.map((a) => <option key={a} value={a}>{a}</option>)}
                </select>
              </Campo>
              <Campo rotulo="Pasta na REDE">
                <input value={form.pasta} onChange={(e) => setForm({ ...form, pasta: e.target.value })} placeholder="ex.: 250 ou 383/K74" />
              </Campo>
              <Campo rotulo="Comarca">
                <input value={form.comarca} onChange={(e) => setForm({ ...form, comarca: e.target.value })} />
              </Campo>
              <Campo rotulo="Vara">
                <input value={form.vara} onChange={(e) => setForm({ ...form, vara: e.target.value })} />
              </Campo>
              <Campo rotulo="Tribunal">
                <input value={form.tribunal} onChange={(e) => setForm({ ...form, tribunal: e.target.value })} />
              </Campo>
              <Campo rotulo="Parte contrária">
                <input value={form.parte_contraria} onChange={(e) => setForm({ ...form, parte_contraria: e.target.value })} />
              </Campo>
              <Campo rotulo="Valor da causa (R$)">
                <input type="number" min="0" step="0.01" value={form.valor_causa}
                  onChange={(e) => setForm({ ...form, valor_causa: e.target.value })} />
              </Campo>
              <Campo rotulo="Responsável">
                <select value={form.responsavel_email} onChange={(e) => setForm({ ...form, responsavel_email: e.target.value })}>
                  <option value="">Sem responsável</option>
                  {responsaveis.map((r) => <option key={r.email} value={r.email}>{r.nome || r.email}</option>)}
                </select>
              </Campo>
              <Campo rotulo="Observação">
                <textarea rows={3} value={form.observacao} onChange={(e) => setForm({ ...form, observacao: e.target.value })} />
              </Campo>
              <div className="pr-acoes">
                <button type="submit" className="btn btn-gold btn-sm" disabled={ocupado}>Salvar</button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditando(false)}>Cancelar</button>
              </div>
            </form>
          )}
        </div>
      )}

      {aba === 'partes' && (
        <div className="pr-secao">
          {dados.partes.length === 0 && <p className="muted">Nenhuma parte cadastrada.</p>}
          <ul className="pr-lista">
            {dados.partes.map((x) => (
              <li key={x.id}>
                <div>
                  <strong>{x.nome}</strong>
                  <div className="muted pr-pequeno">{x.papel}{x.documento ? ` · ${x.documento}` : ''}</div>
                </div>
                {mexe && <button className="btn btn-ghost btn-sm" onClick={() => removerParte(x.id)} disabled={ocupado}>Remover</button>}
              </li>
            ))}
          </ul>
          {mexe && (
            <form onSubmit={incluirParte} className="pr-form">
              <Campo rotulo="Nome">
                <input value={parte.nome} onChange={(e) => setParte({ ...parte, nome: e.target.value })} />
              </Campo>
              <Campo rotulo="Papel">
                <select value={parte.papel} onChange={(e) => setParte({ ...parte, papel: e.target.value })}>
                  {PAPEIS_PARTE.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
              </Campo>
              <Campo rotulo="CPF ou CNPJ (opcional)">
                <input value={parte.documento} onChange={(e) => setParte({ ...parte, documento: e.target.value })} />
              </Campo>
              <button type="submit" className="btn btn-gold btn-sm" disabled={ocupado || !parte.nome.trim()}>Incluir parte</button>
            </form>
          )}
        </div>
      )}

      {aba === 'prazos' && (
        <div className="pr-secao">
          <p className="muted pr-pequeno">
            Prazos do Calendário ligados a este processo ou a esta pasta. Para alterar, use o Calendário.
          </p>
          {prazos === null && <p className="muted">Carregando…</p>}
          {prazos && prazos.length === 0 && <p className="muted">Nenhum prazo ligado a este processo.</p>}
          <ul className="pr-lista">
            {(prazos || []).map((x) => (
              <li key={x.id}>
                <div>
                  <strong>{x.titulo}</strong>
                  <div className="muted pr-pequeno">
                    {fmtDia(x.data)}{x.hora ? ` ${x.hora}` : ''} · {x.tipo}{x.fatal ? ' · fatal' : ''}
                    {x.responsavel ? ` · ${nomeCurto(x.responsavel)}` : ''}
                  </div>
                </div>
                <span className={`pill ${x.concluido ? 'done' : 'pending'}`}>{x.concluido ? 'Cumprido' : 'Aberto'}</span>
              </li>
            ))}
          </ul>
          <button className="btn btn-ghost btn-sm" onClick={() => irPara('/calendario')}>Abrir Calendário</button>
        </div>
      )}

      {aba === 'historico' && (
        <div className="pr-secao">
          {dados.historico.length === 0 && <p className="muted">Sem registros.</p>}
          <ul className="pr-lista pr-hist">
            {dados.historico.map((h) => (
              <li key={h.id}>
                <div>
                  <strong>{ROTULO_EVENTO[h.evento] || h.evento}</strong>
                  {h.de || h.para ? <span className="muted"> · {h.de || '—'} → {h.para || '—'}</span> : null}
                  {h.detalhe ? <div className="muted pr-pequeno">{h.detalhe}</div> : null}
                  <div className="muted pr-pequeno">{fmtData(h.em)} · {nomeCurto(h.por)}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Painel>
  )
}

function Painel({ children, onFechar }) {
  return (
    <div className="pr-drawer-fundo" onClick={onFechar}>
      <aside className="pr-drawer" onClick={(e) => e.stopPropagation()} aria-label="Ficha do processo">
        <button className="pr-fechar" onClick={onFechar} aria-label="Fechar">Fechar</button>
        {children}
      </aside>
    </div>
  )
}

function Campo({ rotulo, children }) {
  return (
    <label className="pr-campo">
      <span>{rotulo}</span>
      {children}
    </label>
  )
}
