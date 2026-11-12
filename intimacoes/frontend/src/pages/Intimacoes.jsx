import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'

// Intimações do DJEN (CNJ) para as OABs do escritório.
// Fluxo: a captura traz a publicação -> a equipe abre, lê o texto, confere a sugestão do
// classificador e cria as providências no Calendário. Nada vai para o Calendário sem conferência.

const CSS = `
.ibb { color: var(--text, #e8eef9); }
.ibb-top { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.ibb-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.ibb-chip { border: 1px solid var(--border, rgba(255,255,255,.09)); background: transparent; color: var(--muted, #8695ad); border-radius: 999px; padding: 6px 12px; font-size: 13px; cursor: pointer; }
.ibb-chip.on { background: var(--gold, #d5b974); border-color: var(--gold, #d5b974); color: #241b06; font-weight: 700; }
.ibb-filtros { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 8px; margin-bottom: 14px; }
.ibb-in { width: 100%; background: var(--surface-2, #131a3d); border: 1px solid var(--border, rgba(255,255,255,.09)); color: var(--text, #e8eef9); border-radius: 10px; padding: 9px 11px; font-size: 14px; }
.ibb-in:focus { outline: 1px solid var(--gold, #d5b974); }
.ibb-sub { color: var(--muted, #8695ad); font-size: 13px; line-height: 1.45; }
.ibb-resumo { color: var(--muted, #8695ad); font-size: 13px; margin-bottom: 10px; }
.ibb-resumo b { color: var(--gold, #d5b974); }
.ibb-lista { display: flex; flex-direction: column; gap: 8px; }
.ibb-item { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start; width: 100%; text-align: left; background: var(--surface, rgba(19,25,61,.72)); border: 1px solid var(--border, rgba(255,255,255,.09)); border-radius: 14px; padding: 12px 14px; color: inherit; cursor: pointer; font: inherit; }
.ibb-item.nova { border-color: rgba(213,185,116,.45); }
.ibb-item:hover { border-color: var(--gold, #d5b974); }
.ibb-linha { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 4px; }
.ibb-num { font-weight: 700; font-size: 15px; }
.ibb-tag { font-size: 11px; border: 1px solid var(--border, rgba(255,255,255,.09)); border-radius: 6px; padding: 2px 6px; color: var(--muted, #8695ad); }
.ibb-tag.ouro { border-color: rgba(213,185,116,.6); color: var(--gold, #d5b974); }
.ibb-dir { text-align: right; font-size: 13px; white-space: nowrap; }
.ibb-aviso { border: 1px solid rgba(213,185,116,.45); background: rgba(213,185,116,.08); color: var(--gold-2, #e8d29a); border-radius: 10px; padding: 9px 11px; font-size: 13px; line-height: 1.45; margin: 8px 0; }
.ibb-erro { border: 1px solid rgba(248,113,113,.5); background: rgba(248,113,113,.08); color: #fca5a5; border-radius: 10px; padding: 9px 11px; font-size: 13px; margin: 8px 0; }
.ibb-ok { border: 1px solid rgba(52,211,153,.45); background: rgba(52,211,153,.08); color: #6ee7b7; border-radius: 10px; padding: 9px 11px; font-size: 13px; margin: 8px 0; }
.ibb-vazio { color: var(--muted, #8695ad); text-align: center; padding: 34px 10px; border: 1px dashed var(--border, rgba(255,255,255,.09)); border-radius: 14px; }
.ibb-btn { border: 1px solid var(--border, rgba(255,255,255,.09)); background: var(--surface-2, #131a3d); color: var(--text, #e8eef9); border-radius: 10px; padding: 9px 14px; font-size: 14px; cursor: pointer; font-weight: 600; }
.ibb-btn.ouro { background: var(--gold, #d5b974); border-color: var(--gold, #d5b974); color: #241b06; }
.ibb-btn.perigo { border-color: rgba(248,113,113,.5); color: #fca5a5; }
.ibb-btn:disabled { opacity: .5; cursor: default; }
.ibb-btn.peq { padding: 5px 9px; font-size: 12px; }
.ibb-fundo { position: fixed; inset: 0; z-index: 50; background: rgba(5,8,26,.8); display: flex; align-items: center; justify-content: center; padding: 16px; }
.ibb-modal { width: min(920px, 100%); max-height: 92vh; overflow: auto; background: var(--surface-solid, #10163a); border: 1px solid var(--border, rgba(255,255,255,.09)); border-radius: 18px; padding: 18px; box-shadow: var(--shadow-lg, 0 26px 64px rgba(0,0,0,.55)); }
.ibb-modal h2 { font-size: 18px; margin-bottom: 4px; }
.ibb-sec { margin-top: 14px; }
.ibb-sec h3 { font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: var(--gold, #d5b974); margin-bottom: 6px; }
.ibb-texto { white-space: pre-wrap; background: var(--surface-2, #131a3d); border: 1px solid var(--border, rgba(255,255,255,.09)); border-radius: 12px; padding: 12px; font-size: 13.5px; line-height: 1.55; max-height: 340px; overflow: auto; font-family: inherit; }
.ibb-acoes { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; margin-top: 16px; }
.ibb-prov { border: 1px solid var(--border, rgba(255,255,255,.09)); background: var(--surface-2, #131a3d); border-radius: 14px; padding: 12px; margin-bottom: 10px; }
.ibb-prov-topo { display: flex; justify-content: space-between; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.ibb-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.ibb-form .largo { grid-column: 1 / -1; }
.ibb-lbl { display: block; font-size: 12px; color: var(--muted, #8695ad); margin-bottom: 3px; }
.ibb-sugestao { display: inline-block; font-size: 11px; font-weight: 700; color: #241b06; background: var(--gold, #d5b974); border-radius: 6px; padding: 2px 7px; }
.ibb-oabs { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.ibb-oab { border: 1px solid var(--border, rgba(255,255,255,.09)); border-radius: 8px; padding: 4px 8px; font-size: 13px; display: inline-flex; gap: 8px; align-items: center; }
@media (max-width: 720px) {
  .ibb-filtros { grid-template-columns: 1fr; }
  .ibb-item { grid-template-columns: 1fr; }
  .ibb-dir { text-align: left; white-space: normal; }
  .ibb-form { grid-template-columns: 1fr; }
  .ibb-fundo { padding: 0; }
  .ibb-modal { width: 100%; max-height: 100vh; height: 100vh; border-radius: 0; }
  .ibb-btn { width: 100%; }
  .ibb-acoes .ibb-btn { width: auto; flex: 1; }
}
`

