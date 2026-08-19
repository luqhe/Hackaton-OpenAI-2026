# Versionamento de API e política de migrations

> Status: aceito  
> Roadmap: R0-15

## API

O MVP usa rotas `/api/*` enquanto a API é interna e pré-1.0. Toda resposta contém `X-Guardian-API-Version` e o health check expõe `api_version`.

### Política

- `API_VERSION` usa `major.minor`.
- Alteração aditiva compatível incrementa `minor`.
- Remoção, mudança semântica ou tipo incompatível exige novo `major`.
- A primeira API pública será publicada sob `/api/v1/*`.
- O agente envia e registra a versão de protocolo usada.
- Servidor rejeita major incompatível com erro explícito; não interpreta silenciosamente.
- Campos novos devem ter default ou ser opcionais durante uma janela de compatibilidade.
- Enum novo precisa ser tratado como desconhecido pelo consumidor antes de ser emitido.

### Depreciação futura

1. Publicar a versão substituta.
2. Emitir aviso mensurável para clientes antigos.
3. Manter janela compatível definida para agentes ainda suportados.
4. Bloquear rollout de remoção enquanto houver dispositivos ativos sem caminho de atualização.
5. Remover somente após telemetria confirmar migração.

## Schema de dados

O SQLite local usa `PRAGMA user_version`, alinhado a `SCHEMA_VERSION`. O processo falha quando encontra versão mais nova que o código suporta.

### Regras de migration

- Toda mudança de schema possui número, descrição, `up` e estratégia de rollback/forward-fix.
- Migrations são determinísticas, revisadas e testadas em banco vazio e cópia anonimizada representativa.
- Nenhuma migration destrutiva é executada junto com código que ainda depende da coluna antiga.
- Mudanças incompatíveis seguem expand/contract:

  1. adicionar estrutura nova compatível;
  2. escrever nos formatos antigo e novo quando necessário;
  3. backfill observável e retomável;
  4. mudar leituras;
  5. remover estrutura antiga em release posterior.

- Backup e restauração são testados antes de migration classificada como alto risco.
- Evidências em object storage possuem migration de metadados separada da movimentação de blobs.
- Rollback nunca restaura dados que já deveriam ter sido excluídos por retenção.

## Compatibilidade agente/API

| Situação | Comportamento |
|---|---|
| Mesmo major, agente mais antigo | aceitar enquanto campos são compatíveis |
| Agente em major não suportado | rejeitar com instrução de atualização, sem enforcement novo |
| API indisponível | agente preserva estado confirmado e não cria bloqueio novo por falha |
| Comando desconhecido | não executar; registrar ack de erro quando o protocolo suportar |

