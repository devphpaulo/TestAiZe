# Validação da reformulação — 5 de outubro de 2026

Ambiente local: Windows 11, Python 3.14.0, Node.js 22.20.0 e Playwright 1.62.1 instalado no prefixo npm do usuário.

O recorder anterior foi substituído por código JavaScript em `src/playwright-recorder`. Os artefatos locais de PyInstaller, o executável, `dist`, `build` e a pasta antiga do recorder na raiz foram removidos. O `.gitignore` previamente alterado pelo usuário foi preservado.

## Evidência

- Regressão Python: 51 testes aprovados, incluindo persistência de pastas/ciclos/scripts, CRUD, downloads sem locks no Windows, snapshots, suítes reais, falhas com segredo redigido, cancelamento do runner, recuperação de execução interrompida, biblioteca/histórico incluídos no backup e verificação dos arquivos necessários ao runner. A regressão manual existente continua passando.
- Testes Node: 10 testes aprovados com o Playwright do ambiente, sem instalação ou compilação local. Incluem e-mail por tipo/identificador/label/nome, senha, texto normal preservado e canários ausentes de todas as atualizações de código capturadas.
- E2E do recorder: 3 testes aprovados; HTTP/WS, hover, select, teclado, paste, codegen, limpeza, execução e cleanup.
- Integração Flask/Node/Chromium: 3 testes aprovados. Incluem entrada pela biblioteca sem spawn, gravação avulsa, download .spec.ts, criação de pasta/ciclo ao salvar, reabertura e edição do arquivo, duas suítes reais e histórico com aprovado/reprovado e motivo da falha. A senha recém-digitada permanece mascarada com confirmação por chave, e a consulta nunca retorna o segredo. Também foram verificados o cenário sem Node e o player manual escuro, com cinco cores distintas na marca e busca sem transbordamento em três larguras de sidebar.
- Capturas desktop e mobile em `src/playwright-recorder/test-results`, ignoradas pelo Git, foram inspecionadas. A interface usa as folhas Carbon do aplicativo e editor com abas.

O workflow foi reformulado para gerar `.exe` somente no GitHub Actions e testar com ferramentas instaladas no runner. Não foi disparado um job remoto nem gerado um novo executável localmente nesta reformulação.

O Cofre fica em memória enquanto o aplicativo estiver aberto, conforme a preferência confirmada pelo usuário. A versão Playwright 1.62.1 continua obrigatória por causa da API privada do recorder. Outras versões não foram declaradas compatíveis.

O erro de execução sem relatório foi reproduzido com `run-suite.cjs` ausente. O inicializador foi restaurado, e o start agora valida inicializador, hook de runtime e reporter antes de criar a execução. As suítes reais e o fluxo completo pelo navegador passaram após a restauração.
