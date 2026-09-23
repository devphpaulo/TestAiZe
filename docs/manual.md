# Manual de uso do TestAiZe

## Abrir

Dê dois cliques em `TestAiZe.exe`. O aplicativo inicia discretamente, abre o navegador e fica na bandeja do Windows, perto do relógio. Não é necessário instalar Python nem manter uma janela de terminal aberta.

No ícone da bandeja, use **Abrir aplicativo**, **Abrir pasta de dados** ou **Encerrar aplicativo**. Se o aplicativo já estiver aberto, dar dois cliques no `.exe` novamente apenas reabre o navegador.

O servidor aceita conexões somente em `127.0.0.1`; não precisa de internet. No cabeçalho, escolha o modo claro ou escuro e a cor **Neutro**, **Roxo**, **Verde**, **Vermelho** ou **Amarelo**. As duas preferências são lembradas pelo navegador. As cores dos status dos testes continuam fixas para facilitar a leitura dos resultados.

## Usar

Importe `.xlsx` ou CSV UTF-8. O perfil automático reconhece `Nome`, `Precondição`, `Status`, `Prioridade`, `Passo`, `Resultado Esperado`, `Dados do teste` e `Pasta`. Revise o mapeamento na prévia se o arquivo usar outros cabeçalhos.

O status do caso pode ser definido diretamente pelos botões de ícone, independentemente dos passos. **Automático pelos passos** volta a calcular o status. A data e a hora de cada seleção de status aparecem abaixo do passo e no PDF. O comentário fica ao fim do caso. O texto de **Pré-condições da planilha** é somente leitura; escreva no campo **Anotações e evidências** logo abaixo. Nesse campo, em **Resultado observado** e em **Comentário do caso**, selecione, substitua ou apague texto de várias linhas normalmente. Cole imagens com `Ctrl+V`, use Enter para continuar abaixo delas e Backspace para remover uma imagem quando o cursor estiver logo depois. Arraste o canto inferior direito da imagem para ajustar sua largura visual. A posição e a largura aparecem também no PDF; o arquivo original permanece intacto. O botão **Anexar arquivos** do passo aceita qualquer tipo de arquivo, inclusive TXT, XLS, XML, JPG e PNG. Esses arquivos ficam separados das imagens inseridas no texto e podem ser baixados ou removidos; cada passo aceita até 5 arquivos de 5 MB. O download entrega os bytes originais com o nome e a extensão preservados, mas sem abrir o conteúdo na origem da aplicação. O PDF incorpora os arquivos originais e exibe um ícone de anexo no passo; o HTML é autossuficiente e oferece um botão Baixar anexo em cada passo.

Para retestar um caso na mesma sessão e no mesmo ciclo, clique em **Iniciar nova execução deste caso** abaixo do comentário. A execução anterior fica em **Execuções anteriores**, fechada por padrão, com status, passos, horários, anotações e imagens preservados. O caso atual começa sem resultados nem evidências e pode receber uma nova avaliação. A exportação em PDF usa somente a execução atual de cada caso; o histórico continua acessível na sessão.

Ao clicar numa sessão, escolha **Todas as pastas** ou uma pasta específica. As barras mostram a distribuição dos casos por status; passe o mouse sobre uma barra para ver quantidades e percentuais. Caminhos como `/MVP-Gestao-Testes/Acessos-e-Auditoria/MVP-GT` aparecem pelo nome da pasta do ciclo, **Acessos-e-Auditoria**; o caminho completo continua identificado no arquivo da sessão. No player, a lateral agrupa os casos por pasta e permite buscar e selecionar vários ciclos no filtro. A borda de cada caso e passo acompanha seu status. As duas laterais podem ser arrastadas para mudar sua largura ou recolhidas pelos botões no topo. **Modo Kanban**, ao lado do tema, mostra os mesmos casos agrupados por status; abra um cartão para voltar ao Test Player.

