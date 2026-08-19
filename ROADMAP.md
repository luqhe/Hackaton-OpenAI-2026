# Guardian — Roadmap de Implementação até Produção

> Status: planejamento para implementação  
> Baseline: MVP local validado em 19/08/2026  
> Horizonte estimado: 18–24 semanas com equipe de 5–7 pessoas  
> Próximo marco: piloto técnico em um Mac real

## 1. Objetivo

Evoluir o Guardian de uma demonstração local reproduzível para um produto seguro, observável e pilotável com famílias convidadas, mantendo três princípios:

1. O classificador interpreta contexto, mas nunca controla diretamente o dispositivo.
2. Bloqueios automáticos só são habilitados depois de avaliação quantitativa e shadow mode.
3. Dados de crianças são minimizados, protegidos e excluídos por política verificável.

O roadmap está organizado por dependências técnicas e gates de segurança. Uma etapa só é considerada concluída quando seus critérios de saída forem atendidos.

## 2. Baseline atual

### Implementado

- [x] Contratos validados para observação, risco, política, incidente e comandos.
- [x] Separação entre `RiskAssessment` e `PolicyDecision`.
- [x] Risk Engine determinístico para fixtures controladas.
- [x] Policy Engine com severidade, confiança e ação configurável.
- [x] API FastAPI com SQLite e ciclo de vida de incidentes.
- [x] Deduplicação de incidentes e evidências.
- [x] Pedido de revisão, decisão do responsável e comando de desbloqueio.
- [x] Telemetria e relatório diário básicos.
- [x] Dashboard do responsável, visão da criança e editor de políticas.
- [x] Modo de enforcement simulado e proteção contra apps essenciais.
- [x] Primitivas iniciais de captura e enforcement no macOS.
- [x] Fixtures seguras e perigosas reproduzíveis.
- [x] Testes automatizados do fluxo local.

### Parcial

- [ ] Observer macOS integrado ao loop principal.
- [ ] Captura adaptativa baseada em mudança perceptual.
- [ ] Context buffer alimentado por observações reais.
- [ ] Evidência visual real e minimizada.
- [ ] Heartbeat representando o estado real do dispositivo.
- [ ] Operação offline e sincronização posterior.

### Não iniciado

- [ ] OCR e análise multimodal reais.
- [ ] Dataset, evals, calibração e shadow mode.
- [ ] Autenticação, autorização e isolamento entre famílias.
- [ ] Identidade e credenciais de dispositivo.
- [ ] Banco e armazenamento de evidências gerenciados.
- [ ] Criptografia, retenção e exclusão verificável.
- [ ] Aplicativo macOS assinado, notarizado e atualizável.
- [ ] Observabilidade, CI/CD, backups e recuperação.
- [ ] Piloto supervisionado e preparação formal para produção.

## 3. Caminho crítico

```text
Fundação e threat model
        ↓
Loop real no macOS
        ↓
Identidade + backend multi-tenant
        ↓
Pipeline de risco + evals
        ↓
Shadow mode
        ↓
Piloto supervisionado
        ↓
Hardening e produção
```

As etapas de experiência do usuário, compliance e operação devem avançar em paralelo, mas não podem antecipar os gates acima.

---

# ETAPA 0 — Fundação e gates do produto

**Duração estimada:** 1–2 semanas  
**Objetivo:** retirar ambiguidades antes de conectar captura real ou armazenar dados de usuários.

**Status da etapa:** implementação concluída; revisão formal e branch protection pendentes.

## Épico 0.1 — Métricas e regras de lançamento

- [x] `R0-01` Definir eventos que podem resultar em `LOG`, `ALERT` e `BLOCK`.
- [x] `R0-02` Definir métricas por categoria: precisão, recall, falso bloqueio e taxa de contestação.
- [x] `R0-03` Definir orçamento de performance do agente: CPU, memória, bateria e volume de rede.
- [x] `R0-04` Definir SLO inicial da API e latência máxima de desbloqueio.
- [x] `R0-05` Definir quais categorias podem entrar no piloto somente como alerta.
- [x] `R0-06` Registrar a regra: nenhuma categoria entra em bloqueio automático sem gate de avaliação aprovado.

