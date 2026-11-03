"""Fluxos de cadencia para Holding Familiar e Direito de Familia (+ reaquecimento anual).

RASCUNHO PARA APROVACAO. Os textos foram escritos a partir do padrao de atendimento de
Holding enviado pelo escritorio (perguntas de qualificacao e lista de documentos). Direito
de Familia ainda nao tem roteiro do escritorio: os textos dessa area sao sugestao e a lista
de documentos precisa ser conferida pela equipe juridica antes de ligar.

Regras seguidas em todos os textos (Provimento 205/2021 da OAB):
  - nao promete resultado, prazo nem valor;
  - nao fala de preco nem de condicao de pagamento;
  - nao usa depoimento de cliente nem caso ganho;
  - sem emoji (padrao do atendimento do escritorio).

COMO USAR: junte este dicionario ao FLUXOS de routers/atendimento.py:

    from .fluxos_holding_familia import FLUXOS_AREAS     # ou cole os itens direto
    FLUXOS.update(FLUXOS_AREAS)

O motor que ja existe (POST /fluxos/processar, cron) cuida do resto: manda um passo por
rodada, para sozinho quando o lead responde e nao passa de 20 envios por rodada.
Os nomes (chaves) tem no maximo 30 letras, que e o tamanho da coluna wa_fluxos.tipo.
{nome} vira o primeiro nome do contato.

Gatilhos sugeridos (ver gatilhos_por_coluna.py):
  card entra em "Proposta"  -> <area>_pos_consulta  (regua de fechamento depois da consulta)
  card entra em "Fechado"   -> <area>_documentos    (pede os documentos da contratacao)
  lead parou de responder   -> <area>_retomar       (ligado na mao pela equipe, no card)
  card entra em "Perdido"   -> reaquecimento_anual  (crie a coluna "Perdido" no quadro)
"""

H = 1          # 1 hora
D = 24         # 1 dia, em horas

