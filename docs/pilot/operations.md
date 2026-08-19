# Alertas e plantão do alpha

> Roadmap: R5-04  
> Owner: Pilot Operations / SRE  
> Status: regras implementadas; entrega de alertas e roster ainda inativos

## Contrato operacional

As regras em `config/pilot/alerts.v1.json` operam apenas sobre métricas técnicas agregadas. O
avaliador `guardian_core.operations.evaluate_alerts` não aceita screenshots, OCR, explicação ou
evidência. Ele exige janelas consecutivas para reduzir ruído, exceto sinais de privacidade e
exclusão, que disparam na primeira ocorrência.

O código e os testes provam a semântica das regras, mas não configuram um provedor externo de
monitoramento/paging. `alerts_active` e `roster_active` permanecem `false` até integração,
destinos reais, rota de escalonamento e drill terem evidência.

## Regras mínimas

| Regra | Gate | Severidade | Resposta |
|---|---:|---:|---|
| acesso cross-family | > 0 | `SEV0` | parar coleta; Security + Privacy |
| coleta proibida | > 0 | `SEV0` | parar coleta; Security + Privacy |
| disponibilidade da API | < 99,5% em 2 janelas | `SEV1` | pausar coorte; shadow only |
| ack de comando p95 | > 5 s em 2 janelas | `SEV1` | desabilitar intervenção; unlock prioritário |
| heartbeat mais antigo | > 90 s em 2 janelas | `SEV2` | marcar degradado; suporte |
| fila offline máxima | > 100 em 2 janelas | `SEV2` | investigar conectividade |
| falha de exclusão | > 0 | `SEV1` | pausar enrollment; Privacy Engineering |

Ausência de métrica não deve produzir “saudável”. O pipeline de observabilidade precisa alertar
se a própria ingestão parar; até essa integração existir, a janela depende de verificação humana
prévia e permanece inelegível para famílias reais.

## Plantão

Cada janela requer `PRIMARY`, `SECONDARY`, `SECURITY` e `PRIVACY`, com contato real mantido no
sistema operacional de plantão — nunca neste repositório. O handoff registra coorte, build,
configuração, modo, riscos abertos, alarmes silenciados, comandos pendentes e término planejado.

| Severidade | primary | secondary | expansão |
|---|---:|---:|---|
| `SEV0` | 5 min | 10 min | Security + Privacy imediatos |
| `SEV1` | 15 min | 30 min | Engineering/Product Safety conforme regra |
| `SEV2` | 4 h | próxima janela | Support/owner do componente |

Se primary não confirmar, a ferramenta deve escalar automaticamente. Falha de paging em `SEV0`
interrompe a janela e usa o canal de contingência previamente testado.

## Drill obrigatório

Antes da primeira janela e a cada mudança de provedor/rota:

1. injetar métrica sintética de acesso cross-family;
2. confirmar disparo, primary, secondary e Security/Privacy;
3. medir tempos sem incluir conteúdo sensível;
4. exercitar desabilitação de intervenção e rollback;
5. simular ausência de primary e canal indisponível;
6. registrar data, participantes, resultado e correções.

Um drill com falha mantém `roster_active = false`. A ativação só ocorre quando todas as regras têm
destino, runbook, owner e teste de entrega; regra silenciada precisa de expiração e aprovador.