## Épico 0.2 — Threat model e mapa de dados

- [x] `R0-07` Modelar ameaças do agente, API, dashboard, evidências e canal de comandos.
- [x] `R0-08` Mapear cada dado coletado, finalidade, localização, acesso e prazo de retenção.
- [x] `R0-09` Definir comportamento para comprometimento da conta do responsável.
- [x] `R0-10` Definir comportamento para adulteração ou remoção do agente pela criança.
- [x] `R0-11` Definir resposta a vazamento de evidência e revogação de dispositivo.
- [x] `R0-12` Criar registro inicial de riscos e responsáveis por mitigação.

## Épico 0.3 — Engenharia básica

- [x] `R0-13` Configurar CI para testes, análise estática e validação de contratos.
- [x] `R0-14` Adicionar formatação e lint de Python e JavaScript.
- [x] `R0-15` Definir versionamento de API e política de migração de banco.
- [x] `R0-16` Criar ADRs para agente nativo, banco, armazenamento e protocolo do dispositivo.
- [x] `R0-17` Criar ambientes separados: desenvolvimento, staging e produção.
- [x] `R0-18` Remover da interface alegações de recursos ainda não implementados ou marcá-las como planejadas.

## Critérios de saída

- [ ] Threat model revisado pela equipe.
- [x] Mapa de dados cobrindo captura, contexto, evidência, telemetria e auditoria.
- [x] Métricas e gates de bloqueio documentados e aplicados no runtime.
- [ ] CI obrigatório para merge — workflow criado; falta habilitar branch protection no GitHub.
- [x] Decisões arquiteturais principais registradas.

---

# ETAPA 1 — Agente macOS real

**Duração estimada:** 3–5 semanas  
**Dependência:** Etapa 0  
**Objetivo:** executar o vertical slice com observação real em um Mac de teste.

## Épico 1.1 — Helper nativo

- [x] `R1-01` Criar helper Swift usando ScreenCaptureKit.
- [x] `R1-02` Obter aplicativo e janela ativos por API nativa apropriada.
- [x] `R1-03` Integrar OCR local com Vision.
- [ ] `R1-04` Expor contrato versionado entre helper Swift e agente Python.
- [x] `R1-05` Tratar múltiplos monitores, mudança de resolução e suspensão.
- [x] `R1-06` Criar onboarding de permissões de Screen Recording e Accessibility/Automation.
- [x] `R1-07` Detectar permissão ausente ou revogada sem entrar em loop de falha.

## Épico 1.2 — Observação adaptativa

- [x] `R1-08` Substituir SHA-256 por perceptual hash ou diferença visual adequada.
- [x] `R1-09` Ignorar telas estáticas e alterações irrelevantes.
- [x] `R1-10` Implementar intervalo configurável e backoff por inatividade.
- [x] `R1-11` Construir context buffer por aplicativo e sessão.
- [x] `R1-12` Limitar o buffer a 1–2 minutos ou 5–10 observações significativas.
- [x] `R1-13` Excluir dados temporários seguros após análise.
- [x] `R1-14` Selecionar ou recortar somente a evidência mínima de incidente.

## Épico 1.3 — Enforcement e ciclo de vida

- [x] `R1-15` Integrar observer real ao `agent.main`.
- [x] `R1-16` Executar a política somente após validação do assessment.
- [x] `R1-17` Implementar monitor de reabertura de app bloqueado.
- [x] `R1-18` Preservar denylist permanente de processos essenciais.
- [x] `R1-19` Persistir estado local para reinício e operação offline.
- [x] `R1-20` Implementar fila local de incidentes e telemetria durante indisponibilidade da API.
- [x] `R1-21` Garantir desbloqueio idempotente e recuperação após crash.
- [x] `R1-22` Implementar heartbeat real com versão, permissões e saúde do agente.

