# Guardian — Contexto Definitivo do Projeto

> Hackathon OpenAI · Trilha Educação e Empregabilidade · MVP macOS · Equipe de 4 pessoas · 5 horas

## 1. Visão do produto

**Guardian** é uma plataforma de proteção e letramento digital para crianças e adolescentes. Responsáveis assinam um plano mensal, cadastram seus filhos, definem políticas de proteção e conectam os dispositivos das crianças à conta familiar.

A proposta não é construir apenas mais um bloqueador de aplicativos. O Guardian funciona como uma **camada de proteção contextual entre a criança e os riscos da internet**: observa o uso do dispositivo em tempo quase real, interpreta contexto visual, textual e, quando necessário, áudio do sistema; detecta situações potencialmente perigosas; aplica regras definidas pela família; bloqueia o aplicativo quando necessário; explica a intervenção à criança; e envia evidências e um relatório ao responsável.

A decisão final permanece com a família. A tecnologia protege e informa; não substitui a educação familiar.

### Tese

> **Não queremos construir um sistema de bloquear aplicativos. Queremos criar uma solução para educação e letramento digital de adolescentes.**

Uma formulação de produto complementar:

> **Traditional parental controls understand apps and rules. Guardian understands what is happening inside the digital experience.**

Tagline de trabalho:

> **Protect the child, not control the internet.**

---

## 2. Usuários e modelo de negócio

### Responsável

- Assina um plano mensal da plataforma.
- Cria o perfil da criança.
- Conecta um ou mais dispositivos ao perfil.
- Define, por categoria, o que é permitido, alertado ou bloqueado.
- Recebe alertas e relatórios de incidentes.
- Recebe um relatório diário mesmo quando nenhum risco é detectado.
- Decide se um aplicativo bloqueado deve permanecer bloqueado ou ser liberado.

### Criança/adolescente

- Sabe que o Guardian está ativo.
- Consegue visualizar quais sinais o Guardian pode observar.
- É avisado de forma educativa quando ocorre uma intervenção.
- Pode solicitar desbloqueio e explicar a situação diretamente ao responsável.
- Não tem câmera nem microfone monitorados pelo Guardian.

### Modelo de relacionamento do MVP

```text
Parent
  │
  ▼
Child
  │
  ▼
Mac
  │
  ▼
Guardian Agent
```

O produto futuro poderá suportar múltiplos filhos e dispositivos por responsável. No hackathon, o fluxo demonstrado será **1 responsável → 1 criança → 1 Mac**.

---

# ETAPA 1 — Produto e MVP

## 3. Jornada completa

```text
Landing / assinatura
        ↓
Criar criança
        ↓
Definir política de proteção
        ↓
Parear dispositivo
        ↓
Guardian ativo no dispositivo
        ↓
Monitoramento contextual
```

Depois do pareamento, existem dois loops de produto.

### Loop A — Proteção em tempo quase real

```text
Atividade digital
      ↓
Observação local
      ↓
Análise contextual
      ↓
Existe risco?
   ┌───────┴───────┐
  NÃO             SIM
   │                │
Descartar       Classificar
                    ↓
              Aplicar política
                    ↓
                Bloquear
                    ↓
          Avisar a criança
                    ↓
           Criar incidente
                    ↓
          Avisar responsável
                    ↓
          Responsável decide
```

### Loop B — Acompanhamento diário

```text
Uso durante o dia
      ↓
Agregação local
      ↓
Estatísticas de uso
      ↓
Daily Safety Report
      ↓
Responsável
```

Mesmo quando nenhum perigo é encontrado, o responsável recebe valor por meio do relatório diário.

## 4. Monitoramento multimodal

O Guardian não deve ser tratado como um simples classificador de screenshots. O contexto de decisão combina:

```text
Visual context
+
On-screen text / OCR
+
System audio quando necessário
+
Aplicativo e janela ativa
+
Histórico recente da sessão
+
Política definida pelo responsável
```

O resultado é:

```text
Risk assessment
+
Policy decision
+
Intervention
+
Explanation
```

### Tela

A meta do MVP é analisar a atividade visual aproximadamente a cada **10 segundos**, mas evitando capturas redundantes de telas estáticas.

