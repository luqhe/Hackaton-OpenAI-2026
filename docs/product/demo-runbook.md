# Runbook da demo local (3 minutos)

## Classificação oficial

O caminho oficial desta entrega é **local e determinístico**. A API, o chat sintético, a
classificação por fixture, a política, o SQLite e as evidências rodam no Mac da apresentação,
sem OpenAI, chave de API, créditos, nuvem, captura real de tela, Docker ou rede externa.

O launcher sempre declara o modo ou a origem no terminal:

- `mode=OPTIONAL_LIVE_DEMO`: o subcomando opcional `live-demo` existe e iniciou; ele declara
  sua própria origem, como `source=OPENAI`;
- `source=LOCAL_FIXTURE`: o subcomando não existe e a fixture oficial foi usada;
- `source=FIXTURE_FALLBACK`: o subcomando existia, mostrou uma falha e a fixture foi iniciada
  separadamente.

`LOCAL_FIXTURE` e `FIXTURE_FALLBACK` são caminhos oficiais da apresentação, não modos
degradados ocultos.

## Preparação antes do ensaio

Na raiz do repositório, com a API parada:

```bash
bash scripts/bootstrap.sh
bash scripts/check.sh
bash scripts/reset-demo.sh
```

Feche abas antigas do Guardian. Deixe dois terminais visíveis e o navegador pronto.
`OPENAI_API_KEY` não é necessária para o caminho oficial e seu valor nunca é exibido.

## Roteiro cronometrado

### 0:00–0:20 — iniciar a API local

No Terminal 1, inicie o servidor sem recarga automática:

```bash
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Espere a mensagem de inicialização. Se a porta estiver ocupada, pare o processo anterior; não
mude para um host ou serviço remoto.

### 0:20–1:05 — apresentar o chat controlado

Abra `http://127.0.0.1:8000/demo-chat`. Mostre primeiro a conversa segura de Minecraft e o
estado pronto para captura. Use **Revelar pedido N**, ou as teclas **→** e **Espaço**, para
revelar os quatro pedidos pessoais, um por vez. Narre a progressão: idade, escola, Instagram e
foto. Ao final, mostre o estado **Risco completo / Pronto para captura**.

### 1:05–1:30 — disparar a classificação oficial

No Terminal 2:

```bash
bash scripts/run-live-demo.sh
```

O launcher valida apenas o runtime e a API locais, abre `/demo-chat` e imprime `mode=...` ou
`source=...`.
Não esconda uma eventual mensagem de erro de `live-demo`; mostre a linha
`source=FIXTURE_FALLBACK` antes de a fixture separada começar. Aguarde no terminal as linhas
`assessment=`, `decision=`, `incident=`, `parent_view=` e `child_view=`.

### 1:30–2:35 — mostrar incidente, política e desbloqueio

Abra a URL `parent_view` exibida no Terminal 2. Mostre o risco alto, a evidência mínima e a regra
familiar determinística `DANGEROUS_CONTACT = BLOCK`.

Abra `child_view`, envie uma explicação curta e volte à visão do responsável. Desbloqueie o
aplicativo. No Terminal 2, confirme `unlocked=Guardian Demo Chat`; essa linha prova o ciclo
incidente → revisão → comando → confirmação local.

### 2:35–3:00 — reset visual

Volte a `/demo-chat`, acione **Reset** (ou pressione **R**) e confirme que somente a mensagem
segura reaparece e que o estado pronto para captura foi restaurado. Encerre destacando que o
mesmo resultado pode ser ensaiado novamente sem conteúdo externo ou permissões do macOS.

## Recuperação rápida

- `API local indisponível`: mantenha o erro visível, inicie o Terminal 1 e execute o launcher
  novamente.
- `source=FIXTURE_FALLBACK`: continue o roteiro; o erro anterior já explicou a troca de origem.
- Incidente antigo ou duplicado: pare a API, execute `bash scripts/reset-demo.sh`, reinicie a API
  e recomece o ensaio.
- O navegador não abriu: mantenha o erro visível e abra manualmente
  `http://127.0.0.1:8000/demo-chat`; não substitua o fluxo por uma URL externa.

Faça dois ensaios completos antes da apresentação: um com `LOCAL_FIXTURE` (estado atual) e, caso
o subcomando local seja integrado depois, outro com `LOCAL_LIVE_DEMO` ou
`FIXTURE_FALLBACK`. Congele mudanças após os dois ensaios passarem em menos de três minutos.
