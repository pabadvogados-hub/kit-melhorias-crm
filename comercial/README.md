# Painel comercial

Painel ao vivo do funil de leads e contratos, lido direto do CRM. Para o administrador, mostra o time inteiro. Para cada pessoa, mostra a própria mesa (`/minha-mesa`). Aplicação passo a passo: [INSTRUCOES_CLAUDE.md](INSTRUCOES_CLAUDE.md).

## O que o painel mostra

- **Números do período** (hoje, semana, mês, mês anterior, 15 dias): leads, respondidos, sem resposta, contratos assinados, em fechamento, perdidos, parados e tempo até a primeira resposta. Com anúncio gravado, custo por lead e custo por contrato. Com ticket configurado, receita estimada.
- **Meta do mês**: realizado contra a meta, projeção pelo ritmo de dias úteis e quanto falta por dia.
- **Mesa de cada pessoa** (só administrador): leads, respostas da equipe, contratos, meta, em fechamento, parados e tempo de primeira resposta da equipe.
- **Funil por coluna**: cards abertos em cada coluna, com os parados destacados.
- **Perdas por motivo e parados**: o motivo de perda é o nome da coluna.
- **Drill-down**: cada número abre a lista de conversas que o gerou (nome, quadro, coluna, dona e datas).

## De onde sai cada número

| Número | Regra |
|---|---|
| Lead | Conversa cuja primeira fala do contato caiu no período. Mesma regra da Análise de leads. Fora: grupo, conversa importada e quadros fora do funil. |
| Respondido | Resposta da IA ou da equipe depois da primeira fala. |
| Contrato assinado | Nota de confirmação de assinatura (a mesma que a Análise de leads usa), contada pela data da assinatura. |
| Fechados entre os leads | Dos leads do período, quantos já assinaram até hoje. É a conversão de verdade. |
| Em fechamento | Sem assinatura, na coluna de elaboração ou de assinatura de contrato. Foto do momento. |
| Perdido | Card que entrou no período numa coluna de perda, mais as conversas apagadas pela limpeza automática (quando a tabela existir). |
| Parado | Card aberto no funil, sem mudar de coluna há N dias. |
| Tempo até a 1ª resposta | Mediana, em minutos, dos leads do período com resposta. |
| Custo | Gasto gravado em `rl_anuncios`, somando as linhas diárias do período. Sem bloco que cubra o período, não aparece. |
| Receita estimada | Contratos assinados vezes o ticket configurado por quadro. |

## O que o painel não sabe medir

- **Valor de venda.** O campo `valor` do CRM fica zerado. A receita só aparece como estimativa, com o ticket configurado. Não existe valor real para somar.
- **Ligações.** O CRM não guarda ligação de forma estruturada, e buscar a palavra no texto das mensagens conta errado: a IA oferece "retorno por ligação" como opção, e isso aparece em conversas que nunca tiveram ligação. Para contar, a equipe escreve uma nota que começa com a marca definida em `marca_ligacao`, por exemplo `LIGAÇÃO: atendeu, 5 min`. Sem essa nota, a seção mostra "não medido".
- **Histórico de colunas.** Parado e perdido usam a coluna atual e a data em que o card entrou nela. Se o card foi para perda e voltou, não aparece como perdido.
- **Motivo de perda além da coluna.** O motivo é o nome da coluna onde o card parou.
- **Quem atribuiu o lead.** Só a dona atual (`atendente_email`) é conhecida.
- **Fechado sem assinatura.** Por padrão, contrato na etapa sem nota de assinatura não conta como fechado. Isso é de propósito, mas pode parecer atraso para quem fechou no papel. Para mudar, `fechado_conta_etapa` em `comercial_metas.json`.

## Arquivos

- `backend/comercial.py`: router FastAPI, só leitura. Rotas `/api/comercial/painel` (admin), `/minha-mesa`, `/conversas`.
- `backend/comercial_metas.json`: metas, tickets, comissão e premissas. Tudo em branco por padrão.
- `frontend/Comercial.jsx`: a tela, uma para o admin e uma para a mesa pessoal.
- `teste_comercial.py`: teste com conversas fictícias num banco temporário, mais as rotas.
- `INSTRUCOES_CLAUDE.md`: passo a passo de aplicação.
