# UI Sleek

Refatoração visual na branch `refactor`, a partir de `reorg`. Nenhuma funcionalidade ou domínio foi adicionado.

## Escopo inspecionado

- `src/playwright-recorder/playwright-recorder-adapter.js` — 165 linhas; SHA inicial `8d8525d488e1`.
- `src/playwright-recorder/public/app.js` — 407 linhas; SHA inicial `3adeb6cab52f`.
- `src/playwright-recorder/public/embedded.js` — 36 linhas; SHA inicial `9290120ab20d`.
- `src/playwright-recorder/public/index.html` — 46 linhas; SHA inicial `f3deebc547d7`.
- `src/playwright-recorder/public/styles.css` — 68 linhas; SHA inicial `b69382557d23`.
- `src/playwright-recorder/recorder-session.js` — 626 linhas; SHA inicial `165ded66d586`.
- `src/playwright-recorder/test/e2e.test.js` — 289 linhas; SHA inicial `8b895e5052ef`.
- `src/playwright-recorder/test/fixture.html` — 38 linhas; SHA inicial `08e70e0933df`.
- `src/playwright-recorder/test/host.test.js` — 292 linhas; SHA inicial `bab524d48074`.
- `src/playwright-recorder/test/recorder-adapter.test.js` — 145 linhas; SHA inicial `26fc09a86858`.
- `src/testplayer/automation_routes.py` — 129 linhas; SHA inicial `b55ccfb6599f`.
- `src/testplayer/static/app.js` — 1619 linhas; SHA inicial `ea942fe6594d`.
- `src/testplayer/static/automation-library.css` — 51 linhas; SHA inicial `45269cf1f2cc`.
- `src/testplayer/static/automation-library.js` — 79 linhas; SHA inicial `c680990f882f`.
- `src/testplayer/static/automation-save.js` — 92 linhas; SHA inicial `d76b95eee599`.
- `src/testplayer/static/automation-script.js` — 17 linhas; SHA inicial `e9c44cc3bcf3`.
- `src/testplayer/static/automation.css` — 43 linhas; SHA inicial `cfb454654ff0`.
- `src/testplayer/static/automation.js` — 112 linhas; SHA inicial `a286bdd886fa`.
- `src/testplayer/static/carbon.css` — 42 linhas; SHA inicial `6a53fba9b5e9`.
- `src/testplayer/static/report.css` — 158 linhas; SHA inicial `a6857809a914`.
- `src/testplayer/static/style.css` — 341 linhas; SHA inicial `3ea57a478e30`.
- `src/testplayer/static/ui-fixes.css` — 1008 linhas; SHA inicial `50680fc3add3`.
- `src/testplayer/static/vault.js` — 90 linhas; SHA inicial `00e8e16aebe3`.
- `src/testplayer/templates/automation.html` — 33 linhas; SHA inicial `97e892851119`.
- `src/testplayer/templates/automation_library.html` — 38 linhas; SHA inicial `a1df15e3e293`.
- `src/testplayer/templates/automation_run_panel.html` — 6 linhas; SHA inicial `023a3dc872ca`.
- `src/testplayer/templates/automation_script.html` — 10 linhas; SHA inicial `78f642dcfc26`.
- `src/testplayer/templates/automation_unavailable.html` — 5 linhas; SHA inicial `67d16ce64c72`.
- `src/testplayer/templates/base.html` — 48 linhas; SHA inicial `35798492c821`.
- `src/testplayer/templates/choose_folder.html` — 57 linhas; SHA inicial `c645deca48f8`.
- `src/testplayer/templates/home.html` — 89 linhas; SHA inicial `509677b83c3d`.
- `src/testplayer/templates/kanban.html` — 15 linhas; SHA inicial `31e4980e41f2`.
- `src/testplayer/templates/player.html` — 176 linhas; SHA inicial `42ebb953dc3a`.
- `src/testplayer/templates/preview.html` — 45 linhas; SHA inicial `721d461f18b4`.
- `src/testplayer/templates/report_export.html` — 170 linhas; SHA inicial `342726fb6faf`.
- `src/testplayer/templates/vault_dialog.html` — 13 linhas; SHA inicial `e3f091e3a9d2`.
- `src/testplayer/web.py` — 771 linhas; SHA inicial `a415b0f51642`.

## Contexto e objetivo

Aplicar uma linguagem visual moderna e minimalista ao TestAiZe, preservando seus fluxos, domínio e estrutura de layout. A referência é `plans/implementar-agora/sleek/DESIGN.md` e `SKILL.md`.

## Tokens e fundamentos

| Uso | Token ou valor |
| --- | --- |
| Destaque principal | `--primary: #3B82F6` |
| Destaque secundário / bloqueado | `--secondary: #8B5CF6` |
| Sucesso | `--success: #16A34A` |
| Atenção | `--warning: #D97706` |
| Erro | `--danger: #DC2626` |
| Superfície clara | `--panel: #FFFFFF` |
| Texto claro | `--ink: #111827` |
| Tipografia | Inter; JetBrains Mono para rótulos técnicos e código |
| Cantos | 4px e 8px |
| Espaçamento dos componentes reformulados | 8px, 16px, 24px e 32px |

