# Roteiro para o Claude Code aplicar o kit no sistema Braga & Braz

Você vai aplicar melhorias que já rodam em produção num sistema com a mesma base de código. O sistema de destino está em produção, com leads reais. As regras abaixo existem para não quebrar o atendimento.

## Antes de começar

1. **Confira se você está na versão que está no ar.** O código de produção fica na VPS do escritório. Se a cópia local estiver atrás, puxe antes de mexer.
2. **Leia o arquivo inteiro antes de editar.** Os trechos do kit dizem *onde* entram ("no lugar de...", "dentro de mover_etapa"). Ache o ponto no código real antes de colar.
3. **Backup do banco** antes de qualquer `ALTER TABLE`: `cp sistema_bragabraz.db sistema_bragabraz.db.bak_$(date +%Y%m%d_%H%M)`.

## Regras durante o trabalho

- **Uma melhoria por vez.** Aplicou, testou, subiu, conferiu. Só então a próxima.
- **Não mande WhatsApp para lead real em teste.** Para testar a IA, chame `gerar_resposta()` direto. Para testar envio, use uma conversa com o número de alguém da equipe. O `dry_run` do `/fluxos/processar` mostra o que sairia sem mandar.
- **Não apague nem renomeie** rotas, campos ou colunas que já existem. O kit só acrescenta. Onde ele *substitui* um trecho (07, 08, gatilhos dos fluxos), o arquivo diz exatamente qual.
- **Nomes que precisam bater com o banco do destino** estão marcados com `AJUSTAR` nos arquivos: nome do quadro, colunas, e-mails das vendedoras, ids de pipeline. Consulte o banco (`wa_pipelines`, `wa_stages`, `usuarios`) e preencha.
- **Os `.js` são referência.** A tela do destino é React (`frontend/src/pages/Atendimento.jsx`). Reimplemente o comportamento como componente; não injete o `.js` no `index.html`.
- **Nada de credencial no repositório.** Chaves novas (D-API, por exemplo) vão no `.env` do backend.

## Depois de cada melhoria

1. `python -m py_compile` nos arquivos alterados e `npm run build` se mexeu na tela.
2. Suba o backend local e teste a rota nova (curl ou tela).
3. Deploy pelo processo do escritório (`deploy/deploy.py`).
4. **Confira que o básico continua de pé:** chega mensagem nova pelo webhook (status 200), a IA responde, o quadro do CRM abre, os fluxos rodam no `dry_run`.

## Ordem e pontos de atenção por item

| Item | Arquivo principal | Atenção |
|---|---|---|
| 07 webhook | `chat/07_webhook_sem_perder_mensagem/` | O webhook atual usa `scalar_one_or_none()` na busca por telefone: troque pelas 3 buscas do arquivo. Depois rode a consulta de duplicatas do topo do arquivo e reporte quantas há. |
| 01 assinatura | `chat/01_assinatura_do_remetente/` | O banco grava o texto **sem** a assinatura. Persona da IA: "Jaqueline". |
| 08 IA | `chat/08_ia_ritmo_humano_e_limites/` | Ajuste `SAUDACAO_WHATSAPP_BUSINESS` para o começo exato da saudação configurada no celular do escritório (pergunte se não souber). |
| Fluxos | `fluxos/` | **Só ligue depois do Renato aprovar os textos.** Leia o aviso sobre `enviar_ja` em `gatilhos_por_coluna.py`. Cron em horário comercial. |
| 09 trava | `crm/09_trava_do_quadro/` | Precisa de `ALTER TABLE` (3 colunas). A partir daí, toda automação move card por `_mover_automatico`. |
| 10 régua | `crm/10_regua_de_contatos/` | A capa do card precisa de um selo na tela do quadro (número de contatos e alerta "lead esperando"). |
| 11 classificação | `crm/11_classificacao_no_contato/` | Chamar `lembrar()` em todo movimento e `recuperar()` quando nasce conversa nova. |
| 12 anúncio | `crm/12_origem_do_anuncio/` | Só faz sentido com anúncio "clique para WhatsApp" no Meta. |
| 13 dona | `crm/13_dona_do_lead/` | Combinar com o Renato quem são as vendedoras e a regra de distribuição antes de ligar o cron. |
| 02, 03 editar | `chat/02_editar_mensagem/` | Pela Z-API, implemente `zapi.editar_texto` conforme a documentação atual (não testado pela Z-API). |
| 04 vídeo | `chat/04_video_pela_camera/` | Precisa de `ffmpeg` na VPS e de `zapi.enviar_video`. |
| 14 a 16 ligação | `ligacao/` | Exige um número conectado na **D-API**: a Z-API não faz ligação pelo navegador. |

## Quando terminar

Liste para quem pediu a aplicação: o que foi aplicado, o que ficou pendente e por quê, e qualquer `AJUSTAR` que dependa de decisão do escritório.
