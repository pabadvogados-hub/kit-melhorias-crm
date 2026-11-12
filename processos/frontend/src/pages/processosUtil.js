// Utilitarios do modulo Processos (formatacao e rotulos). Sem dependencia de tela.

export const PAPEIS_PARTE = [
  'CLIENTE', 'PARTE CONTRÁRIA', 'ADVOGADO CONTRÁRIO', 'TESTEMUNHA', 'INTERESSADO',
]

export const ROTULO_EVENTO = {
  criado: 'Criado',
  fase: 'Fase',
  editado: 'Editado',
  encerrado: 'Encerrado',
  reaberto: 'Reaberto',
  'parte+': 'Parte incluída',
  'parte-': 'Parte removida',
}

export function fmtData(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleDateString('pt-BR') + ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

export function fmtDia(iso) {
  if (!iso) return ''
  const [y, m, d] = String(iso).slice(0, 10).split('-')
  return d && m && y ? `${d}/${m}/${y}` : iso
}

export function nomeCurto(email) {
  if (!email) return 'Sem responsável'
  return email.split('@')[0]
}

export function valorBR(v) {
  if (v === null || v === undefined || v === '') return ''
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
}

// CSV para Excel em portugues: separador ";" e BOM para acentos.
export function baixarCSV(nomeArquivo, cabecalho, linhas) {
  const escapa = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const corpo = [cabecalho, ...linhas].map((l) => l.map(escapa).join(';')).join('\r\n')
  const blob = new Blob(['﻿' + corpo], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nomeArquivo
  a.click()
  URL.revokeObjectURL(url)
}

export function mensagemErro(e) {
  return (e && e.message) || 'Algo não deu certo. Tente de novo.'
}