```text
Tela atual
   ↓
Perceptual / image hash
   ↓
Mudou significativamente?
   ├── Não → ignorar
   └── Sim → capturar e analisar
```

As screenshots normais são temporárias. Evidência visual só deve ser persistida quando fizer parte de um incidente relevante.

### Vídeo

Para vídeos e mídia, o produto conceitualmente utiliza:

```text
Vídeo
 ├── Frames amostrados
 ├── Texto/legendas visíveis
 └── Áudio do sistema quando necessário
          ↓
     Transcrição / sinais
          ↓
     Contexto multimodal
```

Não há necessidade de processar 30 ou 60 frames por segundo. O MVP pode amostrar frames nos mesmos intervalos de observação e usar uma pequena janela temporária de áudio quando a presença de vídeo/mídia justificar análise adicional.

### Áudio

- **Áudio do sistema:** sim, apenas quando necessário.
- **Microfone:** não.
- **Câmera:** não.
- Áudio bruto deve ser temporário e descartado após extração de contexto, salvo se houver uma justificativa explícita de produto para retenção futura.

## 5. Contexto temporal

O Guardian mantém uma memória temporária por aplicativo/sessão. Isso é crítico para riscos que só aparecem por progressão.

Exemplo:

```text
14:01  "hey"
14:03  "how old are you?"
14:05  "what school do you go to?"
14:07  "send me your instagram"
14:09  "send me a picture"
```

Uma mensagem isolada pode ser inocente. A sequência pode caracterizar um padrão de contato potencialmente perigoso.

## 6. Taxonomia de risco

O produto deve trabalhar com categorias configuráveis pelos responsáveis, inspiradas em riscos relevantes para menores e classificação de conteúdo por idade, sem tratar a expressão “conteúdo proibido para menores” como uma blacklist jurídica única e exaustiva.

Taxonomia de produto prevista:

- Conteúdo sexual.
- Nudez.
- Sexo explícito.
- Violência.
- Violência extrema/gore.
- Drogas.
- Álcool.
- Apostas.
- Discurso de ódio / discriminação.
- Contato potencialmente perigoso.
- Atividade criminosa.
- Linguagem imprópria.
- Outras regras definidas pelos pais.

### Escopo funcional do hackathon

Implementar e demonstrar somente três categorias principais:

1. `ADULT_CONTENT`
2. `HATE_SPEECH`
3. `DANGEROUS_CONTACT`

O restante aparece como arquitetura de produto/roadmap, não como promessa de funcionalidade pronta.

## 7. Política personalizada pelo responsável

O responsável define o tratamento por categoria. Exemplo:

```text
Adult sexual content     BLOCK
Graphic violence         BLOCK
Strong language          ALERT ONLY
Social media             ALLOW
Gaming                    ALLOW
Dangerous contact        BLOCK
Hate speech              BLOCK
```

A decisão não é uma simples blacklist. Conceitualmente:

```text
Guardian decision
=
Parent Policy
×
Content Classification
×
Context
×
Confidence
```

Isso permite servir crianças de diferentes idades sem depender de uma política universal.

## 8. Contexto contra falsos positivos

O Guardian deve diferenciar palavras ou imagens sensíveis pelo contexto em que aparecem.

```text
"sexual reproduction"
+
aula de biologia
+
contexto educativo
→ SAFE / ALLOW
```

versus:

```text
conteúdo sexual explícito
+
contexto pornográfico
+
política do responsável = BLOCK
→ HIGH RISK / BLOCK
```

A preferência do sistema é ser conservador em riscos graves, mas não bloquear apenas por palavra-chave. Casos ambíguos devem ser escalados para análise contextual.

## 9. Direção do risco

O Guardian deve distinguir quem está praticando/recebendo o comportamento:

- `CONTENT_CONSUMPTION`
- `CHILD_AS_TARGET`
- `CHILD_AS_ACTOR`

Isso muda a mensagem enviada ao responsável. Exemplo:

- **CHILD_AS_TARGET:** “A criança foi exposta a linguagem discriminatória durante uma conversa.”
- **CHILD_AS_ACTOR:** “Guardian identificou a criança enviando conteúdo classificado como discurso discriminatório.”

## 10. Intervenção

Quando um risco alto viola uma política com ação `BLOCK`:

