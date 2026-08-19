# Minuta de aviso de privacidade do alpha

> Roadmap: R5-02  
> Status: minuta para revisão; não aprovada para participantes  
> Versão do pacote: 2026-08-19.draft-1

## Escopo

Este aviso descreve a arquitetura pretendida do alpha Guardian. A versão final deverá identificar
controlador(es), operador(es), contatos, mercados, bases aplicáveis e direitos por jurisdição. O
MVP local atual não possui identidade multi-tenant nem controles suficientes para dados reais.

## Categorias, finalidade e retenção pretendida

| Categoria | Finalidade | Forma | Retenção-alvo provisória |
|---|---|---|---:|
| heartbeat, versão e permissões | verificar saúde e proteção efetiva | técnica | 30 dias agregados |
| contadores e latências | SLO e diagnóstico | técnica, sem conteúdo | 30–90 dias |
| contexto temporário | interpretar atividade atual | local/efêmero | até 2 minutos quando seguro |
| incidente e assessment | explicar e permitir decisão | registro por família | 90 dias |
| evidência mínima | fundamentar incidente | objeto privado | 30 dias |
| política familiar | aplicar escolha do responsável | configuração | conta ativa + período aprovado |
| comando e ack | executar decisão familiar | evento técnico | 90 dias |

Os prazos são alvos de engenharia e não constituem decisão jurídica. A revisão deve resolver
necessidade, base, período, exceções, backups e obrigações de preservação.

## Acesso e compartilhamento

Dados de uma família devem ficar disponíveis apenas aos responsáveis autorizados, agente pareado
e equipe mínima autorizada/auditada. Evidência não pode ser copiada para tickets ou canais gerais.
Subprocessadores, regiões, transferências e contratos devem constar de um registro aprovado antes
do alpha. Nenhum subprocessador de piloto é aprovado por esta minuta.

## Direitos e solicitações

A versão final deve oferecer canal verificável para acesso, correção, exportação, oposição/retirada
quando aplicável e exclusão. A exclusão deve revogar dispositivo, remover banco e objetos, tratar
filas locais e produzir comprovante técnico sem conteúdo. Backups e exceções precisam ter prazo e
procedimento comunicados.

## Segurança, incidente e contato

O piloto requer criptografia, autenticação, tenant em todas as consultas, links curtos/revogáveis,
redaction de logs e plantão. Suspeita de acesso cruzado, coleta proibida ou exposição interrompe
a sessão. A versão aprovada deverá informar canal de privacidade, segurança e autoridade/data
protection officer quando aplicável; contatos não podem permanecer como placeholders.

## Crianças e decisões automatizadas

O Guardian interpreta contexto, mas a política determinística decide a ação e a decisão final
permanece com a família. O alpha começa em shadow mode. Idade, assentimento, autorização parental,
direitos específicos e limites de profiling devem ser decididos pelos revisores qualificados para
os mercados do piloto.
