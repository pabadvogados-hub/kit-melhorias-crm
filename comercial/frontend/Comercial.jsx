import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

// PAINEL COMERCIAL. Um componente, duas telas:
//   modo="admin" -> painel do time: numeros, mesa de cada pessoa, funil, perdas, metas. So administrador.
//   modo="mesa"  -> a mesa de quem esta logado (rota /minha-mesa), so os numeros dela.
// Tudo vem do backend ao vivo (routers/comercial.py). Cada numero clicavel abre a lista
// de conversas por tras dele: o mesmo recorte que gerou o numero.
// Sem emoji: a tela usa so texto, cor e a paleta da marca.

const PERIODOS = [
  { chave: 'hoje', rotulo: 'Hoje' },
  { chave: 'semana', rotulo: 'Semana' },
  { chave: 'mes', rotulo: 'Mês' },
  { chave: 'mes_anterior', rotulo: 'Mês anterior' },
  { chave: '15dias', rotulo: '15 dias' },
]

const ROTULO_LISTA = {
  leads: 'Leads do período',
  respondidos: 'Leads respondidos',
  sem_resposta: 'Leads sem resposta',
  fechados: 'Contratos assinados no período',
  fechados_de_leads: 'Fechados entre os leads do período',
  em_fechamento: 'Em fechamento, sem assinatura',
  perdidos: 'Perdidos no período',
  parados: 'Parados na mesma coluna',
  etapa: 'Coluna do funil',
}

const ATUALIZA_MS = 60 * 1000
const TZ = 'America/Sao_Paulo'

const nf = (n) => (n == null ? '—' : Number(n).toLocaleString('pt-BR'))
const pct = (n) => (n == null ? '—' : `${Number(n).toLocaleString('pt-BR', { maximumFractionDigits: 1 })}%`)
const moeda = (n) => (n == null ? '—' : Number(n).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }))
const pessoa = (email) => (email ? email.split('@')[0] : 'sem dona')
const dataCurta = (iso) => (iso ? new Date(iso).toLocaleString('pt-BR', { timeZone: TZ, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—')
const hora = (iso) => (iso ? new Date(iso).toLocaleTimeString('pt-BR', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '')
const dataDeIso = (d) => (d ? d.split('-').reverse().join('/') : '')
const mesLegivel = (m) => (m ? `${m.split('-')[1]}/${m.split('-')[0]}` : '')

function minutos(m) {
  if (m == null) return '—'
  if (m < 60) return `${Math.round(m)} min`
  return `${(m / 60).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} h`
}

// localStorage pode estar bloqueado (aba privada, sem permissao): a tela funciona sem ele.
function lerPeriodo() {
  try { return localStorage.getItem('bb_comercial_periodo') || 'mes' } catch { return 'mes' }
}
function salvarPeriodo(p) {
  try { localStorage.setItem('bb_comercial_periodo', p) } catch { /* segue sem guardar */ }
}

const cartao = { margin: 0, padding: 18 }

function Painel({ titulo, sub, children, style }) {
  return (
    <section className="panel" style={{ ...cartao, ...style }}>
      <h2 style={{ fontSize: 15.5 }}>{titulo}</h2>
      {sub && <div className="p-sub" style={{ marginBottom: 14 }}>{sub}</div>}
      {children}
    </section>
  )
}

// Numero da tela. Clicavel quando ha drill-down; alerta deixa o valor em vermelho.
function Tile({ rotulo, valor, apoio, onClick, alerta }) {
  const Tag = onClick ? 'button' : 'div'
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className="panel"
      style={{ margin: 0, padding: '14px 16px', textAlign: 'left', font: 'inherit', color: 'inherit',
        cursor: onClick ? 'pointer' : 'default', width: '100%' }}
    >
      <div className="muted" style={{ fontSize: 11.5, textTransform: 'uppercase', letterSpacing: '.04em' }}>{rotulo}</div>
      <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.2, marginTop: 4,
        color: alerta ? 'var(--danger)' : 'var(--text)' }}>{valor}</div>
      {apoio && <div className="muted" style={{ fontSize: 11.5, marginTop: 3 }}>{apoio}</div>}
    </Tag>
  )
}

function Barra({ valor, maximo, cor = 'var(--gold)' }) {
  const largura = maximo > 0 ? Math.min(100, (valor / maximo) * 100) : 0
  return (
    <div style={{ height: 8, background: 'rgba(255,255,255,0.06)', borderRadius: 5, overflow: 'hidden' }}>
      <div style={{ width: `${largura}%`, height: '100%', background: cor, borderRadius: 5 }} />
    </div>
  )
}

function Meta({ ritmo }) {
  if (!ritmo) return null
  const titulo = `Meta de ${mesLegivel(ritmo.mes)}`
  if (ritmo.meta == null) {
    return (
      <Painel titulo={titulo} sub="Meta de contratos não configurada.">
        <p className="muted" style={{ fontSize: 13 }}>
          Realizado no mês: <strong style={{ color: 'var(--text)' }}>{nf(ritmo.realizado)}</strong> contratos assinados.
          Preencha a meta em comercial_metas.json (metas_mensais) para ver o ritmo.
        </p>
      </Painel>
    )
  }
  const feitoPct = ritmo.meta > 0 ? Math.round((ritmo.realizado / ritmo.meta) * 100) : 0
  return (
    <Painel titulo={titulo} sub={`${nf(ritmo.realizado)} de ${nf(ritmo.meta)} contratos (${feitoPct}%)`}>
      <Barra valor={ritmo.realizado} maximo={ritmo.meta} />
      {ritmo.disponivel && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginTop: 14 }}>
          <Tile rotulo="Projeção do mês" valor={nf(ritmo.projecao)}
            apoio={ritmo.no_ritmo == null ? null : ritmo.no_ritmo ? 'no ritmo da meta' : 'abaixo do ritmo da meta'}
            alerta={ritmo.no_ritmo === false} />
          <Tile rotulo="Ritmo atual" valor={ritmo.ritmo_atual_por_dia == null ? '—' : `${ritmo.ritmo_atual_por_dia.toLocaleString('pt-BR')} por dia útil`}
            apoio={`${ritmo.dias_uteis_decorridos} de ${ritmo.dias_uteis_total} dias úteis`} />
          <Tile rotulo="Precisa por dia útil" valor={ritmo.necessario_por_dia == null ? '—' : ritmo.necessario_por_dia.toLocaleString('pt-BR')}
            apoio={`nos ${ritmo.dias_uteis_restantes} dias úteis que faltam`} />
        </div>
      )}
      {ritmo.disponivel === false && (
        <p className="muted" style={{ fontSize: 12.5, marginTop: 10 }}>Mês fechado: sem projeção.</p>
      )}
    </Painel>
  )
}