const STATUS_OPC = [['nova', 'Novas'], ['conferida', 'Conferidas'], ['descartada', 'Descartadas'], ['todas', 'Todas']]
const STATUS_ROTULO = { nova: 'Nova', conferida: 'Conferida', descartada: 'Descartada' }
const RESULTADO_CAPTURA = {
  ok: 'concluída',
  vazio_confirmado: 'sem intimações no período (três respostas vazias da API)',
  incompleta: 'não concluída: a API não respondeu com dados. A próxima rodada refaz a consulta',
  erro: 'erro na consulta',
}
const TIPOS = [['prazo', 'Prazo fatal'], ['audiencia', 'Audiência'], ['reuniao', 'Reunião'],
  ['providencia', 'Providência'], ['tarefa', 'Tarefa'], ['outro', 'Outro']]
const AVISO_CALCULO = 'A contagem usa só sábados, domingos e feriados nacionais. Feriados locais, suspensões de expediente do tribunal, prazo em dobro e recesso forense (20/12 a 20/01) não entram: confira a data antes de confirmar.'
const AVISO_APROVACAO = 'Prazo e audiência criados por quem não é administrador ficam pendentes e só valem depois da aprovação do administrador. Continuam aparecendo no Calendário enquanto esperam.'

const avisarMenu = () => window.dispatchEvent(new Event('intimacoes-contagem'))

function dataBR(iso) {
  if (!iso) return '—'
  return new Date(iso + 'T12:00:00').toLocaleDateString('pt-BR')
}