```text
HIGH RISK
   ↓
Bloquear aplicativo
   ↓
Impedir reabertura
   ↓
Avisar criança
   ↓
Persistir incidente e evidências
   ↓
Notificar responsável
```

Mensagem de exemplo para a criança:

> **Discord foi temporariamente bloqueado.** O Guardian identificou sinais de que esta conversa pode estar tentando obter informações pessoais suas. Compartilhar escola, endereço, fotos privadas ou outras informações pessoais pode colocar você em risco. Seu responsável recebeu um relatório e poderá decidir se o aplicativo deve ser liberado.

A criança pode selecionar **Solicitar desbloqueio**, escrever sua explicação e enviá-la ao responsável.

## 11. Experiência do responsável

### Dashboard

```text
Lucas                                  Protected ●
MacBook Pro

TODAY
────────────────────────────────
Screen time                    3h 42m
Safety incidents                    1
Apps used                           7

Latest incident
🔴 Dangerous Contact
Discord · 11:42
Application blocked

[ Review incident ]
```

### Relatório de incidente

Deve conter:

- Timestamp.
- Criança/dispositivo.
- Aplicativo.
- Categoria.
- Direção do risco.
- Severidade e confiança.
- Explicação do que foi identificado.
- Sinais/evidências relevantes.
- Screenshots integrais selecionados.
- Ação tomada pelo Guardian.
- Explicação enviada pela criança, caso exista.
- Ações `Keep blocked` e `Unlock`.

## 12. Relatório diário

O relatório diário é descritivo. O Guardian **não deve julgar produtividade ou estilo parental**.

Exemplo:

```text
Lucas — Daily Report

Device usage
4h 18m

Apps
YouTube          1h 21m
Discord            58m
Safari             52m
Minecraft          43m

Protection
✓ No high-risk incidents detected

Locally analyzed
174 screen changes
23 media sessions
3 suspicious events reviewed
0 interventions required
```

O responsável interpreta os hábitos de uso e toma decisões familiares.

## 13. Transparência para a criança

O produto deve possuir uma tela de transparência, reforçando que a proteção é explícita e não espionagem oculta.

```text
Guardian is protecting this Mac

TODAY
Screen changes analyzed       174
Incidents                       0
Screenshots shared              0

Guardian can access
✓ Current screen
✓ Text visible on screen
✓ System audio during media
✗ Microphone
✗ Camera

Your parent can access
✓ Safety incidents
✓ Daily app usage
✓ Incident evidence

Your parent cannot access
✗ Live screen
✗ Microphone
✗ Camera
```

---

# ETAPA 2 — Concorrência e posicionamento

## 14. Categoria atual

Os produtos de controle parental existentes tipicamente combinam alguns destes mecanismos:

- Bloqueio de aplicativos e sites.
- Limites de tempo.
- Permissões e filtros.
- Monitoramento de mensagens/atividade em plataformas suportadas.
- Alertas de conteúdo potencialmente perigoso.
- Localização e relatórios de uso.

Concorrentes principais a considerar:

### Google Family Link

Fortemente orientado a regras, permissões, limites, apps e supervisão do ecossistema Google/Android.

### Qustodio

Combina tempo de tela, bloqueio, visibilidade de atividade, filtros e monitoramento/alertas em diferentes contextos.

### Bark

É o concorrente conceitualmente mais próximo da tese de “detectar risco e alertar os pais”, usando análise de conteúdo e evitando, em sua proposta, que o responsável precise ler tudo indiscriminadamente.

### Microsoft Family Safety / Apple Screen Time

Representam controles integrados ao ecossistema, fortes em limites, permissões, filtros e relatórios de uso.

## 15. Diferencial do Guardian

O Guardian não deve ser apresentado como “parental control com AI”. Isso não é suficientemente original.

O diferencial pretendido é:

> **Entender contextualmente o que está acontecendo dentro da experiência digital, independentemente de depender apenas de uma integração específica com cada aplicativo.**

Matriz conceitual:

| Capability | Controles tradicionais | Guardian |
|---|---:|---:|
| Limites de uso | Forte | Suportado |
| Bloqueio de apps | Forte | Suportado |
| Relatório diário | Forte | Forte |
| Alertas de risco | Variável | Core |
| Entendimento visual cross-app | Limitado | Core |
| Contexto temporal | Variável | Core |
| Frames + texto + áudio | Limitado | Core arquitetural |
| Política parental contextual | Regras | Regras + contexto |
| Explicação da intervenção | Variável | Core UX |
| Criança vê fronteira de privacidade | Variável | Core UX |
| Bloqueio → explicação → pedido → decisão familiar | Parcial | Core loop |

