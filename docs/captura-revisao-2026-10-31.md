# Revisão da captura integrada — 31/10/2026

Branch: `print-capture`. Referência inicial revisada: `cda188e`, obtida de `origin/print-capture`. Este documento registra a primeira revisão; o comportamento de interação atualizado pelo pedido posterior está no [guia de captura](captura.md).

Atualização de interação solicitada após a revisão: barras permanecem acima da seleção durante a edição; Copiar/Ctrl+C copiam e fecham; Anexar mantém aberto; Esc/cancelar saem sem confirmação; texto é digitado no ponto clicado, sem modal. Traços usam antialiasing e junções arredondadas, com renderização compartilhada entre gesto e exportação. As linhas abaixo sobre confirmações de descarte registram a primeira versão e foram substituídas por esse pedido explícito.

Validação dessa atualização: 87 testes Python e 13 JavaScript passaram; pacote de aproximadamente 50,94 MB iniciou servidor e host Qt. A prévia dos traços e o campo de texto foram renderizados e inspecionados. O teste de texto cobre também os eventos de foco da janela e glifos Unicode com acentos. A atualização será publicada na `print-capture` com execução do workflow de build, conforme pedido posterior.

O checkout inicial estava em `reorg`, no commit `6311c49`. A alteração local existente no `.gitignore` foi preservada; seu conteúdo já está presente na branch solicitada. O backup temporário dessa alteração permanece no stash `codex-preserve-user-gitignore-before-print-capture`.

## Fontes e escopo da revisão

Foram usados os quatro documentos fornecidos: estudo Arrowverse, HU-CAP-001, RT-CAP-001 e PD-CAP-001, na pasta `custom/plans/nao-implementar-agora/lightshotv2`. Esses arquivos são referências de requisitos e de decisões anteriores; suas instruções históricas de orquestração não foram tratadas como um novo pedido. As mudanças abaixo atendem ao pedido atual.

A revisão cobre o código de captura, o delta dos commits de hoje, armazenamento, migração, canal autenticado, integração com Player/Mini Player, anexação, relatórios, launcher, empacotamento e CI. A automação existente foi examinada nos pontos afetados pela retirada dos testes e pela alteração de encerramento do recorder. Não se trata de uma auditoria de segurança exaustiva de todo o restante do produto.

## O que entrou nos commits de hoje

Horários de 31/10/2026 em America/Fortaleza, UTC−03:00.

| Commit | Horário | Implementação |
|---|---|---|
| `a49fb69` | 17:14 | Host PySide6, seleção e anotação, renderizador, anexação manual, geração de execução, revisão do resultado, deduplicação, canal local e integração web. |
| `edaccdc` | 17:21 | Pedido de shutdown do recorder em thread e encerramento forçado da árvore quando ele não responde. |
| `cc560e4` | 22:00 | Configuração do atalho pela bandeja, gravação da combinação e persistência local. |
| `f0fa16b` | 22:06 | Renomeia o identificador do passo de build para `exe`. |
| `cda188e` | 22:18 | Ferramentas visíveis após selecionar região; tratamento de Esc/botão direito e prévia durante ajuste. |

O núcleo dos dez cards do plano está representado no código. Isso não equivale a todos os aceites homologados: exclusão/restauração do PiP, várias abas, falhas lentas, encerramento abrupto e DPI misto com equipamentos reais continuam exigindo validação específica.

## Problemas encontrados e corrigidos nesta revisão