Clique em **Exportar Relatório** em qualquer estado da execução, mesmo antes de finalizar. No modal, escolha **PDF** ou **HTML**; todos os casos vêm selecionados e você pode desmarcar casos individuais ou pastas inteiras. Escolha **Somente a última** para exportar a execução atual de cada caso ou **Todas as execuções** para incluir também os retestes anteriores com seus passos e evidências. Antes de gerar, a aplicação salva novamente os dados dos casos selecionados para refletir o status atual. O último PDF fica em `relatorios/relatorio.pdf`; o último HTML fica em `relatorios/relatorio.html`. Ambos usam o modelo com cabeçalho preto, resumo da sessão, distribuição de resultados e seções dos casos. Texto e imagens das pré-condições, dos resultados observados e dos comentários aparecem no ponto correspondente; os arquivos anexados aos passos são listados com nome, extensão e tamanho. O PDF incorpora os arquivos originais, acessíveis em leitores compatíveis, e o HTML inclui arquivos e imagens no mesmo documento e troca o caso exibido quando você seleciona outro caso. Como o HTML incorpora os anexos em Base64, seu tamanho pode crescer cerca de 33% além dos bytes originais, mais imagens e layout.

Se o caso e ao menos um de seus passos estiverem **Reprovados**, aparecem **Gerar relatório da falha** e **Copiar prompt de bug** abaixo dos passos. O PDF de falha contém apenas a execução atual desse caso e fica em `relatorios/falha-caso-...pdf`. O texto copiado vem de `prompt-report-bug.txt` na pasta de dados. Você pode editar esse arquivo em UTF-8; `{{DADOS_DO_CASO}}` é substituído pelos dados, resultados e nomes das evidências da execução atual. Sem esse marcador, os dados do caso são acrescentados ao final do texto. O aplicativo cria um modelo inicial apenas quando o arquivo ainda não existe.

## Onde ficam os dados

Na primeira abertura, o programa cria **Documentos/Executor Local de Testes** (respeitando o local de Documentos configurado no Windows). A pasta mantém o nome antigo para preservar as sessões das versões anteriores. Ali ficam `rascunhos/`, `sessoes/`, `excluidas/`, imagens, PDFs, backups e logs. O próprio `.exe` pode ficar em qualquer pasta e pode ser substituído por uma versão nova sem afetar as sessões. Use **Abrir pasta de dados** na bandeja para chegar ao local exato.

Rascunhos ficam em `rascunhos/`; depois de finalizar, cada execução fica em `sessoes/AAAA-MM-DD/execucao-.../`. A sessão concluída continua editável: você pode ajustar status, anotações, evidências e iniciar retestes nela. É possível exportar PDF ou HTML em qualquer momento, mesmo com casos ou passos ainda não executados. Exportar não finaliza a execução; use **Finalizar execução** quando quiser classificá-la como concluída.

Na lista de sessões, clique em **Excluir** para escolher o destino dos arquivos. **Não, guardar os arquivos** move a pasta completa da sessão para `excluidas/` e a retira da lista. **Sim, excluir também os arquivos** apaga permanentemente a pasta da sessão, incluindo evidências e PDFs. Os backups criados pelo aplicativo incluem também as sessões em `excluidas/`.

Para trazer dados de uma versão anterior, encerre o aplicativo e copie as pastas `rascunhos/` e `sessoes/` da antiga pasta do projeto para **Documentos/Executor Local de Testes**. Ao abrir a nova versão, os bancos antigos recebem as colunas necessárias.

## Segurança dos arquivos

Para guardar uma cópia dos dados, encerre o aplicativo pela bandeja e copie a pasta **Executor Local de Testes** inteira para outro local. Ao restaurar, substitua a pasta de dados com o aplicativo fechado.

Limites desta versão: um operador por vez na mesma máquina; imagens PNG, JPEG ou WebP de até 10 MB e 40 megapixels, até 12 por seção de evidências; arquivos anexados aos passos de até 5 MB cada, 5 por passo. Imagens embutidas na planilha não são importadas.