Mensagem competitiva:

> **Traditional parental controls understand apps and rules. Guardian understands what is happening inside the digital experience.**

---

# ETAPA 3 — Arquitetura técnica definitiva

## 16. Princípio arquitetural

Separar o produto em:

1. **Edge Guardian** — observação, pré-processamento, contexto temporário e enforcement no dispositivo.
2. **Cloud Control Plane** — políticas, incidentes, relatórios, estado do dispositivo e ações do responsável.

```text
┌────────────────────────────────────────────┐
│                CHILD MAC                   │
│                                            │
│ Screen Observer                            │
│      ↓                                     │
│ Change Detector                            │
│      ↓                                     │
│ Observation Pipeline                       │
│  ├── frames                                │
│  ├── OCR                                   │
│  ├── app metadata                          │
│  └── optional system audio                 │
│      ↓                                     │
│ Local Pre-Filter                           │
│      ↓                                     │
│ Context Buffer                             │
│      ↓                                     │
│ Risk Engine                                │
│      ↓                                     │
│ Deterministic Policy Engine                │
│      ↓                                     │
│ App Enforcer + Incident Builder            │
└──────────────────────┬─────────────────────┘
                       │ incident + evidence
                       ▼
┌────────────────────────────────────────────┐
│               CLOUD API                    │
│ Child / Device / Policy / Incident         │
│ Daily Aggregation / Parent Actions         │
└──────────────────────┬─────────────────────┘
                       ▼
              Parent Dashboard
```

## 17. Stack do hackathon

Priorizar ferramentas simples, conhecidas e rápidas de integrar:

- **Agente macOS / Edge:** Python.
- **Captura no macOS:** ScreenCaptureKit ou bridge nativa mínima quando necessário.
- **OCR:** macOS Vision ou ferramenta local equivalente leve.
- **Change detection:** perceptual hash / diferença de imagem.
- **Risk engine:** heurísticas locais + modelo multimodal remoto somente para casos relevantes.
- **Backend:** FastAPI.
- **Database:** SQLite.
- **Frontend do MVP:** SPA responsiva em HTML/CSS/JavaScript servida pelo FastAPI.
- **Frontend pós-hackathon:** Next.js + TypeScript, quando autenticação e deploy independente justificarem o segundo runtime.
- **Persistência de evidência no MVP:** filesystem local + referência no banco.

Não utilizar no hackathon:

- Kubernetes.
- Kafka.
- Redis.
- Microservices.
- Vector database sem necessidade concreta.
- Autenticação production-grade.
- Stripe/checkout real.
- MDM.
- Android funcional.

## 18. Observer

Contrato de observação:

```python
Observation(
    timestamp,
    app_name,
    window_title,
    screenshot_path,
    screen_hash,
    media_detected
)
```

Funções prioritárias:

```python
capture_screen()
detect_change()
get_active_application()
block_application()
unblock_application()
```

No macOS, captura real depende da permissão **Screen Recording**. Identificação do app ativo e AppleScript podem exigir **Accessibility/Automation**. A demo oficial deve continuar funcionando com fixtures quando essas permissões não forem concedidas.

## 19. Context Buffer

Manter aproximadamente os últimos **1–2 minutos** ou **5–10 observações significativas** de uma sessão/aplicativo.

Objetivo: permitir raciocínio temporal sem construir um arquivo permanente do uso da criança.

## 20. Risk Engine

Interface única:

```python
assess_risk(current_observation) -> RiskAssessment
```

Contrato congelado:

```typescript
type RiskAssessment = {
  risk: "SAFE" | "LOW" | "MEDIUM" | "HIGH";
  category: null |
    | "ADULT_CONTENT"
    | "HATE_SPEECH"
    | "DANGEROUS_CONTACT"
    | "OTHER";
  direction: null |
    | "CONTENT_CONSUMPTION"
    | "CHILD_AS_TARGET"
    | "CHILD_AS_ACTOR";
  confidence: number;
  evidence: string[];
  explanation: string;
};
```