function dataHoraBR(txt) {
  if (!txt) return '—'
  // o servidor grava UTC sem fuso: "AAAA-MM-DD HH:MM:SS.ffffff"
  const d = new Date(txt.slice(0, 19).replace(' ', 'T') + 'Z')
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

function itemVazio(processo = '') {
  return { tipo: 'prazo', titulo: '', responsavel: '', data: '', hora: '', fatal: false,
    prazo_dias: '', pasta: '', processo, cliente: '', observacao: '', sugerido: false }
}

export default function Intimacoes() {
  const { user } = useAuth()
  const admin = user?.papel === 'admin'
  const [status, setStatus] = useState('nova')
  const [busca, setBusca] = useState('')
  const [tribunal, setTribunal] = useState('')
  const [de, setDe] = useState('')
  const [ate, setAte] = useState('')
  const [lista, setLista] = useState({ items: [], total: 0 })
  const [cont, setCont] = useState({ novas: 0 })
  const [capturas, setCapturas] = useState([])
  const [aberta, setAberta] = useState(null)
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState('')
  const [avisoCaptura, setAvisoCaptura] = useState('')

  const carregar = useCallback(async () => {
    const qs = new URLSearchParams({ status, por_pagina: '50' })
    if (busca.trim()) qs.set('q', busca.trim())
    if (tribunal.trim()) qs.set('tribunal', tribunal.trim())
    if (de) qs.set('de', de)
    if (ate) qs.set('ate', ate)
    try {
      const [l, c] = await Promise.all([api('/api/intimacoes?' + qs.toString()), api('/api/intimacoes/contagem')])
      setLista(l)
      setCont(c)
      setErro('')
    } catch (e) {
      setErro(e.message)
    } finally {
      setCarregando(false)
    }
  }, [status, busca, tribunal, de, ate])

  const carregarCapturas = useCallback(() => {
    if (!admin) return
    api('/api/intimacoes/capturas').then(setCapturas).catch(() => {})
  }, [admin])

  useEffect(() => {
    const t = setTimeout(carregar, 250)
    return () => clearTimeout(t)
  }, [carregar])

  useEffect(() => {
    const t = setInterval(carregar, 60000)
    return () => clearInterval(t)
  }, [carregar])

  useEffect(() => { carregarCapturas() }, [carregarCapturas])

  async function capturarAgora() {
    setAvisoCaptura('')
    try {
      const r = await api('/api/intimacoes/capturar?dias=3', { method: 'POST', body: {} })
      setAvisoCaptura(r.aviso)
      setTimeout(() => { carregar(); carregarCapturas() }, 20000)
    } catch (e) {
      setAvisoCaptura(e.message)
    }
  }

  function aoMudar() {
    carregar()
    carregarCapturas()
    avisarMenu()
  }

  return (
    <div className="ibb">
      <style>{CSS}</style>

      <div className="ibb-top">
        <div className="ibb-chips" role="tablist" aria-label="Situação">
          {STATUS_OPC.map(([k, rot]) => (
            <button key={k} className={'ibb-chip' + (status === k ? ' on' : '')} onClick={() => setStatus(k)}
              aria-pressed={status === k}>
              {rot}{k === 'nova' && cont.novas ? ` (${cont.novas})` : ''}
            </button>
          ))}
        </div>
        {admin && (
          <button className="ibb-btn" onClick={capturarAgora}>Capturar agora</button>
        )}
      </div>

      {avisoCaptura && <div className="ibb-ok">{avisoCaptura}</div>}

      <div className="ibb-filtros">
        <input className="ibb-in" placeholder="Buscar: número do processo, texto ou órgão" value={busca}
          onChange={(e) => setBusca(e.target.value)} />
        <input className="ibb-in" placeholder="Tribunal (ex.: TJSP)" value={tribunal}
          onChange={(e) => setTribunal(e.target.value)} />
        <input className="ibb-in" type="date" aria-label="Disponibilizada a partir de" value={de}
          onChange={(e) => setDe(e.target.value)} />
        <input className="ibb-in" type="date" aria-label="Disponibilizada até" value={ate}
          onChange={(e) => setAte(e.target.value)} />
      </div>

      <div className="ibb-resumo">
        <b>{cont.novas}</b> {cont.novas === 1 ? 'intimação nova aguardando conferência' : 'intimações novas aguardando conferência'}
        {' · '}{lista.total} na lista
      </div>

      {erro && <div className="ibb-erro">{erro}</div>}

      {admin && capturas.length > 0 && (
        <div className="ibb-aviso" style={{ marginBottom: 14 }}>
          <b>Últimas capturas</b>
          {capturas.slice(0, 4).map((c) => (
            <div key={c.id} style={{ marginTop: 4 }}>
              {dataHoraBR(c.iniciada_em)} · OAB {c.oab} · {RESULTADO_CAPTURA[c.resultado] || c.resultado}
              {' · '}{c.novas} nova(s) · tentativas {c.tentativas}
            </div>
          ))}
        </div>
      )}

      {carregando ? (
        <div className="ibb-vazio">Carregando…</div>
      ) : lista.items.length === 0 ? (
        <div className="ibb-vazio">
          {status === 'nova' ? 'Nenhuma intimação nova. A captura roda sozinha no servidor.' : 'Nada nesta situação.'}
        </div>
      ) : (
        <div className="ibb-lista">
          {lista.items.map((i) => (
            <button key={i.id} className={'ibb-item' + (i.status === 'nova' ? ' nova' : '')}
              onClick={() => setAberta(i.id)}>
              <div>
                <div className="ibb-linha">
                  <span className="ibb-num">{i.numero_processo || 'Sem número'}</span>
                  {i.tribunal && <span className="ibb-tag">{i.tribunal}</span>}
                  {i.status !== 'nova' && <span className="ibb-tag">{STATUS_ROTULO[i.status]}</span>}
                  {i.processo_id && <span className="ibb-tag ouro">Processo no sistema</span>}
                </div>
                <div className="ibb-sub">{i.orgao || '—'}{i.tipo_comunicacao ? ` · ${i.tipo_comunicacao}` : ''}</div>
                <div className="ibb-sub">
                  Sugestão: <b>{i.rotulo_ato || 'não classificado'}</b>
                  {i.prazo_dias ? ` · ${i.prazo_dias} dias` : ''}
                  {i.data_fatal ? ` · fatal sugerida ${dataBR(i.data_fatal)}` : ''}
                </div>
              </div>
              <div className="ibb-dir">
                <div className="ibb-sub">Disponibilizada</div>
                <div>{dataBR(i.disponibilizada_em)}</div>
                {i.status === 'nova' && i.alertas?.length > 0 && <div className="ibb-tag ouro" style={{ marginTop: 6 }}>Conferir</div>}
              </div>
            </button>
          ))}
        </div>
      )}

      {admin && <Oabs />}

      {aberta != null && (
        <Perfil id={aberta} onFechar={() => setAberta(null)} onMudou={aoMudar} />
      )}
    </div>
  )
}

function Perfil({ id, onFechar, onMudou }) {
  const { user } = useAuth()
  const podeTratar = user?.papel === 'admin' || user?.papel === 'advogado'
  const [d, setD] = useState(null)
  const [erro, setErro] = useState('')
  const [modo, setModo] = useState('ver')
  const [motivo, setMotivo] = useState('')
  const [enviando, setEnviando] = useState(false)

  const recarregar = useCallback(() => {
    api(`/api/intimacoes/${id}`).then((r) => { setD(r); setErro('') }).catch((e) => setErro(e.message))
  }, [id])

  useEffect(() => { recarregar() }, [recarregar])

  async function descartar() {
    setEnviando(true)
    setErro('')
    try {
      await api(`/api/intimacoes/${id}/descartar`, { method: 'POST', body: { motivo } })
      onMudou()
      onFechar()
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="ibb-fundo" onClick={(e) => { if (e.target === e.currentTarget) onFechar() }}>
      <div className="ibb-modal" role="dialog" aria-modal="true" aria-label="Intimação">
        {!d ? (
          erro ? <div className="ibb-erro">{erro}</div> : <div className="ibb-vazio">Carregando…</div>
        ) : modo === 'conferir' ? (
          <Conferir d={d} onVoltar={() => setModo('ver')} onSalvo={() => { onMudou(); onFechar() }} />
        ) : (
          <>
            <h2>{d.numero_processo || 'Sem número de processo'}</h2>
            <div className="ibb-sub">
              {d.tribunal}{d.orgao ? ` · ${d.orgao}` : ''}{d.tipo_comunicacao ? ` · ${d.tipo_comunicacao}` : ''}
            </div>
            <div className="ibb-sub" style={{ marginTop: 6 }}>
              Situação: <b>{STATUS_ROTULO[d.status]}</b>
              {d.status !== 'nova' && d.conferida_por && <> · por {d.conferida_por}</>}
              {d.status === 'descartada' && d.descartada_motivo && <> · motivo: {d.descartada_motivo}</>}
            </div>

            <div className="ibb-sec">
              <h3>Datas</h3>
              <div className="ibb-sub">
                Disponibilizada em {dataBR(d.disponibilizada_em)} · publicada em {dataBR(d.publicada_em)} ·
                início da contagem {dataBR(d.inicio_prazo)}
              </div>
            </div>

            <div className="ibb-sec">
              <h3>Sugestão do classificador</h3>
              <div className="ibb-sub">
                {d.rotulo_ato || 'Não classificado'}
                {d.prazo_dias ? ` · ${d.prazo_dias} dias (${d.prazo_origem === 'texto' ? 'indicado no texto' : 'regra usual do ato'})` : ' · sem prazo deduzido'}
                {d.data_fatal ? ` · fatal sugerida ${dataBR(d.data_fatal)}` : ''}
              </div>
              {d.status === 'nova' && d.alertas?.map((a, n) => <div key={n} className="ibb-aviso">{a}</div>)}
            </div>

            <div className="ibb-sec">
              <h3>Texto da intimação</h3>
              <pre className="ibb-texto">{d.texto || 'Texto não informado pelo tribunal.'}</pre>
              {d.link && (
                <p style={{ marginTop: 8 }}>
                  <a href={d.link} target="_blank" rel="noreferrer" style={{ color: 'var(--gold, #d5b974)' }}>
                    Abrir a publicação no tribunal
                  </a>
                </p>
              )}
            </div>

            {d.prazos?.length > 0 && (
              <div className="ibb-sec">
                <h3>Já criado no Calendário</h3>
                {d.prazos.map((p) => (
                  <div key={p.id} className="ibb-sub" style={{ marginBottom: 4 }}>
                    {p.titulo} · {p.tipo} · {dataBR(p.data)}{p.hora ? ` ${p.hora}` : ''}
                    {p.aprovacao === 'pendente' ? ' · aguarda aprovação' : ''}
                    {p.concluido ? ' · concluído' : ''}
                  </div>
                ))}
              </div>
            )}

            {d.status === 'nova' && podeTratar && modo === 'descartar' && (
              <div className="ibb-sec">
                <label className="ibb-lbl" htmlFor="ibb-motivo">Motivo do descarte (fica registrado)</label>
                <textarea id="ibb-motivo" className="ibb-in" rows={3} value={motivo}
                  onChange={(e) => setMotivo(e.target.value)} />
              </div>
            )}

            {erro && <div className="ibb-erro">{erro}</div>}

            <div className="ibb-acoes">
              {d.status === 'nova' && podeTratar && modo !== 'descartar' && (
                <>
                  <button className="ibb-btn perigo" onClick={() => setModo('descartar')}>Descartar</button>
                  <button className="ibb-btn ouro" onClick={() => setModo('conferir')}>Conferir e criar no Calendário</button>
                </>
              )}
              {d.status === 'nova' && podeTratar && modo === 'descartar' && (
                <>
                  <button className="ibb-btn" onClick={() => setModo('ver')}>Voltar</button>
                  <button className="ibb-btn perigo" disabled={enviando || motivo.trim().length < 3} onClick={descartar}>
                    Confirmar descarte
                  </button>
                </>
              )}
              <button className="ibb-btn" onClick={onFechar}>Fechar</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function Conferir({ d, onVoltar, onSalvo }) {
  const [pessoas, setPessoas] = useState([])
  const [itens, setItens] = useState(() => {
    const sugeridos = (d.sugestoes || []).map((s) => ({
      ...itemVazio(d.numero_processo || ''), tipo: s.tipo, titulo: s.titulo, sugerido: true,
      data: s.data || '', prazo_dias: s.prazo_dias ?? '',
    }))
    return sugeridos.length ? sugeridos : [itemVazio(d.numero_processo || '')]
  })
  const [erro, setErro] = useState('')
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    api('/api/intimacoes/responsaveis').then(setPessoas).catch((e) => setErro(e.message))
  }, [])

  function alterar(idx, campo, valor) {
    setItens((atual) => atual.map((it, n) => (n === idx ? { ...it, [campo]: valor } : it)))
  }

  function mover(idx, dir) {
    setItens((atual) => {
      const nova = [...atual]
      const alvo = idx + dir
      if (alvo < 0 || alvo >= nova.length) return atual
      ;[nova[idx], nova[alvo]] = [nova[alvo], nova[idx]]
      return nova
    })
  }

  function remover(idx) {
    setItens((atual) => atual.filter((_, n) => n !== idx))
  }

  async function salvar() {
    setErro('')
    const faltando = itens.findIndex((it) => !it.titulo.trim() || !it.data)
    if (faltando >= 0) {
      setErro(`Providência ${faltando + 1}: informe o título e a data.`)
      return
    }
    setEnviando(true)
    try {
      await api(`/api/intimacoes/${d.id}/conferir`, {
        method: 'POST',
        body: {
          itens: itens.map((it) => ({
            ...it,
            prazo_dias: it.prazo_dias === '' ? null : Number(it.prazo_dias),
            hora: it.tipo === 'audiencia' || it.tipo === 'reuniao' ? it.hora : '',
          })),
        },
      })
      onSalvo()
    } catch (e) {
      setErro(e.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <>
      <h2>Conferir intimação</h2>
      <div className="ibb-sub">{d.numero_processo} · {d.tribunal}</div>

      <div className="ibb-aviso">{AVISO_CALCULO}</div>
      <div className="ibb-aviso">{AVISO_APROVACAO}</div>
      {d.alertas?.map((a, n) => <div key={n} className="ibb-aviso">{a}</div>)}

      <div className="ibb-sec">
        <h3>Providências ({itens.length})</h3>
        {itens.map((it, idx) => (
          <div key={idx} className="ibb-prov">
            <div className="ibb-prov-topo">
              <span className="ibb-sub">Providência {idx + 1}</span>
              <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {it.sugerido && <span className="ibb-sugestao">SUGESTÃO DO CLASSIFICADOR · confira</span>}
                <button className="ibb-btn peq" disabled={idx === 0} onClick={() => mover(idx, -1)}>Subir</button>
                <button className="ibb-btn peq" disabled={idx === itens.length - 1} onClick={() => mover(idx, 1)}>Descer</button>
                {itens.length > 1 && <button className="ibb-btn peq perigo" onClick={() => remover(idx)}>Remover</button>}
              </span>
            </div>
            <div className="ibb-form">
              <div>
                <label className="ibb-lbl">Tipo</label>
                <select className="ibb-in" value={it.tipo} onChange={(e) => alterar(idx, 'tipo', e.target.value)}>
                  {TIPOS.map(([k, rot]) => <option key={k} value={k}>{rot}</option>)}
                </select>
              </div>
              <div>
                <label className="ibb-lbl">Responsável</label>
                <select className="ibb-in" value={it.responsavel} onChange={(e) => alterar(idx, 'responsavel', e.target.value)}>
                  <option value="">Sem responsável</option>
                  {pessoas.map((p) => <option key={p.email} value={p.email}>{p.nome}</option>)}
                </select>
              </div>
              <div className="largo">
                <label className="ibb-lbl">Título</label>
                <input className="ibb-in" value={it.titulo} onChange={(e) => alterar(idx, 'titulo', e.target.value)} />
              </div>
              <div>
                <label className="ibb-lbl">{it.tipo === 'prazo' ? 'Data fatal' : 'Data'}</label>
                <input className="ibb-in" type="date" value={it.data} onChange={(e) => alterar(idx, 'data', e.target.value)} />
              </div>
              {(it.tipo === 'audiencia' || it.tipo === 'reuniao') && (
                <div>
                  <label className="ibb-lbl">Hora</label>
                  <input className="ibb-in" placeholder="14:30" value={it.hora} onChange={(e) => alterar(idx, 'hora', e.target.value)} />
                </div>
              )}
              {it.tipo === 'prazo' && (
                <div>
                  <label className="ibb-lbl">Prazo em dias (vazio = sem prazo deduzido)</label>
                  <input className="ibb-in" type="number" min="1" max="120" value={it.prazo_dias}
                    onChange={(e) => alterar(idx, 'prazo_dias', e.target.value)} />
                </div>
              )}
              <div>
                <label className="ibb-lbl">Pasta do cliente</label>
                <input className="ibb-in" placeholder="Ex.: 383" value={it.pasta} onChange={(e) => alterar(idx, 'pasta', e.target.value)} />
              </div>
              <div>
                <label className="ibb-lbl">Cliente</label>
                <input className="ibb-in" value={it.cliente} onChange={(e) => alterar(idx, 'cliente', e.target.value)} />
              </div>
              <div className="largo">
                <label className="ibb-lbl">Observação</label>
                <textarea className="ibb-in" rows={2} value={it.observacao} onChange={(e) => alterar(idx, 'observacao', e.target.value)} />
              </div>
            </div>
          </div>
        ))}
        <button className="ibb-btn" onClick={() => setItens((a) => [...a, itemVazio(d.numero_processo || '')])}>
          Adicionar providência
        </button>
      </div>

      {erro && <div className="ibb-erro">{erro}</div>}

      <div className="ibb-acoes">
        <button className="ibb-btn" onClick={onVoltar}>Voltar</button>
        <button className="ibb-btn ouro" disabled={enviando} onClick={salvar}>
          {enviando ? 'Gravando…' : `Criar ${itens.length === 1 ? '1 item' : `${itens.length} itens`} no Calendário`}
        </button>
      </div>
    </>
  )
}

function Oabs() {
  const [oabs, setOabs] = useState([])
  const [nova, setNova] = useState('')
  const [rotulo, setRotulo] = useState('')
  const [erro, setErro] = useState('')

  const carregar = useCallback(() => {
    api('/api/intimacoes/oabs').then(setOabs).catch((e) => setErro(e.message))
  }, [])

  useEffect(() => { carregar() }, [carregar])

  async function incluir() {
    setErro('')
    try {
      await api('/api/intimacoes/oabs', { method: 'POST', body: { oab: nova, rotulo } })
      setNova('')
      setRotulo('')
      carregar()
    } catch (e) {
      setErro(e.message)
    }
  }

  async function retirar(oab) {
    setErro('')
    try {
      await api('/api/intimacoes/oabs?oab=' + encodeURIComponent(oab), { method: 'DELETE' })
      carregar()
    } catch (e) {
      setErro(e.message)
    }
  }

  return (
    <div className="ibb-sec" style={{ marginTop: 22 }}>
      <h3>OABs monitoradas</h3>
      <div className="ibb-sub">
        A captura consulta estas OABs. Formato NUMERO/UF, por exemplo 123456/SP. Também podem vir do arquivo de configuração (INT_OABS).
      </div>
      <div className="ibb-oabs">
        {oabs.length === 0 && <span className="ibb-sub">Nenhuma OAB cadastrada ainda.</span>}
        {oabs.map((o) => (
          <span key={o.oab} className="ibb-oab">
            {o.oab}{o.rotulo ? ` · ${o.rotulo}` : ''}
            <button className="ibb-btn peq perigo" onClick={() => retirar(o.oab)}>Remover</button>
          </span>
        ))}
      </div>
      <div className="ibb-filtros" style={{ marginTop: 10, gridTemplateColumns: '1fr 2fr auto' }}>
        <input className="ibb-in" placeholder="NUMERO/UF" value={nova} onChange={(e) => setNova(e.target.value)} />
        <input className="ibb-in" placeholder="Rótulo (opcional)" value={rotulo} onChange={(e) => setRotulo(e.target.value)} />
        <button className="ibb-btn" disabled={!nova.trim()} onClick={incluir}>Adicionar</button>
      </div>
      {erro && <div className="ibb-erro">{erro}</div>}
    </div>
  )
}
