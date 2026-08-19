# Permissões do agente no macOS

O Guardian só declara o observer real como pronto quando as permissões **Gravação da Tela** e
**Acessibilidade** estão ativas. A câmera e o microfone não são solicitados.

## Onboarding

1. Compile o helper com `swift build --package-path native/GuardianCaptureHelper -c release`.
2. Consulte o estado sem abrir diálogos:

   ```bash
   native/GuardianCaptureHelper/.build/release/guardian-capture-helper permissions
   ```

3. Para abrir os prompts do macOS, execute explicitamente:

   ```bash
   native/GuardianCaptureHelper/.build/release/guardian-capture-helper permissions --request
   ```

4. Se o resultado tiver `ready: false`, abra **Ajustes do Sistema → Privacidade e Segurança**,
   habilite Gravação da Tela e Acessibilidade para o terminal/aplicativo que executa o Guardian e
   reinicie esse processo.

O comando retorna `0` somente quando ambas estão prontas e `2` quando falta alguma permissão. Ele
nunca tenta capturar uma tela durante a simples consulta de estado.