Para `risk = "SAFE"`, `category` e `direction` devem ser `null`. Para qualquer outro nível, ambas são obrigatórias. `confidence` deve estar entre `0` e `1`.

## 21. Deterministic Policy Engine

O modelo de AI **não deve controlar diretamente o computador**.

```text
AI / classifier
      ↓
Structured RiskAssessment
      ↓
Deterministic Policy Engine
      ↓
Action
```

Exemplo:

```python
if (
    result.risk == "HIGH"
    and policy[result.category].action == "BLOCK"
):
    block_application()
```

O modelo interpreta contexto. O software aplica a política definida pela família.

O resultado da política usa um contrato separado:

```typescript
type PolicyDecision = {
  action: "IGNORE" | "LOG" | "BLOCK";
  matchedRule: PolicyRule | null;
  reason: string;
};
```

Isso impede que o classificador escolha diretamente uma ação sobre o dispositivo.

## 22. App Enforcer no macOS

No hackathon, o enforcement pode ser simples:

```text
BLOCK
 ↓
encerrar aplicativo
 ↓
observar reabertura
 ↓
se aplicativo continuar bloqueado
 → encerrar novamente
```

Não construir MDM ou extensão de sistema sofisticada em 5 horas.

Enforcement real deve ser opt-in e deny-by-default: somente aplicativos de demonstração presentes em uma allowlist explícita podem ser encerrados. Finder, Terminal, Ajustes do Sistema, processos de login e o próprio Guardian nunca podem ser bloqueados.

## 23. Incident Builder

Estrutura conceitual:

```text
Incident
├── id
├── timestamp
├── child_id
├── device_id
├── application
├── category
├── direction
├── severity
├── confidence
├── explanation
├── evidence
├── screenshot_urls
├── relevant_transcript
├── triggered_policy
├── child_explanation
└── status
```

State machine:

```text
DETECTED
   ↓
BLOCKED
   ↓
PARENT_NOTIFIED
   ↓
┌───────────────────┐
│                   │
▼                   ▼
UNLOCKED        KEPT_BLOCKED
```

Com contestação:

```text
BLOCKED
   ↓
UNLOCK_REQUESTED
   ↓
Parent decision
```

## 24. Privacidade e retenção

### Local / temporário

```text
/tmp/guardian/current/
    observation_001.jpg
    observation_002.jpg
    observation_003.jpg
```

Se seguro:

```text
SAFE → delete raw evidence
```

Se incidente:

```text
HIGH RISK → persist minimal selected evidence
```

A nuvem deve receber apenas:

```text
incident metadata
+
selected incident evidence
+
daily aggregates
```

Não armazenar continuamente a tela, áudio bruto ou histórico completo do dispositivo.

## 25. Offline

O Guardian continua funcionando offline, com capacidade reduzida para preservar bateria e computação.

```text
ONLINE
local pre-filter
   ↓
rich contextual analysis when needed
   ↓
policy engine

OFFLINE
cached policy
+
local heuristics / light classifier
+
reduced observation rate if needed
   ↓
conservative local protection
```

O produto não deve prometer paridade total de inteligência offline no MVP.

Falhas técnicas são **fail-open para novas decisões**: timeout, backend indisponível ou saída inválida geram log e não iniciam um bloqueio novo. Um bloqueio já confirmado pode continuar sendo aplicado com a política em cache até receber um comando válido de desbloqueio.

## 26. Daily Aggregator

Não utilizar AI quando uma agregação determinística resolve o problema.

```text
AppSession
├── app
├── started_at
├── ended_at
└── duration
```

Agregados do dia:

- Tempo total.
- Tempo por aplicativo.
- Número de mudanças de tela analisadas.
- Sessões de mídia.
- Eventos suspeitos analisados.
- Incidentes.

## 27. API mínima

Produto completo poderia expor:

```text
GET    /children/:id
GET    /children/:id/daily-report
GET    /children/:id/incidents
GET    /incidents/:id
POST   /incidents/:id/unlock
POST   /incidents/:id/keep-blocked
GET    /children/:id/policy
PUT    /children/:id/policy
POST   /devices/pair
GET    /devices/:id/status
```

No hackathon, o conjunto mínimo precisa fechar também a comunicação agente → API e API → agente:

