# Treinamento do suporte do alpha

> Roadmap: R5-03  
> Owner: Support Lead  
> Status: currículo pronto; roster ainda não treinado  
> Versão: 2026-08-19.1

## Resultado esperado

Após o treinamento, cada pessoa deve conseguir receber um relato sem copiar conteúdo sensível,
classificar severidade, orientar diagnóstico seguro, acionar kill switch/interrupção e encaminhar
uma classificação incorreta ou solicitação de exclusão ao owner correto. O curso não concede
acesso a evidências nem autoridade para decidir mérito jurídico ou clínico.

O gate em `config/pilot/support-training.v1.json` permanece fechado até existir conclusão nominal,
avaliação e validade para todas as pessoas escaladas na janela.

## Formato

- 60 minutos de conteúdo guiado;
- 45 minutos de exercícios com fixtures, sem dados de famílias;
- avaliação individual de 20 questões e cinco cenários obrigatórios;
- nota mínima de 85%, sem compensar falha em cenário obrigatório;
- reciclagem em 90 dias ou após mudança material de coleta, classificação ou operação.

## Módulos obrigatórios

### SUPPORT-01 — Limites do piloto

Explicar fases `TECHNICAL_TELEMETRY → SHADOW → ALERT`, proibição de `BLOCK` sem gates, capacidades
reais e diferença entre sintoma técnico, classificação e decisão familiar. O participante deve
recusar promessas de detecção total, monitoramento oculto ou resposta de emergência.

### SUPPORT-02 — Intake seguro e privacidade

Registrar apenas família/dispositivo pseudonimizados, horário, versão, modo, permissões, estado,
correlation ID e descrição do sintoma. Nunca pedir screenshot, transcrição, explicação da criança,
token ou credencial em ticket/chat. Evidência excepcional usa fluxo autorizado e auditado.

### SUPPORT-03 — Saúde do agente e operação offline

Ler heartbeat, idade do último evento, permissões, versão, fila e estado `DEGRADED`. Permissão
revogada, API indisponível ou classificador inválido não pode iniciar bloqueio novo. Não orientar
reinstalação antes de registrar estado, confirmar desbloqueios e avaliar revogação da credencial.

### SUPPORT-04 — Classificação incorreta

Distinguir falso positivo, direção incorreta, explicação incompreensível e política familiar.
Registrar categoria, versão, idioma/faixa de contexto, ação simulada e resultado familiar sem
copiar conteúdo. Encaminhar para triagem de Product Safety/Evals e preservar somente amostra mínima
já autorizada. Um relato isolado não autoriza alterar limiar ou reativar categoria.

### SUPPORT-05 — Bloqueio inesperado e kill switch

Tratar bloqueio fora do gate, comando de desbloqueio atrasado ou kill switch indisponível como
`SEV1` no mínimo. Priorizar desbloqueio, desabilitar intervenção, pausar coorte, confirmar ack e
acionar on-call. A equipe de suporte não executa comandos arbitrários no dispositivo.

### SUPPORT-06 — Privacidade, exposição e exclusão

Suspeita de acesso cross-family, evidência exposta ou coleta de câmera/microfone é `SEV0`: parar
coleta, revogar acessos e acionar Security/Privacy. Para retirada, autenticar por canal aprovado,
cessar coleta, revogar dispositivo e encaminhar exclusão verificável, incluindo objetos e filas.

## Avaliação prática

1. **NO_CONTENT_IN_TICKETS:** transformar um relato com screenshot oferecido em ticket técnico sem
   conteúdo e explicar o canal correto.
2. **SEV0_CROSS_FAMILY_ESCALATION:** identificar acesso cruzado, interromper e acionar os owners em
   até cinco minutos.
3. **FAIL_OPEN_NEW_BLOCKS:** responder a backend/classificador indisponível sem sugerir bloqueio.
4. **UNLOCK_PRIORITY:** diagnosticar decisão → comando → polling → ack e escalar ao ultrapassar SLO.
5. **VERIFIED_DELETION_HANDOFF:** registrar escopo, revogação, storage, banco, filas e comprovante.

O instrutor usa somente fixtures reproduzíveis e registra nota, cenários, versão, data e validade.
Falha recebe feedback e nova avaliação; nunca se registra conclusão retroativa.

## Critério de habilitação

`training_complete` só pode mudar para `true` quando todas as pessoas do roster ativo tiverem:

- módulos obrigatórios concluídos;
- nota ≥ 85%;
- cinco cenários aprovados;
- `completed_at` e `expires_at` válidos;
- aceite do código de minimização e escalonamento.

A existência deste currículo não significa que o suporte foi treinado.