O azul da marca foi mantido nos destaques. Botões com texto branco usam a variante `--action: #1D4ED8`, cujo contraste é 6,70:1. As cinco cores opcionais têm variantes de ação com contraste mínimo de 5,01:1. Os tokens de status permanecem independentes da cor de personalização.

Fontes variáveis e licenças OFL estão em `src/testplayer/static/fonts/`. As telas usam esses arquivos locais; relatórios HTML/PDF incorporam as fontes. Não há carregamento externo de fontes.

## Componentes e migração

- `layout.css` reúne as declarações estruturais anteriores na ordem original: colunas, larguras, alturas, posição, redimensionamento, rolagem e breakpoints. Os espaçamentos existentes foram preservados quando sua alteração mudaria o layout solicitado pelo usuário.
- `sleek.css` centraliza temas, cores, tipografia, cantos, foco, estados, superfícies e aparência dos componentes. As folhas específicas de automação e do gravador mantêm sua geometria.
- Botões primários, secundários, discretos e destrutivos mantêm as ações existentes. Hover, active, focus-visible e disabled têm estilos próprios.
- Seleções, erros, resultados e progresso combinam cor com rótulos acessíveis. Bloqueado usa violeta; em andamento usa âmbar; aprovado e reprovado usam verde e vermelho.
- Ícones SVG compartilham traço, tamanho e alinhamento. Os controles de status do Mini Player usam o mesmo conjunto do player principal. Os endereços absolutos dos ícones continuam funcionando no Picture-in-Picture.
- As duas confirmações que usavam `window.confirm` agora usam um diálogo Sleek, preservando confirmação, cancelamento e conteúdo da decisão. Escape cancela e o foco retorna ao controle que abriu o diálogo.
- `report.css` aplica a mesma linguagem visual ao HTML exportado e à impressão PDF. A navegação entre casos, evidências, anexos e as regras de quebra de página foram preservadas.

## Acessibilidade e critérios verificáveis

- Foco visível de 2px em controles operáveis por teclado.
- Controles de status mantêm nomes, `aria-pressed` e ícones distintos.
- Diálogos usam título acessível; as confirmações usam também descrição acessível.
- Campos e erros mantêm seus vínculos, `aria-invalid`, `role=status` e `role=alert` existentes.
- `prefers-reduced-motion` desativa transições, animações e rolagem suave.
- Labels longos podem quebrar linha; áreas de código e listas conservam suas regras de overflow.

## Conteúdo e tom

Os textos continuam descrevendo importação de casos, execução manual, automação e relatórios do TestAiZe. As alterações tornam a orientação mais direta: “Importar casos de teste”, “Revise a importação”, “Gravador pronto” e “Valor secreto”. Contagens de sessões e execuções usam singular e plural naturais. Nenhum conteúdo de e-commerce foi incorporado ao produto.

## Padrões proibidos

- Não alterar grids, ordem dos painéis, proporções ou fluxos para introduzir outra organização visual.
- Não recolorir os resultados de teste com a cor escolhida pelo usuário.
- Não depender de CDN para fontes ou ícones.
- Não usar emoji como ícone de ação ou remover o nome acessível de um botão com ícone.
- Não usar branco sobre o azul principal para texto pequeno sem verificar contraste.
- Não adicionar novas funcionalidades como parte da refatoração visual.

## Checklist de QA executado

- [x] Colunas, posição e largura idênticas antes/depois em sessões, pastas, player, Kanban e biblioteca de automação, em 1440px.
- [x] Prévia da importação, pastas, scripts, Cofre, Mini Player e diálogos renderizados e inspecionados.
- [x] Salvamento de status e resultado observado, sincronização do Mini Player e cancelamento das confirmações por Escape.
- [x] Temas claro/escuro e cinco cores; contraste dos botões primários acima de 4,5:1.
- [x] Sessões e player em 390px sem transbordamento horizontal.
- [x] Movimento reduzido respeitado.
- [x] HTML exportado offline e PDF A4 renderizados com fontes incorporadas.
- [x] 10 testes Node e 3 testes E2E do gravador aprovados.
- [x] 48 de 51 testes Python aprovados; os três erros restantes exigem `src/playwright-recorder/run-suite.cjs`, que já estava excluído antes da refatoração. A exclusão pré-existente foi preservada.

Os arquivos de layout legados foram substituídos por `layout.css` e `sleek.css`; referências nos templates, servidor do gravador e contratos de teste foram atualizadas. Não houve alteração de dependências de aplicação.

Verificações finais: a alternância real de tema atualiza o rótulo do botão; Escape fecha o seletor de cor e devolve o foco. As bordas dos editores têm contraste de 4,76:1 no tema claro e 6,34:1 no escuro. A geometria do player foi medida novamente e permaneceu idêntica.