## Épico 1.4 — Execução persistente e testes

- [x] `R1-23` Empacotar agente e helper para instalação de desenvolvimento.
- [x] `R1-24` Iniciar automaticamente após login/reinício.
- [x] `R1-25` Adicionar logs locais estruturados, sem conteúdo sensível bruto.
- [x] `R1-26` Criar testes E2E em macOS para captura, risco, bloqueio e desbloqueio.
- [x] `R1-27` Testar suspensão, perda de rede, backend indisponível e permissão revogada.
- [x] `R1-28` Medir consumo de CPU, memória, bateria, disco e rede.

## Critérios de saída

- Um Mac limpo executa `captura → análise → política → bloqueio → incidente → desbloqueio`.
- O fluxo sobrevive a reinício do agente e do computador.
- Falha técnica não cria bloqueio novo.
- Nenhum processo essencial pode ser encerrado.
- Dados seguros são descartados e evidências ficam limitadas ao incidente.
- Performance respeita os orçamentos definidos na Etapa 0.

---

# ETAPA 2 — Backend seguro e multi-tenant

**Duração estimada:** 4–6 semanas  
**Dependência:** contratos da Etapa 0; pode iniciar em paralelo à Etapa 1  
**Objetivo:** suportar famílias e dispositivos reais com isolamento e auditoria.

## Épico 2.1 — Identidade familiar

- [ ] `R2-01` Criar modelos `Account`, `Family`, `Membership`, `Child` e `Device`.
- [ ] `R2-02` Implementar autenticação segura do responsável.
- [ ] `R2-03` Implementar autorização por família em todas as operações.
- [ ] `R2-04` Remover IDs hardcoded da API e interface.
- [ ] `R2-05` Adicionar testes negativos de isolamento entre tenants.
- [ ] `R2-06` Implementar encerramento de sessões e revogação de acesso.

## Épico 2.2 — Identidade do dispositivo

- [ ] `R2-07` Criar fluxo de pareamento com código curto e expiração.
- [ ] `R2-08` Emitir credencial única por dispositivo.
- [ ] `R2-09` Armazenar credenciais no Keychain do macOS.
- [ ] `R2-10` Assinar ou autenticar requisições do agente.
- [ ] `R2-11` Implementar rotação, expiração e revogação.
- [ ] `R2-12` Associar comandos e incidentes ao dispositivo autenticado.

## Épico 2.3 — Persistência e evidências

- [ ] `R2-13` Migrar SQLite para PostgreSQL gerenciado.
- [ ] `R2-14` Adicionar migrations versionadas e rollback testado.
- [ ] `R2-15` Migrar evidências para object storage privado.
- [ ] `R2-16` Criptografar dados em trânsito e em repouso.
- [ ] `R2-17` Gerar URLs temporárias e autorizadas para evidências.
- [ ] `R2-18` Implementar política de retenção e exclusão automática.
- [ ] `R2-19` Implementar exportação e exclusão da conta/família.
- [ ] `R2-20` Garantir que backups respeitem o processo de expiração definido.

## Épico 2.4 — Comandos, eventos e auditoria

- [ ] `R2-21` Versionar protocolo de comandos do agente.
- [ ] `R2-22` Definir expiração, retry e idempotência de comandos.
- [ ] `R2-23` Implementar long polling ou canal persistente autenticado, se necessário.
- [ ] `R2-24` Registrar trilha de auditoria de política, evidência e decisão familiar.
- [ ] `R2-25` Impedir alteração silenciosa de registros de auditoria.
- [ ] `R2-26` Adicionar rate limiting e proteção contra abuso.

## Critérios de saída

- Testes provam isolamento entre famílias.
- Todo agente possui identidade revogável.
- Evidências nunca são públicas e expiram conforme política.
- Migrations, backup e restauração são executados em staging.
- Toda alteração relevante produz evento de auditoria.

---

# ETAPA 3 — Inteligência contextual e avaliação

