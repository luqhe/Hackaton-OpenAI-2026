# Checklist de revisão do pacote do alpha

> Roadmap: R5-02  
> Status: aguardando revisores designados

## Escopo e participantes

- [ ] Definir mercados, jurisdições, faixa etária e tamanho da coorte.
- [ ] Confirmar entidade(s), papéis de controlador/operador e contatos reais.
- [ ] Validar autoridade do responsável, consentimento e assentimento por idade.
- [ ] Revisar acessibilidade, idioma e compreensão das informações.

## Dados e fornecedores

- [ ] Aprovar finalidades, bases, minimização, retenção e exclusão/backups.
- [ ] Aprovar subprocessadores, contratos, regiões e transferências.
- [ ] Confirmar proibição de câmera, microfone, tela ao vivo e treinamento não autorizado.
- [ ] Validar acesso interno mínimo, auditoria e resposta a solicitações.

## Operação e risco

- [ ] Confirmar identidade/tenant, autenticação de dispositivo e storage privado.
- [ ] Exercitar retirada, exclusão e comunicação de incidente.
- [ ] Aprovar protocolo, suporte, plantão, kill switches e interrupção.
- [ ] Registrar riscos residuais e responsáveis por aceite.

## Registro de aprovação

Cada revisão precisa registrar nome/identificador do revisor, escopo, versão, data/hora e status.
Uma aprovação parcial não muda `approved_for_pilot` para `true`. Mudança material em coleta,
retenção, fornecedor, mercado, modelo ou intervenção invalida a aprovação afetada e exige nova
revisão.

O arquivo `config/pilot/legal-approvals.v1.json` é o gate legível por máquina. Ele deve permanecer
`PENDING` até revisões reais ocorrerem; commits de engenharia não equivalem a assinatura jurídica.
