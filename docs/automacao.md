# Automação e Cofre

## Execução local

Abra `executar.bat` ou execute `python src/launcher.py`. Não há compilação do recorder, diretório `dist` nem executável gerado localmente. Todo o código da aplicação está em `src`: Python em `src/testplayer` e JavaScript do worker em `src/playwright-recorder`.

## Detecção automática

Cada abertura cria uma nova verificação de Node.js, Playwright Codegen e Chromium. A aplicação não instala nem inclui Node ou Playwright. Se faltar uma ferramenta, o launcher registra o aviso, a home mostra o motivo e a aba Automação fica oculta. A rota direta e a API de start também ficam indisponíveis. As sessões manuais continuam funcionando.

A versão compatível é Node.js 20+ e Playwright 1.62.1. A versão do Playwright é verificada porque a geração incremental ainda usa `_enableRecorder`, isolado no adapter e protegido pelos testes.

O probe procura instalações existentes nos caminhos de módulos do Node, no prefixo npm do usuário, ao lado dos comandos Playwright no PATH e nos prefixos globais usuais. Para uma instalação em diretório diferente, configure `TESTAIZE_PLAYWRIGHT_PATH` ou `NODE_PATH` antes de iniciar o BAT. Não há varredura do disco nem uso de `npx` para baixar pacotes automaticamente.

Para preparar o ambiente manualmente:

```powershell
npm install --global @playwright/test@1.62.1
playwright install chromium
```

Também é reconhecida uma instalação compatível do pacote `playwright`, com seu Codegen e módulo `playwright/test`. Reinicie o aplicativo depois de instalar ou remover ferramentas: a disponibilidade é decidida na abertura.

## Interface

O menu Automação abre a biblioteca em `/iniciativas/automacao`, com pastas, ciclos e scripts. **Gravar teste avulso** abre `/iniciativas/automacao/gravacao` sem exigir organização prévia. O worker usa diretamente `carbon.css` e `ui-fixes.css` do TestAíZé. A gravação organiza destino, navegador e editor com abas **Código gerado** e **Etapas para executar**. Cores, tema e contraste dos botões seguem os tokens do aplicativo.

## Pastas, ciclos e arquivos

Crie, renomeie ou exclua pastas e ciclos pela biblioteca. Na gravação, **Salvar .spec.ts** baixa o código mostrado no editor. **Salvar na biblioteca** permite escolher ou criar uma pasta e ciclo, e dar nome ao script. Salvar novamente na mesma iniciativa atualiza esse script.

Clique no arquivo da biblioteca para revisar o código, alterar nome/ciclo, salvar alterações e baixar a versão persistida. Scripts e metadados ficam em `Documentos/TestAiZe/automacao`, ou no diretório configurado por `--data-dir`, separados das sessões manuais. Os diretórios usam IDs estáveis; os nomes são exibidos pela biblioteca. Eles permanecem após fechar o aplicativo e são incluídos no backup existente (`--backup`), junto com o histórico de suítes.

## Execução de suítes

**Rodar suíte** executa todos os scripts da pasta, ou somente o ciclo selecionado. No editor de script, **Rodar ciclo** executa o ciclo daquele arquivo salvo. Alterações no editor precisam ser salvas antes de executar.

O runner usa Playwright Test do ambiente, em processo separado do recorder. A tela acompanha total, aprovados, reprovados, ignorados, duração e motivo de cada falha. O histórico guarda cada execução. Um arquivo pode conter mais de um `test`: a métrica conta testes efetivos, não apenas arquivos.

Cada execução recebe uma cópia dos scripts e dos valores atuais do Cofre. Editar ou excluir um script depois não altera uma execução iniciada nem seus resultados. O relatório remove valores secretos antes de gravar no disco. Não são habilitados screenshots ou traces automáticos que possam registrar credenciais. O Cofre continua somente em memória.

Há uma suíte ativa por aplicativo, um worker e nenhum retry automático. O limite padrão é 30 segundos por teste e cinco minutos por suíte. **Cancelar execução** encerra somente a árvore do runner criado pelo aplicativo. Ao reabrir, um histórico que ficou em andamento é marcado como interrompido e pode ser executado novamente.

## Cofre

