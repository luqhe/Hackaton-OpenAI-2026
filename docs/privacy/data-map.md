# Mapa de dados e retenção

> Owner: Privacy Engineering  
> Status: baseline técnica; retenções-alvo dependem de revisão de produto e jurídica  
> Roadmap: R0-08

## Princípios

- Coletar somente o necessário para proteção e explicação.
- Manter contexto bruto local e efêmero.
- Enviar à nuvem apenas incidente selecionado e agregados.
- Proibir tela ao vivo, microfone e câmera.
- Não usar dados de crianças para treinamento sem programa separado, base apropriada e aprovação explícita.

## Inventário

| Dado | Origem | Finalidade | Local atual | Destino futuro | Acesso | Retenção-alvo | Exclusão |
|---|---|---|---|---|---|---|---|
| Frame de observação | tela atual | detectar mudança e extrair contexto | arquivo temporário local | não enviar quando seguro | agente | ≤ 2 min se seguro | imediata após análise |
| Hash visual | frame | evitar captura redundante | memória/agregado local | telemetria sem imagem | agente | sessão atual | sobrescrever |
| OCR/texto visível | frame | avaliação contextual | context buffer local | somente trecho necessário do incidente | agente; provider quando indispensável | ≤ 2 min se seguro | limpar buffer |
| App e título de janela | macOS | contexto e relatório | memória/SQLite demo | metadado de incidente/agregado | agente; família correspondente | contexto ≤ 2 min; incidente conforme abaixo | TTL por registro |
| Áudio do sistema | mídia | capacidade futura condicionada | não implementado | não definido | nenhum acesso atual | não aplicável | não aplicável |
| Microfone/câmera | dispositivo | fora do produto | não coletado | proibido | nenhum | zero | não aplicável |
| Assessment | risk engine | explicar risco | memória e incidente | banco do tenant | agente, API, família | 90 dias após incidente, alvo provisório | job de TTL e exclusão da família |
| Evidência selecionada | incidente | permitir decisão familiar | `.data/evidence` no MVP | object storage privado | família, suporte autorizado e auditado | 30 dias, alvo provisório/configurável | TTL + revogação de URL |
| Explicação da criança | formulário | contestação | SQLite demo | banco do tenant | criança e responsáveis da família | junto ao incidente | mesma exclusão do incidente |
| Política familiar | responsável | decisão determinística | SQLite demo | PostgreSQL | responsáveis e agente pareado | enquanto conta ativa + período operacional mínimo | exclusão da família |
| Uso por aplicativo | agente | relatório descritivo | SQLite demo | agregado diário | família | 90 dias, alvo provisório | job de TTL |
| Heartbeat técnico | agente | saúde e permissões | timestamp demo | banco/telemetria | família e operação | 30 dias agregado | TTL |
| Comando/ack | responsável/agente | bloquear/desbloquear | SQLite demo | banco e auditoria | família e operação | 90 dias; auditoria sem conteúdo por prazo aprovado | TTL separado |
| Audit log | sistema | segurança e responsabilização | não implementado | armazenamento controlado | segurança/privacidade | 12 meses, alvo provisório | job controlado e registro de exclusão |
| Credencial do dispositivo | pareamento | autenticar agente | não implementado | Keychain + hash/identificador no backend | agente e auth service | até revogação | revogar e remover |

## Fluxo atual do MVP

```text
fixture JSON
   ↓
Observation em memória
   ↓
assessment + política
   ↓
SQLite local + evidência textual selecionada
   ↓
dashboard local
```

O fluxo atual não deve receber dados reais de famílias.

## Fluxo-alvo do piloto

```text
frame temporário local
   ↓ SAFE → exclusão local
   ↓ INCIDENTE
recorte mínimo + metadados
   ↓ canal autenticado/TLS
banco tenant + object storage privado
   ↓ URL curta autorizada
família correspondente
```

## Controles obrigatórios antes do piloto

- classificação formal dos dados;
- criptografia em trânsito e em repouso;
- tenant e autorização em todas as queries;
- TTL automático e observável;
- exportação e exclusão verificável;
- links de evidência temporários e revogáveis;
- redaction de logs;
- acesso interno mínimo e auditado;
- política específica para backups;
- revisão de fornecedores e localização dos dados.