**Duração estimada:** 5–8 semanas  
**Dependências:** Etapas 0 e 1  
**Objetivo:** substituir heurísticas de demo por um pipeline mensurável e seguro.

## Épico 3.1 — Pipeline de análise

- [ ] `R3-01` Criar interface versionada para providers de classificação.
- [ ] `R3-02` Separar análise local, análise remota e fallback.
- [ ] `R3-03` Combinar OCR, frame selecionado, app, janela e contexto temporal.
- [ ] `R3-04` Tratar conteúdo observado como dado não confiável.
- [ ] `R3-05` Isolar instruções do sistema contra prompt injection visível na tela.
- [ ] `R3-06` Validar output contra schema e rejeitar resposta incompleta.
- [ ] `R3-07` Implementar timeout, retry limitado e circuit breaker.
- [ ] `R3-08` Não enviar evidência remota quando o pré-filtro local concluir `SAFE` com regra confiável.

## Épico 3.2 — Dataset e evals

- [ ] `R3-09` Definir guia de anotação para categoria, direção, severidade e contexto.
- [ ] `R3-10` Construir dataset legalmente utilizável com casos seguros, ambíguos e perigosos.
- [ ] `R3-11` Incluir conteúdo educacional, jornalístico, citações, humor e falso positivo adversarial.
- [ ] `R3-12` Separar treino/desenvolvimento, calibração e teste final.
- [ ] `R3-13` Medir métricas por categoria, idade, aplicativo e direção do risco.
- [ ] `R3-14` Criar suite de regressão obrigatória para mudança de prompt/modelo.
- [ ] `R3-15` Versionar modelo, prompt, dataset e resultado de avaliação.

## Épico 3.3 — Calibração e decisão

- [ ] `R3-16` Calibrar confiança por categoria.
- [ ] `R3-17` Definir limiares distintos para `LOG`, `ALERT` e `BLOCK`.
- [ ] `R3-18` Implementar zona ambígua sem bloqueio automático.
- [ ] `R3-19` Medir taxa de contestação e reversão pelo responsável.
- [ ] `R3-20` Impedir que atualização de modelo habilite bloqueio sem nova aprovação do gate.
- [ ] `R3-21` Implementar kill switch por categoria e versão.

## Épico 3.4 — Shadow mode

- [ ] `R3-22` Registrar decisões simuladas sem intervir no dispositivo.
- [ ] `R3-23` Comparar heurística, modelo, política e decisão humana.
- [ ] `R3-24` Criar dashboard interno de falsos positivos e falsos negativos revisados.
- [ ] `R3-25` Executar shadow mode antes de ativar alertas reais.
- [ ] `R3-26` Executar nova janela de shadow mode antes de cada categoria entrar em `BLOCK`.

## Critérios de saída

- Evals são reproduzíveis e obrigatórios no CI de mudanças de risco.
- O pipeline rejeita output inválido e falha sem bloquear.
- Métricas por categoria atendem aos gates definidos na Etapa 0.
- Shadow mode demonstra estabilidade antes de qualquer intervenção automática.
- Kill switch foi testado em staging.

---

# ETAPA 4 — Experiência completa da família

**Duração estimada:** 3–5 semanas  
**Dependências:** identidade da Etapa 2; pode avançar em paralelo à Etapa 3  
**Objetivo:** transformar o dashboard da demo em produto utilizável e transparente.

## Épico 4.1 — Onboarding

- [ ] `R4-01` Criar conta e família.
- [ ] `R4-02` Cadastrar criança com configuração adequada à idade.
- [ ] `R4-03` Explicar claramente coleta, retenção e fronteiras de privacidade.
- [ ] `R4-04` Configurar políticas iniciais com defaults conservadores.
- [ ] `R4-05` Parear dispositivo e acompanhar permissões do macOS.
- [ ] `R4-06` Confirmar proteção somente após heartbeat real do agente.

## Épico 4.2 — Incidentes e decisão

