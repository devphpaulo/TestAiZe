# TestAiZe

![GitHub repo size](https://img.shields.io/github/repo-size/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub last commit](https://img.shields.io/github/last-commit/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub license](https://img.shields.io/github/license/devphpaulo/TestAiZe?style=for-the-badge)

<p align="center">
  <img src="src/testplayer/static/favicon.svg" alt="Logo TestAiZe" width="128">
</p>

TestAiZe é uma cópia do Zephyr Scale que roda inteira no seu computador — 100% local e gratuita. Sem Jira, sem nuvem, sem mensalidade: você importa a planilha de casos, executa os testes passo a passo com evidências e sai com um relatório em PDF ou HTML pronto para enviar. Tudo offline — os dados nunca saem da sua máquina.

## Por que usar

- **Fluxo que você já conhece** — os mesmos conceitos do Zephyr Scale: casos, passos, status, evidências, ciclos e pastas. Sem precisar de conta Atlassian.
- **Execução local** — use `executar.bat` no código-fonte ou abra o `.exe` gerado pelo GitHub Actions. O app abre no navegador, quieto na bandeja do Windows.
- **Privacidade total** — roda 100% offline; planilhas, evidências e relatórios ficam nos seus Documentos.
- **Relatórios prontos** — PDF e HTML com resumo, distribuição de resultados e evidências. O HTML permite baixar os arquivos anexados; o PDF lista esses arquivos sem incorporá-los. Caso reprovado? Um clique gera o PDF da falha e copia o prompt de bug.
- **Reteste sem retrabalho** — reexecute um caso sem perder as execuções anteriores, filtre por pasta ou enxergue tudo no modo Kanban.

## Requisitos

- **Executável:** Windows 10/11 com Edge ou Chrome para a geração de PDF.
- **Código-fonte:** Python 3.12+ com `pip`.

## Instalação

Baixe o executável versionado gerado pelo workflow **Build exe** na aba [Actions](https://github.com/devphpaulo/TestAiZe/actions). Node e Playwright não são incluídos no executável: Automação usa as ferramentas instaladas no computador.

Ou rode a partir do código-fonte:

```
git clone https://github.com/devphpaulo/TestAiZe.git
cd TestAiZe
pip install -r requirements.txt
```

## Uso

```
executar.bat               # ou: python src/launcher.py
```

Importar planilha → executar casos no Test Player → exportar relatório. O aplicativo salva sessões, evidências, relatórios e logs em **Documentos/TestAiZe**. O passo a passo completo está no [manual de uso](docs/manual.md).

> Por enquanto os casos de teste entram somente via planilha. A criação e edição manual de casos dentro do app está em idealização para uma versão futura.

## Automação com Playwright

A aba **Automação** abre uma biblioteca de pastas, ciclos e scripts, separada das sessões manuais. Use **Gravar teste avulso** para informar uma URL e gravar com Chromium. **Salvar .spec.ts** baixa o teste; **Salvar na biblioteca** organiza o arquivo em uma pasta e ciclo. Os scripts podem ser reabertos e editados.

**Rodar suíte** executa os scripts da pasta ou ciclo selecionado e mostra total, aprovados, reprovados, ignorados e o motivo das falhas. Cada execução mantém um histórico com cópia dos scripts usados.

O BAT inicia o aplicativo sem build local. A cada abertura, o TestAíZé verifica Node.js 20+, Playwright Codegen 1.62.1 e Chromium no ambiente. Quando indisponíveis, informa o motivo e oculta a aba Automação; o executor manual continua disponível.

Se quiser habilitar Automação, prepare as ferramentas no ambiente, separadamente:

```powershell
npm install --global @playwright/test@1.62.1
playwright install chromium
executar.bat
```

Não há instalação automática dessas ferramentas. Sair ou recarregar descarta apenas a gravação não salva; a biblioteca permanece no diretório de dados. O **Cofre** permite cadastrar chaves e marcar valores como Secret. E-mail e senha gravados usam `process.env.PLAYWRIGHT_EMAIL` e `process.env.PLAYWRIGHT_PASSWORD`, tanto nas etapas avulsas quanto nas suítes. Os valores do Cofre duram somente enquanto o aplicativo estiver aberto.

Veja [operação e build da automação](docs/automacao.md) e [testes do recorder](src/playwright-recorder/README.md).

## Planilha de casos

O app importa `.xlsx` ou CSV UTF-8 no layout do Zephyr Scale: 8 colunas fixas (`Nome`, `Precondição`, `Status`, `Prioridade`, `Passo`, `Resultado Esperado`, `Dados do teste`, `Pasta`), uma linha por passo, com os dados do caso preenchidos só na primeira linha. O guia completo — colunas, formato das linhas, nomenclatura por trilha e formatação — está em [docs/planilha.md](docs/planilha.md).

## Contribuição

Contribuições são muito bem-vindas — em código ou em issues com sugestões de melhoria. Abra issues com intenção clara, objetivo e valor real, sem fugir da ideia principal do projeto: ser uma ferramenta 100% local. Para contribuir com código: faça um fork, crie um branch, commite e abra o PR.

## Autor

**Paulo Henrique** — [@devphpaulo](https://github.com/devphpaulo)

## Licença

MIT — veja [LICENSE](LICENSE).