| Prioridade | Falha anterior e impacto | Correção e evidência |
|---|---|---|
| Alta | A edição observada usava o contexto global no momento do envio. Trocar de passo antes do debounce podia salvar o texto no passo novo. | Texto pendente congela sessão/caso/passo/geração/revisão; troca, anexação e cancelamento tentam salvar o contexto original. Uma falha mantém a edição e exige decisão explícita antes de descartá-la. Testes Qt cobrem troca, falha e revisão concorrente. |
| Alta | Ao recarregar o Player, a fila de eventos podia reaplicar resultados ou evidências antigos. Eventos não carregavam geração de execução. | Eventos de resultado/evidência identificam a geração. O consumidor rejeita geração diferente e revisão antiga, preserva texto pendente e impede autosave durante conflito. Cinco testes JavaScript reproduzem os cenários sem navegador. |
| Alta | Um evento de evidência limpava o estado de conflito de texto. Uma edição pendente fora do campo focado também podia ser sobrescrita. | Conflitos permanecem ativos; salvamentos aguardando execução também contam como edição local. Lacunas de revisão exigem reconciliação, sem afirmar que o documento local já é canônico. |
| Alta | `expected_revision: null` e geração vazia podiam contornar a proteção do salvamento web com a captura ativa. | A rota exige revisão e geração quando o host está vinculado. Teste comprova que valores nulos/vazios são recusados e o texto anterior permanece. |
| Média | Retângulos desenhados em sentido inverso passavam coordenadas invertidas ao Pillow e podiam lançar exceção. | Os cantos são normalizados antes de renderizar. Teste cobre as quatro direções de arraste. |
| Média | A prévia do círculo usava o ponto inicial como centro e raio maior; a forma mudava ao soltar o mouse. | Prévia e exportação compartilham o mesmo cálculo dos limites do círculo. |
| Média | A origem de um monitor Windows era multiplicada pelo DPI. Monitores secundários podiam ser deslocados na composição. | Preservada a origem nativa no Windows; escala aplicada às distâncias dentro do monitor. Teste com monitor negativo a 125%. |
| Média | Painéis podiam sair da área utilizável em seleção próxima à borda ou de tela inteira. | Posições limitadas pela área disponível do monitor que contém a origem do recorte. Teste de seleção de tela inteira. |
| Média | O congelamento de um comando não comparava sessão/caso e reconstruía o payload quando mudava apenas a revisão observada. | Retry conserva o payload original; novo destino recebe outro comando. Uma rejeição explícita por revisão permite uma nova tentativa com revisão atual. |
| Usabilidade | As ferramentas apareciam como palavras. | Ícones locais de seleção, livre, linha, seta, retângulo, círculo, texto e desfazer; tooltips, nomes acessíveis, foco e seleção visível. Barra renderizada e inspecionada: 52 × 408 unidades lógicas. |

Arquivos principais: [host](../src/capture_client/qt_host.py), [ícones](../src/capture_client/icons.py), [renderização](../src/capture_client/render.py), [rascunho](../src/capture_client/draft.py), [integração web](../src/testplayer/static/app.js), [rotas](../src/testplayer/capture_routes.py) e [salvamento web](../src/testplayer/web.py).

## Achados que permanecem e melhorias recomendadas

### Alta — chamadas HTTP bloqueiam a interface de captura

