# Gates de risco, performance e lançamento

> Owner: Product Safety  
> Status: aprovado como baseline de engenharia; limiares quantitativos são provisórios até existirem evals representativos  
> Roadmap: R0-01 a R0-06

## 1. Semântica de ações — R0-01

| Ação | Efeito no dispositivo | Visibilidade | Quando usar |
|---|---|---|---|
| `IGNORE` | Nenhum | Métrica técnica agregada, sem incidente | Avaliação `SAFE` ou regra parental `ALLOW` |
| `LOG` | Nenhum | Registro técnico sem notificação familiar | Sinal baixo/médio, confiança insuficiente ou categoria sem gate |
| `ALERT` | Nenhum | Incidente e notificação ao responsável | Risco relevante com política `ALERT`, sem autorização para bloquear |
| `BLOCK` | Encerra e impede reabertura do app permitido pelo enforcer | Incidente, explicação à criança e notificação | Todos os gates de bloqueio atendidos |

`RiskAssessment` nunca contém essas ações. O Policy Engine combina assessment, política familiar e gate de lançamento para produzir `PolicyDecision`.

## 2. Condições obrigatórias para BLOCK

Um novo bloqueio só pode ocorrer quando todas as condições forem verdadeiras:

1. O assessment passou na validação de schema.
2. `risk = HIGH`.
3. A categoria e a direção são conhecidas.
4. A confiança atende ao limiar calibrado da categoria.
5. A política familiar está configurada como `BLOCK`.
6. A versão do classificador passou por eval e shadow mode para essa categoria.
7. O kill switch da categoria está desligado.
8. O aplicativo está na allowlist de enforcement e fora da denylist essencial.
9. Não ocorreu timeout, perda de backend ou erro do classificador.
10. Existe caminho operacional para contestação e desbloqueio.

Falha em qualquer condição reduz a ação para `ALERT` ou `LOG`. Falha técnica nunca cria um bloqueio novo.

## 3. Métricas de classificação — R0-02

As métricas devem ser calculadas por categoria, direção, idioma, versão do classificador e faixa de contexto.

| Métrica | Fórmula/definição | Gate provisório para ALERT | Gate provisório para BLOCK |
|---|---|---:|---:|
| Precisão | verdadeiros positivos / previsões positivas | ≥ 90% | ≥ 97% |
| Recall | verdadeiros positivos / positivos reais | reportar | ≥ 80% para o conjunto avaliado |
| Taxa de falso bloqueio | sessões seguras bloqueadas / sessões seguras | 0% porque não bloqueia | ≤ 0,10% |
| Contestação | incidentes contestados / incidentes exibidos | monitorar | ≤ 5% |
| Reversão | bloqueios revertidos / bloqueios decididos | n/a | ≤ 2% |
| Output inválido | respostas rejeitadas / análises | ≤ 0,50% | ≤ 0,10% |

Os números acima são metas de engenharia, não evidência atual de qualidade. Eles precisam ser revisados quando o guia de anotação e o conjunto de teste final forem congelados.

## 4. Orçamento do agente — R0-03

Medir em um Mac de referência definido antes da Etapa 1, com uma jornada de pelo menos quatro horas.

| Recurso | Meta inicial | Gate de piloto |
|---|---:|---:|
| CPU média | ≤ 3% | ≤ 5% |
| Pico de CPU por análise | ≤ 30% por até 2 s | ≤ 50% por até 3 s |
| Memória residente | ≤ 200 MB | ≤ 300 MB |
| Disco temporário | ≤ 100 MB | ≤ 250 MB |
| Rede diária sem incidentes | ≤ 10 MB/dispositivo | ≤ 25 MB/dispositivo |
| Impacto adicional de bateria | ≤ 5% em 8 h | ≤ 8% em 8 h |
| Capturas redundantes | ≤ 10% das observações enviadas à análise | ≤ 20% |

O agente deve aplicar backoff por inatividade e descartar material seguro para cumprir os limites.

## 5. SLOs iniciais — R0-04

| Indicador | Objetivo inicial | Medição |
|---|---:|---|
| Disponibilidade da API do piloto | 99,5% mensal | health check externo |
| Criação de incidente p95 | ≤ 2 s, sem upload | tracing do request |
| Comando de desbloqueio online p95 | ≤ 5 s | decisão do responsável → ack do agente |
| Heartbeat considerado saudável | ≤ 90 s de idade | timestamp do dispositivo |
| Comandos duplicados executados | 0 | idempotency key + auditoria |
| Restauração de backup do piloto | ≤ 4 h | exercício documentado |

O desbloqueio tem prioridade operacional superior a relatórios e agregações.

## 6. Matriz de liberação por categoria — R0-05

| Categoria | Estado inicial | Máximo permitido antes de evals | Requisito para BLOCK |
|---|---|---|---|
| `DANGEROUS_CONTACT` | `SHADOW` | `ALERT` | eval por progressão temporal + shadow mode aprovado |
| `ADULT_CONTENT` | `SHADOW` | `ALERT` | eval visual/contextual e falso positivo educacional aprovado |
| `HATE_SPEECH` | `SHADOW` | `ALERT` | eval por idioma, citação e direção do risco aprovado |
| `OTHER` | `LOG_ONLY` | `LOG` | categoria específica criada e avaliada |

Fixtures de demonstração podem simular `BLOCK` em ambiente `development`, mas isso não altera o estado de liberação para usuários reais.

## 7. Regra não negociável — R0-06

Nenhuma categoria pode entrar em bloqueio automático em staging, piloto ou produção sem:

- versão de dataset e classificador identificadas;
- relatório de eval reproduzível;
- shadow mode concluído na coorte definida;
- aprovação registrada por Product Safety e Engineering;
- kill switch operacional testado;
- plano de rollback e suporte comunicado.

Alterar modelo, prompt, taxonomia, direção ou limiar pode invalidar o gate e exigir nova avaliação.

