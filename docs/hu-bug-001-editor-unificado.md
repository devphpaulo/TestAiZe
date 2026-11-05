# Editor de imagens unificado — Bugs e Test Player

Pedido de 04/11/2026: recuperar imagens com Ctrl+Z, padronizar o redimensionamento e remover o foco azul duplo de todos os campos de bugs.

- Bugs, resultado observado, pré-condições e comentários do Player usam o mesmo componente de seleção e alças nas bordas/cantos. Imagens não exibem moldura permanente, nome, botão de remoção ou controle de largura.
- Delete/Backspace excluem a imagem selecionada. Ctrl+Z restaura posição e largura; Ctrl+Y/Ctrl+Shift+Z refazem. A largura também pode ser ajustada pelas setas e desfeita.
- O histórico de imagens usa assinaturas do documento para respeitar a ordem da edição nativa de texto. Digitar depois de uma exclusão não faz Ctrl+Z ignorar o texto e restaurar primeiro a imagem.
- Durante a edição do bug, os arquivos locais continuam disponíveis até o salvamento explícito. No Player, uma cópia dos bytes é preservada antes da exclusão; se o arquivo já foi removido pelo autosave, desfazer o envia novamente e atualiza a referência no documento. O autosave aguarda a conclusão dessas operações.
- Operações rápidas de excluir/desfazer são serializadas por imagem. Falhas de restauração impedem declarar o documento salvo com uma referência inválida.
- Os uploads de restauração enviam a geração esperada. Uma página de execução antiga não pode restaurar uma imagem em outra execução do caso.
- Campos do bug, select, textareas e editores têm uma única borda cinza de 1 px no foco, sem outline azul ou sombra. As alças azuis permanecem apenas na imagem selecionada.

O histórico pertence à edição da página atual; recarregar ou abrir outra página inicia um novo histórico. O autosave do Player não encerra esse histórico.

## Evidências

- 115 testes Python passaram, incluindo rejeição de upload de restauração em geração antiga nos passos, pré-condições e comentários.
- 14 testes JavaScript de imagens/status/captura e 8 testes do recorder passaram. A cobertura inclui restauração após exclusão, IDs atualizados, corrida com exclusão pendente, falha de upload, ordem com texto e múltiplas exclusões.
- Navegador: bug Delete → Ctrl+Z → Ctrl+Y → Ctrl+Z → salvar; Player Delete → aguardar autosave → Ctrl+Z → aguardar autosave → recarregar. Imagens e largura foram preservadas.
- Pré-condições e comentários: excluir a única imagem, aguardar autosave, desfazer e recarregar conservou a imagem.
- Player: arraste lateral de 65% para 55%, seguido de Ctrl+Z, retornou a 65%. Undo de texto intercalado manteve as imagens.
- Estilos computados nos temas claro/escuro confirmaram borda de 1 px cinza, outline desativado e ausência de sombra no foco dos campos e editores afetados.
- Revisão independente `dan-delivery-review`: SEM ACHADOS BLOQUEANTES.

Novo pacote: `dist/editor-unificado/TestAiZe-01.005.000.exe`. O smoke verifica os assets compartilhados, servidor e host Qt sem substituir o executável anterior em uso.
