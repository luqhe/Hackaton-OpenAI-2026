# R3 — Pipeline contextual, evals e shadow mode

> Implementação: `guardian.classifier.v1`
>
> Estado de liberação: classificação e baseline sintético funcionais; bloqueio real continua desligado

## Fluxo implementado

```text
Observation + OCR + frame selecionado + mensagens recentes
                         │
                         ▼
               ContextBundle não confiável
                         │
              pré-filtro local versionado
                 │                   │
       SAFE por regra confiável      contexto relevante
       (não envia evidência)         │
                 │                   ▼
                 │          provider remoto versionado
                 │             timeout + 1 retry
                 │                   │
                 │          schema válido? ── não ──┐
                 │                   │               │
                 └───────────────────┴──────── fallback conservador
                                                   │
                                                   ▼
                              calibração → política → gates exatos → kill switch
                                                   │
                                      shadow: registra, nunca intervém
```

O contrato `ClassifierProvider` fixa a versão da interface e exige identidade de provider, modelo e prompt. O contexto serializa aplicativo, janela, OCR, texto visível, hash do frame e mensagens em ordem temporal. Todo esse bloco é delimitado como dado não confiável; nenhuma string observada entra nas instruções de sistema.

## Falha segura

- Timeout e indisponibilidade recebem no máximo uma repetição por análise.
- Três falhas consecutivas abrem o circuit breaker; após a janela de recuperação, uma nova tentativa é permitida.
- Refusal, JSON inválido, campos extras, categoria/direção incoerentes ou resposta incompleta são rejeitados.
- O fallback preserva um sinal local para revisão, reduz `HIGH` para `MEDIUM` e marca o resultado como inelegível para bloqueio.
- Um `SAFE` só evita a chamada remota quando uma regra local identificada é confiável; ausência de sinal em um frame desconhecido não basta.

## Calibração e liberação

`config/risk-controls.v1.json` mantém curvas monotônicas e limiares distintos de `LOG`, `ALERT` e `BLOCK` por categoria. A faixa entre `LOG` e `BLOCK` é ambígua e nunca bloqueia automaticamente.

Um `BLOCK` requer simultaneamente:

1. risco `HIGH` acima do limiar calibrado;
2. pipeline elegível, sem fallback;
3. política familiar compatível;
4. aprovação para a combinação exata de interface, modelo, prompt e dataset;
5. janela de shadow `STAGING_COHORT` aprovada para a categoria e versão;
6. aprovação de Product Safety e Engineering;
7. kill switch inativo.

Trocar qualquer versão faz a igualdade da aprovação falhar. Os kill switches versionados por categoria permanecem ativos no baseline atual.

## Dataset e regressão

O arquivo `evals/dataset-v1.jsonl` contém somente cenários sintéticos originais e separa `development`, `calibration` e `test`. Inclui casos seguros, ambíguos e perigosos; português/inglês; contexto educacional, jornalístico, citação, humor, prompt injection e progressão temporal.

`scripts/run_r3_evals.py --check` executa o teste final congelado e falha o CI quando precisão, recall, falso positivo, output inválido ou precisão por categoria ultrapassam os limites registrados. O relatório inclui cortes por categoria, faixa etária, aplicativo e direção.

## Shadow mode

Cada registro compara assessment local, assessment do modelo, ação da política, ação simulada e revisão humana. Apenas hashes de contexto entram no log; o conteúdo observado não é duplicado. O schema fixa `actual_intervention=false`.

O baseline em `evals/results/` foi executado sobre o conjunto sintético. Ele serve como prova reproduzível do mecanismo e como dashboard interno de QA, mas `release_eligible=false`: não substitui uma coorte representativa em staging. Cada categoria e nova combinação de versões precisa de outra janela antes de receber uma aprovação de `BLOCK`.

## Matriz de rastreabilidade

| Issues | Evidência principal |
|---|---|
| R3-01–R3-03 | `contracts.py`, `context.py`, `providers.py`, `pipeline.py` |
| R3-04–R3-08 | delimitação não confiável, prompt estático, schema estrito, retry/circuit breaker e short-circuit seguro |
| R3-09–R3-12 | guia de anotação, manifesto e dataset com três splits |
| R3-13–R3-15 | `evaluation.py`, gate congelado, CI e relatórios versionados |
| R3-16–R3-21 | `calibration.py` e `risk-controls.v1.json` |
| R3-22–R3-26 | `shadow.py`, baseline, dashboard e gates exatos por categoria/versão |