- [ ] `R4-07` Exibir linha do tempo e evidências mínimas do incidente.
- [ ] `R4-08` Exibir por que a política foi acionada.
- [ ] `R4-09` Permitir contestação da criança sem expor conteúdo desnecessário.
- [ ] `R4-10` Notificar o responsável por canal configurável.
- [ ] `R4-11` Exibir confirmação de que o dispositivo executou o desbloqueio.
- [ ] `R4-12` Tratar dispositivo offline, comando expirado e decisão concorrente.

## Épico 4.3 — Transparência e acessibilidade

- [ ] `R4-13` Mostrar ao menor o que está ativo e quais dados foram compartilhados.
- [ ] `R4-14` Diferenciar claramente capacidade implementada de capacidade planejada.
- [ ] `R4-15` Implementar acessibilidade de teclado, leitor de tela, contraste e zoom.
- [ ] `R4-16` Revisar linguagem para faixas etárias distintas.
- [ ] `R4-17` Internacionalizar textos e datas.

## Épico 4.4 — Família e relatórios

- [ ] `R4-18` Suportar múltiplas crianças e dispositivos.
- [ ] `R4-19` Implementar relatório diário com dados reais de sessão.
- [ ] `R4-20` Evitar métricas que julguem produtividade ou estilo parental.
- [ ] `R4-21` Permitir ajustar retenção e canais de notificação.
- [ ] `R4-22` Criar fluxo de suporte, feedback e relato de classificação incorreta.

## Critérios de saída

- Uma família completa onboarding sem intervenção da equipe técnica.
- O status “protegido” corresponde a heartbeat recente e permissões válidas.
- Fluxos essenciais atendem à revisão de acessibilidade.
- A criança consegue entender e contestar uma intervenção.
- Nenhuma tela promete recurso ainda indisponível.

---

# ETAPA 5 — Alpha supervisionado

**Duração estimada:** 3–4 semanas  
**Dependências:** Etapas 1–4  
**Objetivo:** validar segurança, utilidade e operação com um grupo pequeno e convidado.

## Preparação

- [ ] `R5-01` Definir protocolo do piloto, suporte e critérios de interrupção.
- [ ] `R5-02` Concluir revisão de consentimento, privacidade e termos aplicáveis ao piloto.
- [ ] `R5-03` Treinar suporte para incidentes técnicos e classificações incorretas.
- [ ] `R5-04` Configurar alertas operacionais e plantão durante janelas de teste.
- [ ] `R5-05` Instrumentar funil de onboarding, saúde do agente e latência de comandos.
- [ ] `R5-06` Testar remoção completa dos dados de uma família piloto.

## Execução progressiva

- [ ] `R5-07` Iniciar somente com telemetria técnica e shadow mode.
- [ ] `R5-08` Habilitar alertas sem bloqueio para categorias aprovadas.
- [ ] `R5-09` Revisar eventos com processo controlado e acesso mínimo.
- [ ] `R5-10` Medir falso positivo, contestação, compreensão e confiança familiar.
- [ ] `R5-11` Habilitar bloqueio apenas em categoria e coorte aprovadas pelo gate.
- [ ] `R5-12` Manter kill switch e rollback disponíveis durante todo o piloto.

## Critérios de saída

- Nenhum incidente crítico de privacidade ou isolamento.
- Saúde e performance do agente atendem aos orçamentos.
- Latência de desbloqueio atende ao SLO definido.
- Métricas de classificação permanecem dentro dos gates.
- Feedback confirma que intervenção e transparência são compreensíveis.
- Problemas encontrados possuem correção e regressão automatizada.

---

# ETAPA 6 — Hardening de produção

**Duração estimada:** 4–6 semanas  
**Dependência:** piloto concluído  
**Objetivo:** tornar instalação, backend e operação confiáveis para lançamento controlado.

## Épico 6.1 — Distribuição macOS

