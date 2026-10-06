# Worker de automação do TestAíZé

JavaScript executado diretamente por Node, sem build intermediário. Node.js 20+ e Playwright Codegen 1.62.1 com Chromium devem estar instalados no ambiente. O resolver não instala ferramentas; o host Python detecta a disponibilidade na abertura.

Na raiz do projeto, use `executar.bat`. Para o worker isolado: `node src/playwright-recorder/server.js`. A porta standalone padrão é 4173; no host a porta é efêmera e a UI usa modo embedded.

## Validação

```powershell
npm --prefix src/playwright-recorder test
npm --prefix src/playwright-recorder run test:e2e
npm --prefix src/playwright-recorder run test:host
```

Os testes usam o Playwright do ambiente. `TESTAIZE_PYTHON` pode indicar o Python do host; por padrão é `.venv/Scripts/python.exe`. `TESTAIZE_SCREENSHOT` habilita capturas da interface e do Cofre. `TESTAIZE_EXE` é usado pelo smoke do executável no GitHub Actions.

O adapter mantém a API privada do recorder isolada. E-mail e senha viram referências a `process.env` antes de qualquer atualização de código. Etapas editáveis usam os valores atuais enviados pelo Cofre do host através de stdin.

`RECORDER_PORT`, `RECORDER_PARENT_ORIGIN`, `RECORDER_PLAYWRIGHT_MODULE`, `RECORDER_MANAGED` e `RECORDER_PARENT_PID` são configurações internas do host. A readiness é `PLAYWRIGHT_RECORDER_READY http://127.0.0.1:<porta>`. HTTP/WS aceitam somente loopback e a origem correspondente; CSP permite somente o pai configurado.

`shutdown` ou EOF na pipe de controle encerram o worker. A biblioteca `ws` vendorizada preserva a licença MIT. Consulte [operação e Cofre](../../docs/automacao.md) para os limites e a distribuição.