```text
GET    /api/health
POST   /api/incidents
GET    /api/incidents
GET    /api/incidents/:id
POST   /api/incidents/:id/evidence
GET    /api/evidence/:id
POST   /api/incidents/:id/request-unlock
POST   /api/incidents/:id/unlock
POST   /api/incidents/:id/keep-blocked
GET    /api/devices/:id/commands
POST   /api/devices/:id/commands/:commandId/ack
POST   /api/devices/:id/telemetry
GET    /api/daily-report
GET    /api/children/:id/policy
PUT    /api/children/:id/policy
POST   /api/devices/pair
```

O agente consulta comandos pendentes por polling curto durante a demo. Autorizar um desbloqueio cria um comando persistente e idempotente, executado e confirmado pelo agente.

---

# ETAPA 4 — Execução em 5 horas / divisão de equipe

## 28. Vertical slice obrigatório

Tudo que for implementado deve servir este fluxo:

```text
Unsafe interaction
      ↓
Mac observes
      ↓
Risk reasoning
      ↓
HIGH
      ↓
Application blocked
      ↓
Child warning
      ↓
Incident created
      ↓
Parent sees screenshot + explanation
      ↓
Child sends explanation
      ↓
Parent unlocks
      ↓
Application works again
```

Se esse fluxo funcionar de ponta a ponta, o MVP está pronto para demo.

## 29. Pessoa 1 — Edge / macOS

Ownership: `/agent`

Prioridades:

- P0: screenshot real.
- P0: identificar app ativo.
- P0: bloquear/desbloquear aplicativo.
- P1: screen-change detection.
- P2: áudio do sistema.

Entregas:

```python
capture_screen()
detect_change()
get_active_app()
block_app()
unblock_app()
```

Áudio é a primeira feature a ser cortada caso o cronograma deslize.

## 30. Pessoa 2 — Risk Engine

Ownership: `/risk_engine`

Entregas:

- `assess_risk()`.
- Context buffer.
- Structured output.
- Regras/heurísticas locais.
- Integração multimodal remota quando necessária.
- Fixtures reproduzíveis.

Fixtures mínimas:

```text
fixtures/
  safe_biology/
  dangerous_contact/
  adult_content/
  hate_speech/
```

O risk engine precisa funcionar com fixtures mesmo se o collector ainda não estiver integrado.

## 31. Pessoa 3 — Backend

Ownership: `/api`

Entregas:

- FastAPI.
- SQLite.
- Incident lifecycle.
- Daily report.
- Pedido de desbloqueio.
- Política mínima.

Modelos mínimos:

```text
Child
Device
Policy
Incident
AppSession
```

No MVP, IDs de parent/child podem ser hardcoded para a demo. Não implementar autenticação real.

## 32. Pessoa 4 — Frontend / Demo

Ownership: `/web`

Telas:

- `/` — dashboard do responsável.
- `/incidents/:id` — relatório/evidências.
- `/child` — relatório diário + transparência.
- `/settings` — políticas de proteção.

Além disso, criar a experiência de aviso/bloqueio da criança. Para reduzir o risco de integração no hackathon, a SPA é servida pelo FastAPI e consome `/api/*` na mesma origem.

## 33. Monorepo

```text
guardian/
├── agent/
├── risk_engine/
├── api/
├── guardian_core/
├── web/
├── fixtures/
├── tests/
├── scripts/
└── README.md
```

Contratos de dados devem ser congelados antes do desenvolvimento paralelo.

## 34. Cronograma

### 00:00–00:20 — Architecture freeze

- Criar monorepo.
- Congelar schemas.
- Definir fixture da demo.
- Definir processo de execução.
- Cada pessoa assume seu diretório.

### 00:20–01:30 — Desenvolvimento paralelo

```text
P1: screen → file; app → blocked
P2: fixtures → RiskAssessment
P3: incident → SQLite → API
P4: mock → dashboard
```

### 01:30 — Checkpoint obrigatório

Precisam existir quatro provas independentes:

1. Screenshot real.
2. Structured risk result.
3. API persistindo incidente.
4. Dashboard renderizando incidente.

Se uma falhar, cortar features antes de adicionar outras.

### 01:30–02:30 — Integração principal

```text
real screenshot
      ↓
Risk Engine
      ↓
Incident
      ↓
API
      ↓
Dashboard
```