FLUXOS_AREAS = {

    # =====================================================================
    # HOLDING FAMILIAR / PLANEJAMENTO PATRIMONIAL
    # =====================================================================
    'holding_retomar': {
        'nome': 'Holding - retomar conversa',
        'descricao': 'Lead de holding que parou de responder durante a qualificacao. 3 toques em 6 dias.',
        'passos': [
            {'ordem': 1, 'apos_horas': 1 * D, 'texto': (
                "Olá, {nome}! Ficou alguma dúvida sobre o planejamento patrimonial da sua família? "
                "Se preferir, me conte em poucas palavras o que você gostaria de organizar que eu sigo daqui.")},
            {'ordem': 2, 'apos_horas': 3 * D, 'texto': (
                "{nome}, muitas famílias deixam esse assunto para depois e só olham para ele quando "
                "acontece um imprevisto. Organizar antes costuma trazer mais tranquilidade para todos. "
                "Quando puder, me responda e combinamos o próximo passo.")},
            {'ordem': 3, 'apos_horas': 6 * D, 'texto': (
                "{nome}, este é meu último lembrete por aqui para não incomodar. "
                "Quando quiser retomar a conversa sobre o patrimônio da sua família, é só responder esta mensagem.")},
        ],
    },

    'holding_pos_consulta': {
        'nome': 'Holding - acompanhamento apos a consulta',
        'descricao': 'Depois da consulta estrategica (card em Proposta). 5 toques em 15 dias.',
        'passos': [
            {'ordem': 1, 'apos_horas': 4 * H, 'texto': (
                "{nome}, obrigado pelo tempo na nossa conversa de hoje. "
                "Ficou alguma dúvida sobre o que conversamos? Estou por aqui para esclarecer.")},
            {'ordem': 2, 'apos_horas': 2 * D, 'texto': (
                "{nome}, uma dúvida comum depois da consulta: a holding não muda a rotina da família. "
                "Os bens continuam sendo usados como sempre; o que muda é a forma como estão organizados "
                "e como vão passar para a próxima geração. Se quiser, explico melhor algum ponto.")},
            {'ordem': 3, 'apos_horas': 5 * D, 'texto': (
                "{nome}, se for importante para você, podemos fazer uma conversa rápida com os demais "
                "membros da família que vão participar da decisão. Assim todos ouvem a mesma explicação. "
                "Me diga um dia e horário que funcione.")},
            {'ordem': 4, 'apos_horas': 9 * D, 'texto': (
                "{nome}, passando para saber como está a decisão sobre o planejamento patrimonial. "
                "Se algo travou, me conte o que é que a gente vê juntos.")},
            {'ordem': 5, 'apos_horas': 15 * D, 'texto': (
                "{nome}, vou encerrar o acompanhamento por aqui para não ser insistente. "
                "Quando a família quiser seguir com o planejamento, é só me chamar nesta conversa.")},
        ],
    },

    'holding_documentos': {
        'nome': 'Holding - documentos da contratacao',
        'descricao': 'Dispara quando o card entra em Fechado: pede os documentos para estruturar a holding.',
        'passos': [
            {'ordem': 1, 'apos_horas': 0, 'texto': (
                "Que bom ter a sua família conosco, {nome}! Para começarmos a estruturação, vamos precisar de:\n\n"
                "1) Documentos pessoais (RG e CPF) de quem vai participar da holding\n"
                "2) Matrículas atualizadas dos imóveis\n"
                "3) IPTU ou documentos dos demais bens\n"
                "4) Contrato social, se houver empresa envolvida\n"
                "5) Uma relação dos bens da família\n\n"
                "Pode mandar por aqui mesmo, aos poucos, conforme for reunindo.")},
            {'ordem': 2, 'apos_horas': 2 * D, 'texto': (
                "{nome}, conseguiu separar os documentos? Se alguma matrícula estiver difícil de conseguir, "
                "me avise que eu explico como pedir a certidão atualizada no cartório.")},
            {'ordem': 3, 'apos_horas': 5 * D, 'texto': (
                "{nome}, seguimos aguardando os documentos para avançar com a estruturação. "
                "Se preferir, mande primeiro os documentos pessoais e a relação de bens, e o restante depois.")},
            {'ordem': 4, 'apos_horas': 10 * D, 'texto': (
                "{nome}, o trabalho da holding está aguardando a documentação para andar. "
                "Se tiver qualquer dificuldade, me chame que a equipe ajuda a organizar.")},
        ],
    },

    # =====================================================================
    # DIREITO DE FAMILIA  (sem roteiro do escritorio ainda: textos para aprovacao)
    # Tom: acolhedor e discreto. A pessoa costuma estar num momento dificil
    # (separacao, guarda, pensao, inventario). Nunca pressionar.
    # =====================================================================
    'familia_retomar': {
        'nome': 'Familia - retomar conversa',
        'descricao': 'Lead de familia que parou de responder. 3 toques em 7 dias, tom acolhedor.',
        'passos': [
            {'ordem': 1, 'apos_horas': 1 * D, 'texto': (
                "Olá, {nome}. Sei que esses assuntos de família nem sempre são fáceis de falar. "
                "Fico à disposição para continuar no seu tempo, por aqui mesmo.")},
            {'ordem': 2, 'apos_horas': 3 * D, 'texto': (
                "{nome}, se preferir conversar por ligação em vez de mensagem, me diga um horário "
                "e a equipe liga para você. Tudo o que você contar fica entre você e o escritório.")},
            {'ordem': 3, 'apos_horas': 7 * D, 'texto': (
                "{nome}, vou deixar de mandar mensagens para respeitar o seu momento. "
                "Quando quiser retomar, é só responder aqui.")},
        ],
    },

    'familia_pos_consulta': {
        'nome': 'Familia - acompanhamento apos a consulta',
        'descricao': 'Depois da consulta (card em Proposta). 4 toques em 12 dias.',
        'passos': [
            {'ordem': 1, 'apos_horas': 4 * H, 'texto': (
                "{nome}, obrigado pela confiança em conversar com a gente hoje. "
                "Se lembrar de algo que não perguntou na consulta, pode mandar por aqui.")},
            {'ordem': 2, 'apos_horas': 2 * D, 'texto': (
                "{nome}, passando para saber como você está e se ficou alguma dúvida "
                "sobre os caminhos que conversamos.")},
            {'ordem': 3, 'apos_horas': 6 * D, 'texto': (
                "{nome}, sabemos que decisões de família levam tempo. Quando se sentir pronto(a) "
                "para seguir, me avise e a equipe organiza o próximo passo com você.")},
            {'ordem': 4, 'apos_horas': 12 * D, 'texto': (
                "{nome}, vou encerrar o acompanhamento por aqui. "
                "Sempre que precisar, é só chamar nesta conversa.")},
        ],
    },

    'familia_documentos': {
        'nome': 'Familia - documentos da contratacao',
        'descricao': 'Dispara quando o card entra em Fechado. LISTA DE DOCUMENTOS A CONFERIR com a equipe por tipo de caso.',
        'passos': [
            {'ordem': 1, 'apos_horas': 0, 'texto': (
                "{nome}, obrigado por confiar o seu caso ao escritório. Para darmos andamento, vamos precisar de:\n\n"
                "1) RG e CPF\n"
                "2) Comprovante de residência\n"
                "3) Certidão de casamento ou documento da união estável\n"
                "4) Certidão de nascimento dos filhos, se houver\n"
                "5) Comprovantes de renda e relação de bens, se o caso envolver pensão ou partilha\n\n"
                "Pode mandar por aqui, aos poucos. Se tiver dúvida sobre algum item, me pergunte.")},
            {'ordem': 2, 'apos_horas': 2 * D, 'texto': (
                "{nome}, conseguiu reunir os documentos? Se algum estiver difícil de achar, "
                "me avise que eu explico como conseguir a segunda via.")},
            {'ordem': 3, 'apos_horas': 5 * D, 'texto': (
                "{nome}, seguimos aguardando os documentos para avançar com o seu caso. "
                "Pode começar pelo RG, CPF e comprovante de residência.")},
            {'ordem': 4, 'apos_horas': 10 * D, 'texto': (
                "{nome}, o seu caso está aguardando a documentação para andar. "
                "Qualquer dificuldade, me chame que a equipe ajuda.")},
        ],
    },

    # =====================================================================
    # TODAS AS AREAS
    # =====================================================================
    'reaquecimento_anual': {
        'nome': 'Reaquecimento anual',
        'descricao': 'Lead perdido ou que preferiu deixar para depois: 3 toques em 4, 8 e 12 meses. Para se responder.',
        'passos': [
            {'ordem': 1, 'apos_horas': 120 * D, 'texto': (
                "Olá, {nome}! Faz alguns meses que conversamos. "
                "Se o assunto voltou a ser prioridade, fico à disposição para retomar.")},
            {'ordem': 2, 'apos_horas': 240 * D, 'texto': (
                "{nome}, passando para lembrar que o escritório segue à disposição. "
                "Se a sua situação mudou, me conte por aqui.")},
            {'ordem': 3, 'apos_horas': 365 * D, 'texto': (
                "{nome}, faz um ano da nossa conversa. Se em algum momento precisar, "
                "é só responder esta mensagem que a equipe retoma com você.")},
        ],
    },
}
