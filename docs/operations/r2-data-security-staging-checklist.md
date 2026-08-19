# Gate de staging — dados, evidências, auditoria e abuso

Código local não conclui este gate. Anexe outputs sem segredos, timestamps, ambiente, responsável e correlação de execução.

## PostgreSQL e migrations — R2-13/R2-14

- [ ] Provar instância gerenciada, região, versão suportada, mínimo privilégio e `sslmode=verify-full` com certificado validado.
- [ ] Executar migration em banco vazio e cópia sintética representativa; comparar schema/checksum/contagens/FKs.
- [ ] Exercitar rollback seguro e forward-fix. Confirmar que rollback recusa qualquer ledger/tabela não vazia e nunca remove tombstone.

## Object storage e criptografia — R2-15/R2-16/R2-17

- [ ] Provar public-access block/bucket policy/IAM mínimo; negar leitura anônima e listagem cross-role.
- [ ] Provar TLS e SSE-KMS por metadata/provider; exercitar rotação da chave e restore autorizado.
- [ ] Provar grant ≤300 s, auth atual, family scope, session binding, revocation epoch, logout e revogação antecipada.
- [ ] Confirmar logs/audit sem URL/token, frame, OCR, blob, credencial ou segredo.

## Retenção, export/delete e backup — R2-18/R2-19/R2-20

- [ ] Rodar TTL com relógio controlado, retry e alerta de falha; confirmar tombstone→inacessível→blob delete→metadata purge.
- [ ] Exportar e excluir uma família sintética com reautenticação; revogar sessões/devices/grants antes da purga.
- [ ] Restaurar backup anterior à exclusão em ambiente isolado; reconciliar ledger externo antes do tráfego e provar ausência no DB/object store.
- [ ] Registrar RPO/RTO, retenção/expiração de backup, criptografia, acesso e procedimento de descarte.

## Auditoria e abuso — R2-24/R2-25/R2-26

- [ ] Instrumentar policy/evidence/family decision com actor/family/action/target/result/correlation, sem conteúdo.
- [ ] Provar UPDATE/DELETE negados, rotação `key_id`, verificação após restore e checkpoint imutável externo/WORM.
- [ ] Executar carga distribuída do limiter PostgreSQL. Exaurir evidence/login/pair/general e provar unlock/ack/heartbeat dentro do SLO.

Sem todos os itens acima, R2-13–R2-20 e R2-24–R2-26 permanecem `External Pending`.
