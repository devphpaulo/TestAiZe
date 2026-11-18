# Cabeçalho unificado

O cabeçalho compartilhado usa o seletor **Quadros** para abrir Sessões, Bugs ou Automação. Nas páginas internas, a opção inicial Quadros permite retornar também ao quadro da categoria atual. Automação permanece indisponível quando o ambiente não oferece esse recurso.

O botão de aparência reúne os ícones de tema e paleta. O painel oferece Claro e Escuro na primeira linha e as cinco cores existentes abaixo. As preferências continuam armazenadas nas mesmas chaves locais, inclusive para sincronização do Mini Player. Escape fecha o painel e devolve o foco ao botão; clicar ou mover o foco para fora também fecha.

O indicador “Nesta máquina” foi retirado do cabeçalho. As ações Modo Kanban/Modo lista e Mini Player foram preservadas, com apresentação compacta em telas estreitas.

## Validação

- 116 testes Python e 25 testes JavaScript aprovados.
- Navegador com dados sintéticos: temas claro/escuro, paleta, persistência após navegação, detalhe de bug → quadro de Bugs, Player → Sessões e acesso a Automação.
- Player em 390 px: Modo Kanban, ícone do Mini Player, select e botão de aparência visíveis; painel dentro da tela.
- Revisão independente dan-delivery-review: dois achados de navegação corrigidos; revisão final sem achados bloqueantes.
- Build Windows gerado em `dist/barra-unificada/TestAiZe-01.005.000.exe` (55,78 MB); smoke aprovou servidor local, assets do cabeçalho e host Qt de captura.