O botão com cadeado abre o Cofre. As chaves iniciais são `PLAYWRIGHT_EMAIL` e `PLAYWRIGHT_PASSWORD`. Você pode cadastrar outras chaves, alterar valores, marcar Secret ou limpar entradas.

Campos de senha geram `process.env.PLAYWRIGHT_PASSWORD ?? ""`. Campos `type=email`, ou cujo identificador, nome, autocomplete, label ou placeholder indique e-mail, geram `process.env.PLAYWRIGHT_EMAIL ?? ""`. O valor digitado é substituído antes de qualquer emissão de código. Se a classificação falhar, o adapter mantém a máscara conservadora de senha.

Ao rodar as etapas, o worker usa os valores atuais do Cofre. Para outras chaves, use `process.env.SUA_CHAVE` nas etapas editáveis. Atualizações seguem pela pipe privada de controle do worker, sem reiniciar Chromium e sem passar pelo protocolo público WebSocket.

Secret oculta o valor nas consultas. Depois de salvar, o valor recém-digitado permanece mascarado no campo e aparece **Valor salvo nesta execução**. Ao fechar/reabrir o diálogo, o valor não é reenviado ao navegador: uma máscara fixa e a confirmação indicam que ele continua cadastrado. Os valores ficam somente em memória durante a execução do aplicativo: nenhum arquivo, banco ou armazenamento do navegador é usado para persistir o Cofre.

Chaves de runtime, como `NODE_OPTIONS`, `PATH` e `RECORDER_*`, são reservadas. O Cofre aceita chaves em maiúsculas com números e underscores, como `API_TOKEN`.

## Ciclo de vida e API

Abrir a biblioteca não inicia recorder ou Chromium. O worker inicia somente ao entrar na gravação, em porta loopback efêmera; Chromium inicia após **Iniciar**. Readiness, health, CSRF, ownership por página, stop idempotente, presença periódica e watchdog permanecem. Scripts persistidos são independentes dos casos manuais.

| Método | Rota | Função |
|---|---|---|
| GET | `/iniciativas/automacao` | Biblioteca de automação |
| GET | `/iniciativas/automacao/gravacao` | Iniciativa avulsa |
| GET | `/iniciativas/automacao/pastas/<id>` | Ciclos, scripts e histórico |
| POST/PUT/DELETE | `/api/iniciativas/automacao/pastas`, `/ciclos`, `/scripts` | CRUD protegido por CSRF |
| GET | `/api/iniciativas/automacao/scripts/<id>/download` | Download do script salvo |
| POST | `/api/iniciativas/automacao/execucoes` | Iniciar suíte com snapshot |
| GET | `/api/iniciativas/automacao/execucoes/<id>` | Métricas e resultados |
| POST | `/api/iniciativas/automacao/execucoes/<id>/cancelar` | Cancelar o runner ativo |
| POST | `/api/iniciativas/automacao/recorder/start` | Iniciar worker instalado em `src` |
| POST | `/api/iniciativas/automacao/recorder/stop` | Encerrar worker do proprietário |
| GET | `/api/iniciativas/automacao/recorder/status` | Estado e presença da página |
| GET | `/api/iniciativas/automacao/cofre` | Metadados e valores não secretos, sem cache |
| POST | `/api/iniciativas/automacao/cofre` | Salvar ou limpar chave com CSRF |

## Testes e GitHub Actions

Na raiz: `python -m unittest discover -s tests`.

Com Playwright instalado no ambiente: `npm --prefix src/playwright-recorder test`, `npm --prefix src/playwright-recorder run test:e2e` e `npm --prefix src/playwright-recorder run test:host`. Não há `npm ci`, TypeScript ou build intermediário para executar o código da aplicação.

O workflow prepara Node e Playwright somente no runner para testar a integração. PyInstaller inclui o código JavaScript e os assets do aplicativo no `.exe`, mas não inclui Node, Playwright, browsers nem diretório de runtime portátil. `dist` existe apenas como saída do job de build no Actions. O smoke do executável usa as ferramentas do runner, como acontecerá na máquina de quem usar a aplicação.

A biblioteca JavaScript `ws` 8.21.3 do transporte local está em `src/playwright-recorder/vendor/ws`, com sua licença MIT. Ela pertence ao código do worker; não é um runtime Node nem uma cópia de Playwright.
