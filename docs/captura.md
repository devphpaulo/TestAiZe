# Captura de tela do TestAíZé

## Capturar e anexar uma evidência

1. Abra o TestAíZé e selecione o caso e o passo no Test Player. Aguarde o resultado observado ser salvo.
2. Deixe a aplicação que deseja capturar na frente e pressione **PrintScreen** ou o atalho configurado.
3. Arraste para selecionar a região. As dimensões e as alças ajudam a ajustar o recorte; as ferramentas aparecem depois da seleção.
4. Escolha um ícone: seleção, desenho livre, linha, seta, retângulo, círculo ou texto. Passe o mouse sobre ele para ver seu nome. O botão destacado indica a ferramenta selecionada.
5. Escolha a cor nos quadradinhos. **Desfazer**, ou **Ctrl+Z** fora do campo de texto, remove a última anotação. Na ferramenta Texto, clique na imagem e digite ali mesmo. **Enter** conclui; **Shift+Enter** cria outra linha. Escolher outra ferramenta também conclui a anotação. As barras continuam visíveis durante o desenho.
6. Confira o caso, o passo destacado e o destino escrito no botão **Anexar**. Se necessário, selecione outro passo no painel.
7. Clique em **Anexar** e espere a confirmação indicando qual passo recebeu a imagem. Ela aparece no resultado observado e permanece disponível na sessão e nos relatórios.

**Resultado observado** é o texto do passo. A ferramenta **Texto** desenha palavras dentro da imagem. São conteúdos separados. Anotar, trocar a cor e navegar pelos passos não anexam uma imagem automaticamente.

## Copiar, salvar e cancelar

- **Copiar**, ou **Ctrl+C**, coloca a imagem final no clipboard e fecha a captura. Não anexa ao teste. No campo Resultado observado, Ctrl+C mantém o comportamento normal de copiar texto.
- **Salvar** grava um PNG no local escolhido. Não anexa ao teste.
- **Cancelar**, **Esc** ou botão direito fecha a captura imediatamente, sem confirmação, inclusive durante desenho ou digitação. Texto observado que já foi salvo continua no passo; conteúdo ainda não sincronizado é descartado ao sair.

Copiar, salvar e anexar usam o mesmo renderizador: a saída contém o recorte e as anotações, sem barras, alças, dimensões ou painel do editor. Continuar desenhando depois de anexar não modifica a evidência que já foi confirmada. Um novo clique em Anexar é outra ação explícita e pode criar outra evidência.

O editor permanece aberto depois de salvar ou anexar. Copiar fecha; para outra captura, pressione o atalho novamente e selecione outra área. As ferramentas reaparecem em cada nova seleção, mesmo depois de copiar e reabrir várias vezes; a cor escolhida é mantida. O rascunho da imagem fica em memória e não é recuperado ao encerrar o aplicativo.

Setas, linhas, retângulos, círculos e traços livres usam bordas suavizadas. Linhas têm pontas e junções arredondadas; retângulos têm um arredondamento discreto nos cantos. A prévia e a imagem exportada usam o mesmo desenho, mantendo os pixels da captura original sem redimensionamento.

## Alterar o atalho

No ícone do TestAíZé ao lado do relógio do Windows, clique com o botão direito e escolha **Atalho da captura**. Pressione a nova combinação e clique em **Salvar atalho**. **Esc** cancela a alteração. Um atalho ocupado por outro programa é recusado. A escolha fica em `config/atalho-captura.json`, na pasta de dados.

Se o Windows abrir sua ferramenta de recorte ao pressionar PrintScreen, escolha outra combinação no TestAíZé. A aplicação não toma à força o atalho de outro programa.

## Destino, conflitos e limites

Confira sempre o destino antes de anexar. Depois de um reteste, selecione explicitamente um passo da execução atual. Uma captura associada à geração anterior não deve ser gravada silenciosamente na nova execução.

Se aparecer conflito de resultado observado, copie o texto local para um lugar seguro antes de recarregar ou descartar a edição. Compare-o com o texto salvo no Player. A proteção de revisão impede sobrescrever silenciosamente outra edição; ainda não há uma tela de mesclagem de conflitos.

Uma anexação recusada mantém o recorte disponível para copiar ou salvar. O limite continua sendo **12 imagens por passo**, **10 MiB por imagem** e **40 milhões de pixels**. A captura é anexada em PNG.

Sem caso aberto, é possível capturar, desenhar, copiar e salvar; Anexar precisa de um destino válido. A captura manual funciona sem Node, Playwright, conta ou internet. Para usar a automação de testes do produto, consulte [automação](automacao.md).

## Pasta de dados e limites conhecidos

Use **Abrir pasta de dados** na bandeja para localizar as sessões. O caminho padrão pode estar dentro do OneDrive, conforme a configuração do Windows. Para iniciar com outra pasta local, use `TestAiZe-VERSAO.exe --data-dir "D:\TestAiZe-Dados"`. Essa opção escolhe o local de novas sessões; não move dados existentes.

A captura atual fecha o Mini Player em PiP antes de obter a imagem e não o reabre automaticamente. Reabra-o no Player quando terminar. Para uso previsível, mantenha uma aba do Player vinculada à tarefa. A coordenação de várias abas, a restauração do PiP e a experiência durante falhas lentas do serviço local ainda precisam de melhorias descritas na [revisão técnica](captura-revisao-2026-10-31.md).
