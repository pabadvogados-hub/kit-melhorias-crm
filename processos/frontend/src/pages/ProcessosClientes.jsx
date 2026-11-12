import { useEffect, useState } from 'react'
import { api } from '../api'
import { nomeCurto, fmtDia, mensagemErro } from './processosUtil'

// Aba Clientes: busca, cadastro e ficha. A ficha lista os processos do cliente (so os que a pessoa ve).

const VAZIO = { nome: '', cpf_cnpj: '', telefone: '', email: '', endereco: '', cidade: '', uf: '' }

export default function ProcessosClientes({ onAbrirProcesso }) {
  const [q, setQ] = useState('')
  const [lista, setLista] = useState([])
  const [carregando, setCarregando] = useState(true)
  const [aberto, setAberto] = useState(null)     // ficha do cliente selecionado
  const [modo, setModo] = useState(null)         // null | 'novo' | 'editar'
  const [form, setForm] = useState(VAZIO)
  const [erro, setErro] = useState('')
  const [aviso, setAviso] = useState('')
  const [ocupado, setOcupado] = useState(false)

  async function buscar() {
    try {
      const r = await api(`/api/processos/clientes?q=${encodeURIComponent(q)}`)
      setLista(r.items)
      setErro('')
    } catch (e) {
      setErro(mensagemErro(e))
    } finally {
      setCarregando(false)
    }
  }

  useEffect(() => {
    const t = setTimeout(buscar, q ? 300 : 0)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q])

  async function abrirCliente(id) {
    setModo(null); setAviso(''); setErro('')
    try {
      setAberto(await api(`/api/processos/clientes/${id}`))
    } catch (e) {
      setErro(mensagemErro(e))
    }
  }

  function novo() {
    setAberto(null); setForm(VAZIO); setModo('novo'); setAviso(''); setErro('')
  }

  function editar() {
    const c = aberto.cliente
    setForm({ nome: c.nome, cpf_cnpj: c.cpf_cnpj, telefone: c.telefone, email: c.email,
      endereco: c.endereco, cidade: c.cidade, uf: c.uf })
    setModo('editar'); setAviso(''); setErro('')
  }

  async function salvar(ev) {
    ev.preventDefault()
    setOcupado(true); setErro('')
    try {
      if (modo === 'novo') {
        const r = await api('/api/processos/clientes', { method: 'POST', body: form })
        setAviso('Cliente cadastrado.')
        await abrirCliente(r.id)
      } else {
        const r = await api(`/api/processos/clientes/${aberto.cliente.id}`, { method: 'PATCH', body: form })
        setAberto(r)
        setModo(null)
        setAviso('Dados salvos.')
      }
      buscar()
    } catch (e) {
      setErro(mensagemErro(e))
    } finally {
      setOcupado(false)
    }
  }

  const campo = (rotulo, chave, extra = {}) => (
    <label className="pr-campo">
      <span>{rotulo}</span>
      <input value={form[chave]} onChange={(e) => setForm({ ...form, [chave]: e.target.value })} {...extra} />
    </label>
  )

  return (
    <div className="pr-clientes">
      <div className="pr-clientes-col">
        <div className="pr-linha">
          <input className="pr-busca-cli" placeholder="Buscar cliente: nome, CPF, telefone, e-mail" value={q}
            onChange={(e) => setQ(e.target.value)} aria-label="Buscar cliente" />
          <button className="btn btn-gold btn-sm" onClick={novo}>+ Cliente</button>
        </div>
        {erro && <div className="alert alert-error">{erro}</div>}
        <ul className="pr-lista pr-lista-cli">
          {lista.map((c) => (
            <li key={c.id} className={`pr-item-cli ${aberto && aberto.cliente.id === c.id ? 'on' : ''}`}
              onClick={() => abrirCliente(c.id)} tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') abrirCliente(c.id) }}>
              <strong>{c.nome}</strong>
              <div className="muted pr-pequeno">{[c.telefone, c.email].filter(Boolean).join(' · ') || 'Sem contato'}</div>
            </li>
          ))}
        </ul>
        {!lista.length && !carregando && <p className="muted pr-vazio">Nenhum cliente encontrado.</p>}
      </div>

      <div className="pr-clientes-col pr-clientes-ficha">
        {aviso && <div className="alert alert-ok">{aviso}</div>}

        {modo && (
          <form onSubmit={salvar} className="pr-form">
            <h3 className="pr-subtitulo">{modo === 'novo' ? 'Novo cliente' : 'Editar cliente'}</h3>
            {campo('Nome', 'nome', { required: true })}
            {campo('CPF ou CNPJ (opcional)', 'cpf_cnpj')}
            {campo('Telefone', 'telefone')}
            {campo('E-mail', 'email', { type: 'email' })}
            {campo('Endereço', 'endereco')}
            <div className="pr-linha-2">
              {campo('Cidade', 'cidade')}
              {campo('UF', 'uf', { maxLength: 2 })}
            </div>
            <div className="pr-acoes">
              <button type="submit" className="btn btn-gold btn-sm" disabled={ocupado || !form.nome.trim()}>Salvar</button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setModo(null)}>Cancelar</button>
            </div>
          </form>
        )}

        {!modo && aberto && (
          <>
            <div className="pr-ficha-topo">
              <div>
                <div className="pr-ficha-titulo">{aberto.cliente.nome}</div>
                <div className="muted pr-pequeno">{aberto.cliente.cpf_cnpj || 'Sem CPF/CNPJ'}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={editar}>Editar</button>
            </div>
            <dl className="pr-dl">
              <dt>Telefone</dt><dd>{aberto.cliente.telefone || <span className="muted">—</span>}</dd>
              <dt>E-mail</dt><dd>{aberto.cliente.email || <span className="muted">—</span>}</dd>
              <dt>Endereço</dt><dd>{[aberto.cliente.endereco, aberto.cliente.cidade, aberto.cliente.uf].filter(Boolean).join(', ') || <span className="muted">—</span>}</dd>
            </dl>
            <h3 className="pr-subtitulo">Processos ({aberto.processos.length})</h3>
            {aberto.processos.length === 0 && <p className="muted pr-pequeno">Nenhum processo visível para você.</p>}
            <ul className="pr-lista">
              {aberto.processos.map((p) => (
                <li key={p.id} className="pr-linha-clicavel" onClick={() => onAbrirProcesso(p.id)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter') onAbrirProcesso(p.id) }}>
                  <div>
                    <strong>{p.numero || 'Sem número'}</strong>
                    <div className="muted pr-pequeno">
                      {p.fase} · {nomeCurto(p.responsavel_email)}{p.pasta ? ` · pasta ${p.pasta}` : ''}
                      {p.criado_em ? ` · aberto em ${fmtDia(p.criado_em.slice(0, 10))}` : ''}
                    </div>
                  </div>
                  <span className={`pill ${p.status === 'ativo' ? 'running' : 'pending'}`}>
                    {p.status === 'ativo' ? 'Ativo' : 'Encerrado'}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {!modo && !aberto && <p className="muted">Escolha um cliente à esquerda, ou cadastre um novo.</p>}
      </div>
    </div>
  )
}