- [ ] `R6-01` Assinar binários e instalador.
- [ ] `R6-02` Notarizar e validar instalação em versões suportadas do macOS.
- [ ] `R6-03` Implementar atualização automática assinada e rollback.
- [ ] `R6-04` Proteger canal de atualização contra downgrade e adulteração.
- [ ] `R6-05` Definir matriz de compatibilidade e política de fim de suporte.
- [ ] `R6-06` Criar desinstalação segura e verificável.

## Épico 6.2 — Confiabilidade e observabilidade

- [ ] `R6-07` Criar dashboards de API, agente, comandos, armazenamento e classificação.
- [ ] `R6-08` Definir SLOs, alertas e error budgets.
- [ ] `R6-09` Implementar tracing e correlação sem registrar conteúdo sensível.
- [ ] `R6-10` Testar backup, restauração e recuperação de desastre.
- [ ] `R6-11` Executar testes de carga, degradação e indisponibilidade de dependências.
- [ ] `R6-12` Implementar feature flags e rollout gradual.

## Épico 6.3 — Segurança e privacidade

- [ ] `R6-13` Realizar revisão de arquitetura de segurança.
- [ ] `R6-14` Executar pentest do agente, API e dashboard.
- [ ] `R6-15` Corrigir achados críticos e altos antes do lançamento.
- [ ] `R6-16` Finalizar política de retenção, exclusão, exportação e acesso interno.
- [ ] `R6-17` Formalizar resposta a incidentes e comunicação.
- [ ] `R6-18` Concluir revisão jurídica e de privacidade aplicável aos mercados de lançamento.
- [ ] `R6-19` Documentar subprocessadores e fluxo internacional de dados, quando aplicável.

## Épico 6.4 — Operação de produto

- [ ] `R6-20` Definir suporte, escalonamento e tempos de resposta.
- [ ] `R6-21` Criar runbooks para bloqueio incorreto, agente offline e evidência indisponível.
- [ ] `R6-22` Monitorar custo por dispositivo e por incidente.
- [ ] `R6-23` Definir limites de plano sem comprometer funções de segurança.
- [ ] `R6-24` Preparar status page, comunicação de manutenção e rollback operacional.

## Gate de produção

- Aplicativo assinado, notarizado, atualizável e removível.
- Pentest sem achados críticos ou altos pendentes.
- Restauração de backup e rollback testados.
- SLOs e alertas operacionais ativos.
- Retenção e exclusão verificadas ponta a ponta.
- Documentação jurídica, de privacidade e suporte aprovada.
- Bloqueios automáticos limitados às categorias aprovadas por evals e piloto.

---

# ETAPA 7 — Pós-lançamento

**Objetivo:** expandir capacidades somente após estabilidade do núcleo.

- [ ] `R7-01` Expandir taxonomia uma categoria por vez, repetindo eval e shadow mode.
- [ ] `R7-02` Adicionar novos idiomas com dataset e métricas próprios.
- [ ] `R7-03` Avaliar agente Windows.
- [ ] `R7-04` Avaliar Android/iOS conforme restrições das plataformas.
- [ ] `R7-05` Aprimorar análise de mídia e áudio do sistema com coleta mínima.
- [ ] `R7-06` Adicionar integrações de notificação e suporte.
- [ ] `R7-07` Avaliar plano comercial, cobrança e administração de assinatura.
- [ ] `R7-08` Publicar relatórios de transparência e métricas agregadas de segurança.

---

## 4. Marcos

| Marco | Previsão | Resultado |
|---|---:|---|
| M0 — Fundação aprovada | Semana 2 | Gates, threat model, CI e ADRs |
| M1 — Vertical slice real | Semana 6 | Fluxo completo em Mac real |
| M2 — Backend pilotável | Semana 10 | Famílias e dispositivos isolados |
| M3 — Shadow mode validado | Semana 14 | Pipeline contextual mensurado |
| M4 — Alpha concluído | Semana 18 | Uso supervisionado e gates revisados |
| M5 — Produção controlada | Semana 22–24 | Hardening, segurança e operação aprovados |

As previsões assumem execução paralela das Etapas 1/2 e 3/4. Uma equipe menor ou dependências jurídicas externas podem ampliar o horizonte.