function Conversas({ drill, onFechar }) {
  const [lista, setLista] = useState(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    let vivo = true
    setLista(null)
    setErro('')
    const q = new URLSearchParams({ metrica: drill.metrica, periodo: drill.periodo })
    if (drill.pessoa) q.set('pessoa', drill.pessoa)
    if (drill.quadro) q.set('quadro', drill.quadro)
    if (drill.etapa != null) q.set('etapa', drill.etapa)
    api(`/api/comercial/conversas?${q.toString()}`)
      .then((r) => { if (vivo) setLista(r) })
      .catch((e) => { if (vivo) setErro(e.message) })
    return () => { vivo = false }
  }, [drill])

  return (
    <section className="panel" style={{ ...cartao, borderColor: 'rgba(213,185,116,0.4)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <div>
          <h2 style={{ fontSize: 15.5 }}>{`${drill.titulo}${lista ? ` (${nf(lista.total)})` : ''}`}</h2>
          <div className="p-sub" style={{ marginBottom: 0 }}>
            {lista?.limitado_a ? `Mostrando as ${lista.limitado_a} mais recentes.` : 'Lista do mesmo recorte que gerou o número.'}
          </div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onFechar}>Fechar lista</button>
      </div>
      {erro && <div className="alert alert-error">{erro}</div>}
      {!lista && !erro && <div className="muted">Carregando…</div>}
      {lista && lista.conversas.length === 0 && <div className="muted">Nenhuma conversa nesse recorte.</div>}
      {lista && lista.conversas.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table className="tabela-compacta" style={{ minWidth: 720 }}>
            <thead>
              <tr>
                <th>Nome</th><th>Quadro</th><th>Coluna</th><th>Dona</th>
                <th>Chegou</th><th>Respondeu</th><th>Na coluna desde</th><th>Assinado</th>
              </tr>
            </thead>
            <tbody>
              {lista.conversas.map((c) => (
                <tr key={c.id}>
                  <td style={{ fontWeight: 600 }}>{c.nome}</td>
                  <td className="muted">{c.quadro}</td>
                  <td>{c.etapa || '—'}</td>
                  <td className="muted">{pessoa(c.dona)}</td>
                  <td>{dataCurta(c.primeiro_contato)}</td>
                  <td>{dataCurta(c.primeira_resposta)}</td>
                  <td>{dataCurta(c.etapa_desde)}</td>
                  <td>{dataCurta(c.assinado_em)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function Comercial({ modo = 'admin' }) {
  const admin = modo === 'admin'
  const [periodo, setPeriodo] = useState(lerPeriodo)
  const [dados, setDados] = useState(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(false)
  const [drill, setDrill] = useState(null)

  const carregar = useCallback(async () => {
    setCarregando(true)
    try {
      const rota = admin ? '/api/comercial/painel' : '/api/comercial/minha-mesa'
      setDados(await api(`${rota}?periodo=${periodo}`))
      setErro('')
    } catch (e) {
      setErro(e.message)
    } finally {
      setCarregando(false)
    }
  }, [admin, periodo])

  // Ao vivo: recarrega a cada minuto, mas so com a aba visivel.
  useEffect(() => {
    carregar()
    const t = setInterval(() => { if (document.visibilityState === 'visible') carregar() }, ATUALIZA_MS)
    return () => clearInterval(t)
  }, [carregar])

  function trocarPeriodo(p) {
    salvarPeriodo(p)
    setPeriodo(p)
    setDrill(null)
  }

  function abrir(metrica, extra = {}) {
    setDrill({ metrica, periodo, titulo: ROTULO_LISTA[metrica] || metrica, ...extra })
  }

  const r = dados?.resumo
  const dias = dados?.parados?.dias
  const apagados = dados?.perdas?.apagados_pela_limpeza
  const tiles = r ? [
    { rotulo: 'Leads', valor: nf(r.leads), apoio: `${nf(r.respondidos)} responderam (${pct(r.taxa_resposta)})`,
      metrica: 'leads' },
    { rotulo: 'Sem resposta', valor: nf(r.sem_resposta), alerta: r.sem_resposta > 0,
      apoio: 'nenhuma fala nossa depois da primeira', metrica: 'sem_resposta' },
    { rotulo: 'Contratos assinados', valor: nf(r.fechados),
      apoio: `${nf(r.fechados_de_leads_do_periodo)} vieram dos leads do período (${pct(r.taxa_fechamento_de_leads)})`,
      metrica: 'fechados' },
    { rotulo: 'Em fechamento', valor: nf(r.em_fechamento), apoio: 'na elaboração ou assinatura, sem assinatura ainda',
      metrica: 'em_fechamento' },
    { rotulo: 'Perdidos', valor: nf(r.perdidos),
      apoio: apagados ? `inclui ${nf(apagados)} apagados pela limpeza` : 'desqualificado ou não seguiu',
      metrica: 'perdidos' },
    { rotulo: 'Parados', valor: nf(r.parados), alerta: r.parados > 0,
      apoio: dias ? `${dias} dias ou mais na mesma coluna` : '', metrica: 'parados' },
    { rotulo: 'Até a 1ª resposta', valor: minutos(r.tempo_1a_resposta_min),
      apoio: `equipe: ${minutos(r.tempo_1a_resposta_equipe_min)} (mediana)` },
    admin && r.custo_por_lead != null && { rotulo: 'Custo por lead', valor: moeda(r.custo_por_lead),
      apoio: `gasto ${moeda(r.gasto_anuncios)} no período (anúncios gravados)` },
    admin && r.custo_por_fechamento != null && { rotulo: 'Custo por contrato', valor: moeda(r.custo_por_fechamento),
      apoio: 'gasto de anúncio ÷ contratos assinados' },
    r.receita_estimada != null && { rotulo: 'Receita estimada', valor: moeda(r.receita_estimada),
      apoio: `estimativa pelo ticket configurado${r.fechados_sem_ticket ? ` · ${r.fechados_sem_ticket} sem ticket` : ''}` },
  ].filter(Boolean) : []

  return (
    <>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div role="group" aria-label="Período" style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {PERIODOS.map((p) => (
            <button key={p.chave} type="button" aria-pressed={periodo === p.chave}
              className={`btn btn-sm ${periodo === p.chave ? 'btn-gold' : 'btn-ghost'}`}
              onClick={() => trocarPeriodo(p.chave)}>{p.rotulo}</button>
          ))}
        </div>
        <div className="muted" style={{ fontSize: 12.5, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="live-dot" aria-hidden="true" />
          <span>Ao vivo{dados ? ` · atualizado às ${hora(dados.gerado_em)}` : ''}</span>
          <button className="btn btn-ghost btn-sm" onClick={carregar} disabled={carregando}>
            {carregando ? 'Atualizando…' : 'Atualizar'}
          </button>
        </div>
      </div>

      {dados && (
        <div className="muted" style={{ fontSize: 13, marginBottom: 16 }}>
          {dados.periodo.rotulo} · {dataDeIso(dados.periodo.de)} a {dataDeIso(dados.periodo.ate)}
          {!admin && ' · sua mesa'}
        </div>
      )}
      {erro && <div className="alert alert-error">{erro}</div>}
      {!dados && !erro && <div className="center-load">Carregando o painel…</div>}

      {dados && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 18 }}>
            {tiles.map((t) => (
              <Tile key={t.rotulo} rotulo={t.rotulo} valor={t.valor} apoio={t.apoio} alerta={t.alerta}
                onClick={t.metrica ? () => abrir(t.metrica) : undefined} />
            ))}
          </div>

          {drill && <Conversas drill={drill} onFechar={() => setDrill(null)} />}

          <Meta ritmo={dados.meta?.ritmo} />

          {admin && dados.mesa && (
            <Painel titulo="Mesa de cada pessoa" sub="Quem está com cada lead e cada contrato. Toque no número para ver as conversas.">
              {dados.mesa.length === 0 && <div className="muted">Nenhuma conversa com dona no CRM ainda.</div>}
              {dados.mesa.length > 0 && (
                <div style={{ overflowX: 'auto' }}>
                  <table className="tabela-compacta" style={{ minWidth: 640 }}>
                    <thead>
                      <tr>
                        <th>Pessoa</th><th>Leads</th><th>Respostas</th><th>Contratos</th>
                        <th>Meta do mês</th><th>Em fechamento</th><th>Parados</th><th>1ª resposta</th>
                        {dados.ligacoes?.medido && <th>Ligações</th>}
                        {dados.comissao && <th>Comissão</th>}
                      </tr>
                    </thead>
                    <tbody>
                      {dados.mesa.map((m) => (
                        <tr key={m.pessoa}>
                          <td style={{ fontWeight: 600 }}>{pessoa(m.pessoa)}</td>
                          <td><button className="btn btn-ghost btn-sm" onClick={() => abrir('leads', { pessoa: m.pessoa })}>{nf(m.leads)}</button></td>
                          <td>{nf(m.respostas_equipe)}</td>
                          <td><button className="btn btn-ghost btn-sm" onClick={() => abrir('fechados', { pessoa: m.pessoa })}>{nf(m.fechados)}</button></td>
                          <td className="muted">{m.meta_fechados != null ? `${nf(m.realizado_mes)} de ${nf(m.meta_fechados)}` : `${nf(m.realizado_mes)} no mês`}</td>
                          <td>{nf(m.em_fechamento)}</td>
                          <td><button className="btn btn-ghost btn-sm" onClick={() => abrir('parados', { pessoa: m.pessoa })}
                            style={{ color: m.parados ? 'var(--danger)' : undefined }}>{nf(m.parados)}</button></td>
                          <td>{minutos(m.tempo_1a_resposta_equipe_min)}</td>
                          {dados.ligacoes?.medido && <td>{nf(m.ligacoes)}</td>}
                          {dados.comissao && <td>{moeda(m.comissao_estimada)}</td>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Painel>
          )}

          {dados.comissao && (
            <Painel titulo="Comissão estimada" sub="Valor fixo por contrato assinado, configurado em comercial_metas.json. Estimativa.">
              <div style={{ fontSize: 22, fontWeight: 800 }}>{moeda(dados.comissao.total_estimado)}</div>
            </Painel>
          )}

          {admin && dados.funil && (
            <Painel titulo="Funil por coluna" sub="Cards abertos em cada coluna agora. Toque no número para ver os cards.">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
                {dados.funil.map((q) => {
                  const maximo = Math.max(1, ...q.etapas.map((e) => e.quantidade))
                  return (
                    <div key={q.pid} style={{ border: '1px solid var(--border-soft)', borderRadius: 12, padding: 14 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                        <strong style={{ fontSize: 13.5 }}>{q.quadro}</strong>
                        <span className="muted" style={{ fontSize: 12 }}>{nf(q.abertas)} abertos · {nf(q.entradas_no_periodo)} entraram</span>
                      </div>
                      <div style={{ display: 'grid', gap: 8 }}>
                        {q.etapas.map((e) => (
                          <div key={e.nome}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 12.5, marginBottom: 3 }}>
                              <span>{e.nome || '(sem coluna)'}</span>
                              <span>
                                <button className="btn btn-ghost btn-sm" style={{ padding: '2px 8px' }}
                                  onClick={() => abrir('etapa', { quadro: q.quadro, etapa: e.nome || '(sem etapa)', titulo: `${q.quadro}: ${e.nome || 'sem coluna'}` })}>
                                  {nf(e.quantidade)}
                                </button>
                                {e.parados > 0 && <span className="muted" style={{ marginLeft: 6, color: 'var(--danger)' }}>{nf(e.parados)} parados</span>}
                              </span>
                            </div>
                            <Barra valor={e.quantidade} maximo={maximo} />
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </Painel>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 22 }}>
            <Painel titulo="Perdas por motivo" sub="O motivo é a coluna em que o card parou.">
              {dados.perdas.por_motivo.length === 0 && <div className="muted">Nenhuma perda no período.</div>}
              {dados.perdas.por_motivo.map((m) => (
                <div key={m.motivo} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, padding: '6px 0',
                  borderBottom: '1px solid var(--border-soft)' }}>
                  <span>{m.motivo}</span><strong>{nf(m.quantidade)}</strong>
                </div>
              ))}
              {dados.perdas.apagados_pela_limpeza != null && dados.perdas.apagados_pela_limpeza > 0 && (
                <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  {nf(dados.perdas.apagados_pela_limpeza)} já apagados pela limpeza automática de desqualificados.
                </div>
              )}
            </Painel>

            <Painel titulo="Parados" sub={dias ? `Sem mudar de coluna há ${dias} dias ou mais.` : ''}>
              {dados.parados.por_etapa.length === 0 && <div className="muted">Nada parado. Bom sinal.</div>}
              {dados.parados.por_etapa.map((p) => (
                <div key={`${p.quadro}|${p.etapa}`} style={{ display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13, padding: '6px 0',
                  borderBottom: '1px solid var(--border-soft)' }}>
                  <span>{p.etapa} <span className="muted">· {p.quadro}</span></span>
                  <button className="btn btn-ghost btn-sm" style={{ padding: '2px 8px' }}
                    onClick={() => abrir('etapa', { quadro: p.quadro, etapa: p.etapa, titulo: `${p.quadro}: ${p.etapa}` })}>
                    {nf(p.quantidade)} · até {nf(p.dias_maximo)} dias
                  </button>
                </div>
              ))}
            </Painel>
          </div>

          <Painel titulo="Ligações" sub="O que esta tela não consegue medir, e por quê.">
            {dados.ligacoes?.medido
              ? <div className="muted" style={{ fontSize: 13 }}>{nf(dados.ligacoes.total)} ligações registradas no período.</div>
              : <div className="muted" style={{ fontSize: 13 }}>Não medidas. O CRM não guarda ligação de forma estruturada. Para contar, a equipe escreve uma nota que começa com a marca configurada em comercial_metas.json (marca_ligacao).</div>}
          </Painel>

          <Painel titulo="Como ler os números" style={{ marginBottom: 40 }}>
            <ul className="muted" style={{ fontSize: 12.5, lineHeight: 1.6, paddingLeft: 18 }}>
              {dados.avisos.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </Painel>
        </>
      )}
    </>
  )
}