Até 2h30, um incidente real deve aparecer no dashboard.

### 02:30–03:15 — Intervention loop

```text
HIGH
 ↓
block
 ↓
child warning
 ↓
unlock request
 ↓
parent unlock
```

### 03:15–03:45 — Produto secundário

Se o core estiver estável:

- Daily usage.
- Screen hash/change detection.
- Privacy counters.

### 03:45 — Feature freeze

Depois disso, não adicionar features novas.

### 03:45–04:20 — Reliability

Testar repetidamente:

- Falha/timeout de modelo remoto.
- Screenshot ausente.
- Output inválido.
- App já fechado.
- Tentativa de reabrir app bloqueado.
- Incidente duplicado.
- Backend indisponível.

Adicionar validação, fallback, deduplicação e timeout apenas onde necessário.

### 04:20–05:00 — Demo e ensaio

Usar fixtures/páginas locais controladas. Não depender de pornografia real, pessoas externas, Discord real ou conteúdo imprevisível.

---

# 35. Demo recomendada

## Cenário principal — Dangerous Contact

A conversa começa normal:

```text
Alex: hey, saw your Minecraft build
```

Guardian não intervém.

Depois:

```text
how old are you?
what school do you go to?
send me your Instagram
send me a picture
```

O Context Agent percebe a progressão.

```text
Risk: HIGH
Category: DANGEROUS_CONTACT
Direction: CHILD_AS_TARGET
Action: BLOCK
```

O aplicativo fecha e fica bloqueado. A criança recebe a explicação educativa. O responsável recebe um incidente com screenshots, timestamps, explicação e sinais detectados.

A criança envia:

> “É um amigo da minha escola.”

O responsável pressiona `Unlock`. O aplicativo pode ser aberto novamente.

## Cenário secundário — Contexto evita falso positivo

Mostrar rapidamente uma página/aula de biologia contendo terminologia sexual.

```text
Sensitive terminology
+
Educational context
→ SAFE
→ No intervention
```

Esse cenário demonstra que o produto não é um filtro de palavras proibidas.

---

# 36. O que NÃO implementar no hackathon

- Checkout/pagamento real.
- Autenticação real.
- Android funcional.
- Deploy para app stores.
- Push/email real.
- Multi-parent.
- Multi-child funcional.
- Modelo multimodal grande rodando localmente.
- Treinamento de modelo próprio.
- Browser extension completa.
- MDM.
- Captura contínua de áudio.
- Classificação funcional de toda a taxonomia.
- Infra cloud production-grade.

Esses itens pertencem ao roadmap e não ao vertical slice de 5 horas.

---

# 37. Princípios técnicos para apresentação

## Adaptive edge observation

O Guardian não captura telas cegamente quando nada muda. Utiliza mudança visual para reduzir processamento e exposição desnecessária.

## Contextual multimodal reasoning

```text
image
+
text
+
audio when needed
+
temporal history
+
parent policy
```

## Deterministic enforcement

```text
Model / classifier
      ↓
Structured assessment
      ↓
Deterministic policy engine
      ↓
Action
```

A AI não recebe poder irrestrito de controlar o dispositivo.

## Privacy by ephemerality

```text
SAFE
→ delete raw data

INCIDENT
→ persist only selected evidence
```

## AI somente onde agrega valor

Agregações de tempo, estados de incidente, políticas e regras de enforcement devem continuar determinísticos. AI é usada para interpretação contextual, não como substituto universal de software convencional.

---

# 38. Definição final do produto

> **Guardian é uma camada de proteção contextual entre crianças e os riscos da internet. Em vez de decidir previamente apenas quais aplicativos uma criança pode acessar, o sistema entende o que está acontecendo durante o uso, combina esse contexto com regras definidas pelos responsáveis, intervém quando existe risco e devolve a decisão final para a família.**

O fluxo arquitetural central é:

```text
Edge monitoring
      ↓
Context extraction
      ↓
Multimodal risk reasoning
      ↓
Deterministic parental policy
      ↓
Intervention
      ↓
Family decision
      ↓
Daily digital-safety reporting
```

Para o hackathon, sucesso significa demonstrar **um único fluxo funcional, confiável e compreensível em menos de três minutos**, e não construir a plataforma inteira.
