# HU-BUG-001 — ajustes de interface

Pedido de 04/11/2026: correções dos 15 pontos indicados nas capturas do usuário.

## Alterações

| Pontos | Entrega |
|---|---|
| 1 e 12 | Quadro com CSS próprio, títulos e contadores sem sobreposição; card com identificador, nome, data e severidade no canto inferior direito. |
| 2 e 3 | Imagens sem moldura ou controles permanentes. Selecionar exibe alças nas bordas/cantos; arrastar conserva proporção e largura percentual. Delete/Backspace excluem a imagem selecionada; setas ajustam largura. Retornar ao texto ou navegar pelo teclado limpa a seleção. |
| 4 e 9 | Ações de reteste e vínculo no canto superior direito das respectivas seções. Removidos os rótulos vazios de reteste e vínculos. |
| 5, 6, 11 e 13 | Modal inspirado no exportador de relatórios: cabeçalho e rodapé fixos, lista com rolagem, agrupamento por pasta, seleção individual/em lote, busca, contadores, borda discreta e temas claro/escuro. Escape fecha e devolve o foco ao botão de abertura. |
| 7 e 8 | Aprovados não aparecem na seleção. Casos exibem badge de status à direita. O servidor continua revalidando e recusando aprovados caso o estado mude durante a seleção. |
| 10 | Vínculos exibem o nome do caso e seu status atual na execução correspondente, resolvidos por `(session_id, case_id)`. O identificador da sessão deixa de ser o texto da linha. Vínculos inativos continuam identificados. |
| 14 e 15 | Campos, select, textarea, editor, busca, botões e badges com tokens e estilos inspirados no shadcn, aplicados à stack Flask/Jinja existente. |

## Severidade

A solicitação atual substitui a decisão anterior de severidade textual livre. Criação e edição agora aceitam **Baixa, Média, Alta e Bloqueador**, com código normalizado no banco. Acentos e capitalização dos rótulos são reconhecidos. Registros históricos não são reescritos automaticamente; um valor antigo fora da lista é mostrado como atual e exige uma escolha válida para salvar a edição.

## Validação

- 114 testes Python passaram, incluindo resolução de nomes/status em duas execuções com o mesmo `case_id`, select, obrigatórios e enum de severidade e destino alternativo do build.
- 12 testes JavaScript de editor/status/captura e 8 testes do recorder passaram.
- No navegador: Kanban, campos e modal nos temas claro/escuro; modal em 390 px; seleção por pasta e contador; aprovados ausentes; busca sem resultados; vínculo e nomes/status das linhas; arraste lateral de 65% para 50%; Delete/Backspace; salvamento e largura preservada após recarga; navegação com Tab/Shift+Tab e fechamento por Escape com retorno do foco.
- Revisão independente `dan-delivery-review`: SEM ACHADOS BLOQUEANTES após corrigir a seleção de imagem ao retornar ao texto pelo teclado.
- O smoke do pacote também verifica a presença de `bugs.css`, além dos templates, JavaScript, banco global e host Qt já cobertos.

O CSS de bugs é carregado depois dos estilos globais e usa classes próprias, evitando as colisões que causaram os títulos e o modal claro incorretos. Não houve migração de framework nem alteração nos estilos dos campos do Player.

## Pacote Windows

O build aceita `--dist-dir` para gerar uma saída alternativa sem substituir um executável em uso. Nesta entrega, o pacote está em `dist/ajustes-visuais/TestAiZe-01.005.000.exe`; o destino padrão de builds e do CI continua sendo `dist/`.
