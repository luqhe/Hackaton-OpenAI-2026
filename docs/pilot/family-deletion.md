# Exclusão verificável de família

> Roadmap: R5-06  
> Owner: Privacy Engineering / Backend  
> Status: storage local do MVP verificado; escopo externo do piloto pendente

## Escopo implementado

`GuardianStore.delete_family()` remove, em uma única operação controlada, a família e seus filhos,
dispositivos, políticas, incidentes, evidências, comandos, sessões, telemetria diária, eventos de
onboarding e amostras de saúde. Arquivos de evidência são movidos primeiro para staging dentro do
diretório autorizado, as linhas são excluídas e os arquivos staged são destruídos após o commit.

O método rejeita qualquer caminho de evidência que resolva fora do diretório configurado. Se a
transação de banco falhar, os arquivos são restaurados. Se a limpeza final falhar, o receipt fica
`FAILED_STORAGE_CLEANUP` e alimenta a métrica operacional `family_deletion_failures`; a operação
não pode ser declarada concluída.

Se rollback do banco e restauração de um arquivo falharem juntos, o restore é best-effort e o
receipt sempre termina `FAILED_DATABASE` com o staging preservado. O erro de banco permanece como
causa e o erro de restore aparece no erro composto; nunca se deixa receipt `STARTED` silencioso.

## Receipt e minimização

O receipt técnico retém apenas:

- ID aleatório da operação;
- hash SHA-256 da referência familiar;
- status e timestamps;
- contagens por entidade removida.

Ele não contém nome da família/criança, caminho de evidência, conteúdo observado, explicação ou
credencial. Um tombstone `COMPLETED` impede que a família demo seja recriada pela inicialização
automática após exclusão.

## Execução local

Pare a API e confirme os alvos exatos. A CLI exige que `--confirm-family-id` seja idêntico ao ID:

```bash
python scripts/delete_pilot_family.py \
  --database .data/guardian.db \
  --evidence-directory .data/evidence \
  --family-id family-demo \
  --confirm-family-id family-demo
```

Depois, confirme receipt `COMPLETED`, ausência de linhas/arquivos e reinicie a API para verificar
que o tombstone impede reseed. A operação é irreversível no storage local; recuperação só pode vir
de backup sujeito à política aprovada.

Uma limpeza interrompida pode ser retomada pelo ID exato do receipt:

```bash
python scripts/delete_pilot_family.py \
  --database .data/guardian.db \
  --evidence-directory .data/evidence \
  --resume-receipt del-example \
  --confirm-receipt-id del-example
```

Para `FAILED_STORAGE_CLEANUP`, a retomada destrói apenas os arquivos staged validados e marca
`COMPLETED`. Para `FAILED_DATABASE`, ela restaura os arquivos ao evidence root e mantém o receipt
falho para que uma nova exclusão seja iniciada conscientemente.

## Prova automatizada

`tests/test_family_deletion.py` cria dados em todas as tabelas relevantes, persiste evidência,
executa a exclusão, verifica banco/filesystem/receipt e reinicia o store. Também prova que caminho
fora do evidence root aborta sem apagar a família ou o arquivo externo.

## Limite do gate do piloto

A prova atual cobre SQLite e filesystem local. O alpha real continua bloqueado até que o inventário
inclua e teste:

- backups gerenciados e prazo de expiração;
- object storage, versões, réplicas e URLs;
- estado/outbox/credencial no Mac;
- analytics, alerting e subprocessadores;
- retenção legal/auditável aprovada.

`config/pilot/deletion.v1.json` mantém `pilot_scope_verified = false`. Portanto, esta entrega prova
a remoção completa do storage atualmente implementado, sem alegar exclusão ponta a ponta de uma
infraestrutura que ainda não existe.
