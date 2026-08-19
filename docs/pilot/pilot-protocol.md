# Protocolo do alpha supervisionado

> Roadmap: R5-01  
> Owner: Pilot Operations  
> Status: rascunho interno; o piloto permanece desabilitado

## Objetivo e limites

O alpha existe para verificar operação, transparência e segurança com uma coorte pequena e
convidada. A primeira fase aceita somente telemetria técnica e decisões em `SHADOW`: não envia
alertas familiares e não bloqueia aplicativos. O arquivo executável
`config/pilot/protocol.v1.json` mantém `pilot_enabled = false` até todos os gates de entrada
terem evidência registrada.

Este protocolo não autoriza coleta com famílias reais, não substitui revisão jurídica ou de
privacidade e não transforma o MVP single-family em produto pilotável. Identidade,
autorização por família, credencial revogável do dispositivo, storage privado, exclusão
verificável e aprovações registradas continuam pré-requisitos.

## Coorte e progressão

- até 10 famílias convidadas, com responsável e dispositivo identificados;
- janelas assistidas de no máximo 120 minutos durante a fase inicial;
- um dispositivo por família na primeira janela;
- progressão independente por coorte: `TECHNICAL_TELEMETRY → SHADOW → ALERT`;
- `BLOCK` continua proibido até os gates quantitativos de `docs/product/release-gates.md`;
- cada progressão exige registro de versão, período, responsáveis, métricas e rollback.

## Gate de entrada da sessão

O coordenador da janela deve registrar, antes de iniciar:

1. coorte, famílias e dispositivos participantes;
2. confirmação de consentimento aplicável e aprovações jurídica/privacidade vigentes;
3. build e configuração implantados, inclusive kill switches;
4. saúde dos agentes, permissões e fila offline;
5. dashboards, alertas e plantonistas alcançáveis;
6. teste sintético de incidente, comando, ack e exclusão;
7. canal de suporte comunicado à família;
8. horário de início, término planejado e owner da decisão de interrupção.

Se qualquer item estiver ausente, a janela não começa. Indisponibilidade de backend ou
permissão revogada degrada a observação e nunca cria um bloqueio novo.

## Atendimento e severidades

| Nível | Exemplo | Confirmação inicial | Autoridade |
|---|---|---:|---|
| `SEV0` | exposição/cross-tenant ou coleta proibida | 5 min | qualquer plantonista interrompe tudo |
| `SEV1` | bloqueio inesperado, kill switch/rollback falho, SLO crítico | 15 min | on-call pausa coorte/intervenções |
| `SEV2` | agente degradado sem risco de dados ou bloqueio | 4 h | suporte técnico coordena correção |
| `SEV3` | dúvida, feedback ou problema cosmético | 1 dia | suporte registra e prioriza |

O suporte coleta apenas identificadores técnicos, horários, versão e sintomas. Conteúdo de
tela, explicação da criança e evidência não devem ser copiados para chat, e-mail ou ticket.
Acesso excepcional à evidência requer finalidade, autorização mínima e trilha de auditoria.

## Interrupção e contenção

As condições canônicas estão em `config/pilot/protocol.v1.json`. Em caso de dúvida, preservar
a família prevalece sobre manter a janela:

1. declarar severidade e interromper a coleta/coorte indicada;
2. desabilitar `BLOCK` e `ALERT` antes de investigar classificação;
3. revogar acessos/credenciais quando houver suspeita de exposição;
4. confirmar que comandos de desbloqueio pendentes foram entregues;
5. preservar somente logs técnicos redigidos e IDs necessários;
6. informar participantes de forma factual, sem especular causa;
7. seguir o playbook correspondente e abrir registro de incidente;
8. documentar correção, regressão, impacto e decisão de descarte/retenção.

Nenhuma família nova entra enquanto um `SEV0` estiver aberto. Uma coorte afetada não retoma
até a combinação de owners indicada em `restart_requires` registrar a revisão.

## Encerramento e rollback da janela

- retornar todas as categorias ao estado anterior ou `SHADOW`;
- confirmar heartbeat e ausência de comandos pendentes;
- revogar credenciais temporárias e acesso excepcional;
- verificar TTL, exclusões solicitadas e outbox local;
- registrar métricas agregadas, interrupções, tickets e desvios;
- coletar feedback sem solicitar conteúdo sensível;
- comunicar término e canal de acompanhamento aos participantes.

O rollback válido é uma configuração previamente testada. Reverter apenas o backend sem
confirmar estado do agente e comandos não encerra a janela.

## Critério para considerar R5-01 operacional

O protocolo pode ser exercitado internamente com fixtures. Abrir o alpha para famílias reais
exige todos os gates de entrada, lista nominal de suporte/on-call e aprovação do pacote de
consentimento, privacidade e termos. A existência deste documento, isoladamente, não comprova
essas condições.