## 5. Próximo sprint recomendado

**Meta do sprint:** provar observação real e estabelecer controles mínimos de engenharia.

### P0

- [x] `R0-01` Definir ações e gates por categoria.
- [x] `R0-07` Criar threat model inicial.
- [x] `R0-08` Criar mapa de dados.
- [x] `R0-13` Configurar CI com os testes existentes.
- [x] `R0-18` Corrigir alegações de recursos não implementados na interface.
- [ ] `R1-01` Criar spike de ScreenCaptureKit em Swift.
- [ ] `R1-02` Validar captura de app e janela ativos.
- [ ] `R1-03` Validar OCR com Vision em fixture visual local.
- [ ] `R1-04` Prototipar contrato helper Swift → Python.

### P1

- [ ] `R1-08` Comparar alternativas de change detection.
- [ ] `R1-11` Integrar observações reais ao context buffer.
- [ ] `R1-26` Criar primeiro teste E2E executável somente no macOS.
- [ ] `R2-01` Propor modelo de tenancy e identidade.

### Resultado esperado

Ao final do sprint, o sistema deve capturar uma janela real, extrair texto localmente, converter o resultado para `Observation` e executar o Risk Engine sem depender de JSON escrito manualmente.

## 6. Composição mínima da equipe

| Papel | Responsabilidades principais |
|---|---|
| Engenharia macOS | Helper nativo, permissões, instalação e enforcement |
| Backend/segurança | Identidade, tenancy, dados, comandos e auditoria |
| ML/evals | Pipeline contextual, dataset, calibração e shadow mode |
| Frontend/produto | Onboarding, incidentes, transparência e acessibilidade |
| QA/SRE | E2E, CI/CD, observabilidade, carga e recuperação |
| Produto/design | Políticas, linguagem, testes com famílias e métricas |
| Privacidade/jurídico | Consentimento, retenção, contratos e mercados suportados |

As duas últimas funções podem começar parciais, mas precisam participar antes do piloto.

## 7. Definition of Ready

Uma tarefa está pronta para implementação quando possui:

- problema e usuário afetado;
- comportamento esperado e estados de erro;
- dependências identificadas;
- implicações de privacidade e segurança avaliadas;
- critérios de aceite testáveis;
- telemetria necessária definida;
- owner e estimativa acordados.

## 8. Definition of Done

Uma tarefa só está concluída quando:

- código e contratos foram revisados;
- testes automatizados relevantes passam;
- falhas e comportamento offline foram considerados;
- logs não expõem conteúdo sensível;
- documentação operacional foi atualizada;
- métricas e alertas necessários existem;
- compatibilidade e rollback foram avaliados;
- nenhuma alegação de interface excede a capacidade implementada.

## 9. Regras de priorização

1. Segurança e reversibilidade antes de amplitude de funcionalidades.
2. Evals antes de novos bloqueios automáticos.
3. Identidade e isolamento antes de dados de famílias reais.
4. Observabilidade antes de ampliar o piloto.
5. Monólito modular antes de microserviços.
6. Uma plataforma confiável antes de novas plataformas.
7. Uma categoria bem validada antes de expandir a taxonomia.

## 10. Fora do caminho crítico atual

Os itens abaixo não devem deslocar capacidade das Etapas 0–6:

- checkout e cobrança;
- migração prematura para microserviços;
- Kubernetes, Kafka ou vector database sem caso comprovado;
- suporte simultâneo a várias plataformas;
- treinamento de modelo próprio antes de existir um programa de evals;
- expansão de taxonomia antes da validação de `DANGEROUS_CONTACT`;
- migração de frontend apenas por preferência tecnológica;
- captura contínua de áudio sem necessidade e controles definidos.

---

Este roadmap deve ser atualizado ao final de cada marco. Mudanças que alterem coleta, retenção, enforcement ou categorias de risco precisam passar novamente pelos gates de segurança e avaliação correspondentes.