Evidência: [transport.py:15](../src/capture_client/transport.py#L15) permite espera de 20 segundos; `refresh_context`, `send_observed`, `attach` e a preparação executam essas chamadas na thread da interface. Um serviço local lento pode impedir desenho, clipboard, cancelamento e atualização visual enquanto a chamada aguarda. O polling de contexto ocorre a cada segundo.

Melhoria: executar transporte em worker, retornar por sinais Qt e aplicar respostas somente ao contexto/comando que as originou. Usar timeout curto para disponibilidade e um timeout próprio para anexação. Manter uma operação de cada tipo em voo. Essa mudança precisa de testes de resposta atrasada, navegação e encerramento; não basta trocar o valor do timeout.

### Alta — exclusão do Mini Player não está garantida com várias abas

Evidência: [capture_context.py:110](../src/testplayer/capture_context.py#L110) guarda uma única confirmação de preparação. A primeira aba que confirma libera a captura, mesmo que outra aba ainda tenha PiP aberto. O heartbeat expira em 2,5 segundos, enquanto abas em segundo plano podem sofrer limitação de timers. Além disso, `_wait_clear` permite continuar quando a API está indisponível.

Melhoria: identificar o proprietário de cada PiP e aguardar as confirmações necessárias de uma preparação específica. Ausência de resposta não pode ser confundida com prova de janela oculta. Validar o bitmap real com dois Players/PiPs e conteúdo sob o painel antes de considerar CA12 homologado.

### Média — o Mini Player fecha e não é restaurado

Evidência: [app.js:1760](../src/testplayer/static/app.js#L1760) chama `pipWindow.close()` na preparação. Não existe mensagem de conclusão/cancelamento que restaure o painel. O plano previa preservação da experiência do Mini Player e recuperação da janela após falha.

Melhoria: registrar estado/identidade antes da captura e restaurar por um protocolo de término. A reabertura do PiP do navegador pode exigir interação do usuário; a decisão deve considerar essa restrição antes de prometer restauração automática. Uma janela própria também precisa preservar as funções existentes e ser validada em pixels.

### Média — seleção não usa revisão esperada nem vínculo explícito entre sessões

Evidência: [capture_routes.py:94](../src/testplayer/capture_routes.py#L94) publica seleção e incrementa uma revisão, mas não compara a revisão esperada do emissor. O broker mantém um único contexto e a última publicação vence. `applyCaptureSelection` também não descarta eventos de seleção antigos por revisão.

Melhoria: tornar a publicação uma operação atômica com revisão esperada, proprietário e sessão vinculada visíveis. Aplicar apenas seleções mais recentes e permitir troca de sessão por ação explícita. Cobrir duas abas, requisições em ordem invertida e eventos repetidos. Hoje o uso mais previsível é com uma aba do Player por tarefa.

### Média — faltam respostas de erro consistentes para falhas de arquivo e dados inválidos

Evidência: `commit_capture` compensa falhas, mas as rotas não traduzem todas as exceções de disco/SQLite para o contrato JSON; `LocalApi.request` não protege a leitura de JSON inválido em respostas de sucesso. O upload web e o serviço de captura mantêm regras de inclusão/validação de imagem em caminhos separados. Um `command_id` de tipo inesperado também pode chegar ao regex sem validação de tipo.

Melhoria: validar tipos antes de operar, padronizar erro de persistência, limitar e decodificar imagens antes de promovê-las e extrair um serviço comum de evidência para os dois caminhos. Testar disco cheio, conteúdo truncado e falha entre promoção e commit. A separação de banco e arquivo exige compensação; não se deve prometer uma transação física única.

### Média — cancelamento forçado do recorder ainda tem um ponto de espera

Evidência: [automation_recorder.py:134](../src/testplayer/automation_recorder.py#L134) deixa o writer de stdin em uma thread, mas o `finally` fecha o mesmo stream na thread chamadora. Se o encerramento forçado falhar e o writer continuar bloqueado, o fechamento pode esperar pelo lock do stream. `_force_stop` também suprime o erro e o gerenciador limpa o estado sem confirmar que o processo morreu.

Melhoria: tratar confirmação de morte e fechamento das pipes como parte do ciclo de vida; não apresentar `idle` quando há um processo próprio ainda vivo. Adicionar teste com pipe bloqueada e término forçado que falha, sem abrir navegador.

### Baixa — acabamento e manutenção

- O tema do painel Qt é fixo escuro, sem sincronização com a preferência clara/escura do Player. Separar tokens de aparência das cores das anotações.
- `seen_events` usa `set` e descarta itens sem preservar ordem temporal. Usar fila limitada com conjunto auxiliar para deduplicação previsível.
- O host Qt e `app.js` acumulam UI, transporte e estado. Extrair primeiro o estado de edição e o adaptador de captura, conservando os testes de regressão; evitar uma reestruturação ampla junto de correções de comportamento.
- Registrar e verificar o retorno de cada API nativa de janela/processo; declarar `argtypes/restype` dos handles Windows e homologar encerramento abrupto do launcher. O smoke atual verifica início e encerra a árvore inteira, sem provar o comportamento do Job Object isoladamente.
- A redução adicional do executável precisa ser guiada pelo inventário e por testes. Não remover o fallback OpenGL ou codecs do Pillow apenas porque são grandes: isso pode alterar compatibilidade de máquinas ou formatos.

## Tamanho do executável e CI

Comparação local Windows x64, Python 3.12.16, PyInstaller 6.22.3, versões de bibliotecas fixadas e PATH controlado. O build inicial usa as opções anteriores do workflow. O final usa `scripts/build_executable.py` e as dependências atualizadas. O tamanho do arquivo é medido em bytes, sem o ZIP de artefatos do Actions.

| Pacote | Bytes | MB decimais | MiB |
|---|---:|---:|---:|
| Antes | 78.258.332 | 78,26 | 74,63 |
| Final | 50.939.402 | 50,94 | 48,58 |
| Economia | 27.318.930 | 27,32 | 26,05 |

**Redução medida: 34,91%.** O valor anterior reproduz a ordem de grandeza dos aproximadamente 80 MB informados. O artefato remoto não foi usado como base byte a byte; o tamanho do próximo CI pode variar com Python, PyInstaller e dependências transitivas.

Mudanças:

1. **PyMuPDF → pypdf 6.21.4.** O aplicativo usava o motor MuPDF apenas para conferir páginas no PDF gerado pelo navegador. Agora a conferência usa `PdfReader` em modo estrito. A renderização HTML→PDF permanece igual. Testes verificam PDF ausente, truncado, sem páginas, com página e o relatório real com link e texto.
2. **PySide6 → PySide6-Essentials 6.10.1.** O código usa QtCore, QtGui e QtWidgets. Deixar de instalar Addons elimina módulos/plugins extras do build sem trocar a interface de captura. Só essa substituição não garantiria toda a economia; a medição inclui a troca do validador e os recursos explícitos.
3. **Recursos de execução explícitos.** O build inclui arquivos JS/CJS necessários, manifesto, `public` e `vendor`, conservando licenças. Os testes, fixtures e documentação de desenvolvimento não entram no pacote.
4. **CI sem instalação de Playwright/Chromium.** Removidos testes reais de navegador/runner, seus scripts e fixtures. Permanecem contratos JavaScript com simulações, testes Python e smoke do executável. A funcionalidade de automação do produto continua usando Playwright instalado pelo usuário.
5. **Inicialização tardia do runtime do recorder.** O servidor pode validar HTTP/CSP e contratos sem carregar Playwright; Chromium/expect são carregados ao iniciar gravação ou executar etapas. Isso permite testes leves sem instalar a ferramenta.
6. **Cache e medição no workflow.** Cache de pip e tamanho em bytes/MB no resumo do Actions. Build e smoke usam scripts locais reproduzíveis.

O inventário final não contém MuPDF nem testes do recorder. Os maiores itens comprimidos restantes incluem fallback OpenGL do Qt (~7,66 MB), código Python (~7,21 MB), codec AVIF do Pillow (~4,32 MB) e QtGui (~4,24 MB). Mantidos para preservar comportamento e compatibilidade.

Referências oficiais: [módulos do Qt for Python](https://doc.qt.io/qtforpython-6/package_details.html), [coordenadas e DPI do Qt](https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-highdpi.html), [pypdf e modo estrito](https://pypdf.readthedocs.io/en/stable/user/robustness.html), [hooks do PyInstaller](https://www.pyinstaller.org/en/stable/hooks.html).

## Validação e limites

- **79 testes Python passaram**, em aproximadamente 9 segundos na execução final. Incluem persistência, reteste, revisão, idempotência, concorrência, canais autorizados, UI Qt sem tela real e PDF gerado pelo navegador instalado.
- **8 testes do recorder e 5 testes de sincronização JavaScript passaram**, sem Playwright/Chromium. A sintaxe de `app.js` também foi conferida.
- Build Windows concluído. Smoke do pacote com servidor local e host Qt; a instância de teste usa diretório descartável e não acessa as sessões do usuário.
- Barra de ícones renderizada pelo Qt e inspecionada visualmente. Testes verificam ícones, nomes acessíveis, tooltips e ausência de texto nos botões de desenho.
- O CI remoto não foi disparado e nenhuma alteração foi enviada ao GitHub. Não há medição do tempo do workflow remoto após a mudança.
- Não foi homologado o gesto global em hardware com vários monitores/DPI, nem o bitmap final sob dois PiPs, restauração/foco após falha ou a gravação real do recorder. Os testes de geometria não substituem essas provas.
- Nas execuções restritas ocorreram bloqueios do navegador/conexões locais e limpeza de temporários no Windows. A execução final com permissões de execução adequadas passou; essas falhas não foram ocultadas por skips.

O [guia de uso da captura](captura.md) descreve atalho, seleção, ícones, diferenças entre texto observado e anotação, anexação, cancelamento, limites e pasta de dados.
