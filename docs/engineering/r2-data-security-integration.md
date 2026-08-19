# Integração dos controles de dados da Etapa 2

## Dependências já integradas

Esta branch inclui a fundação de identidade `6c83be4`. Todos os serviços recebem `guardian_core.identity.FamilyScope`; o único tenant aceito é `scope.family_id`. IDs opacos nunca ampliam o escopo.

O schema data-security é uma migration aditiva posterior ao schema SQLite v2. Ela pressupõe `families(id)` e `incidents(family_id, id)` e adiciona FKs compostas para `evidence_objects` e `evidence_access_grants`. O integrador deve executá-la depois da migração v1→v2 e antes de habilitar rotas de evidência/auditoria.

## Pontos de composição pendentes

- `create_app` deve construir `DataSecuritySettings`, `create_database`, object store, audit trail e rate limiter uma vez no lifespan.
- As rotas de evidência devem passar o `FamilyScope` resolvido pela autenticação e um `AuthenticatedSubject` vinculado à sessão atual. O endpoint de entrega é proxy/autorizado; o bucket nunca é público.
- Logout, revogação de membership e exclusão familiar devem revogar a sessão e avançar o epoch familiar antes de responder sucesso.
- Os repositórios SQL devem consultar evidência por `(family_id, evidence_id)` e incidentes por `(family_id, incident_id)`. Foreign e missing retornam o mesmo 404.
- As ações de policy, evidence, incident decision, export/delete e rate denial chamam `AuditTrail.append` apenas com IDs opacos, resultado e correlation ID.
- Rotas do agente mapeiam para buckets separados: unlock→`UNLOCK`, ack→`COMMAND_ACK`, heartbeat→`HEARTBEAT`. Pairing, login, evidence e general nunca compartilham esses contadores.
- Restore deve executar `RestoreReconciler.reconcile_before_access` e exigir `safe_to_open=true` antes de liberar tráfego.

O adapter PostgreSQL, o backend de rate limit e o S3-compatible adapter são reais e injetáveis; o `GuardianStore` completo ainda precisa ser portado/composto sobre PostgreSQL após a consolidação dos schemas R2. SQLite e filesystem permanecem exclusivamente em development/test.
