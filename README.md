# TestAiZe

![GitHub repo size](https://img.shields.io/github/repo-size/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub last commit](https://img.shields.io/github/last-commit/devphpaulo/TestAiZe?style=for-the-badge)

<p align="center">
  <img src="testplayer/static/favicon.svg" alt="Logo TestAiZe" width="128">
</p>

TestAiZe é uma cópia do Zephyr Scale que roda inteira no seu computador — 100% local e gratuita. Sem Jira, sem nuvem, sem mensalidade: você importa a planilha de casos, executa os testes passo a passo com evidências e sai com um relatório em PDF ou HTML pronto para enviar. Tudo offline — os dados nunca saem da sua máquina.

## Por que usar

- **Fluxo que você já conhece** — os mesmos conceitos do Zephyr Scale: casos, passos, status, evidências, ciclos e pastas. Sem precisar de conta Atlassian.
- **Zero instalação** — um único `.exe`. Dois cliques e o app abre no navegador, quieto na bandeja do Windows.
- **Privacidade total** — roda 100% offline; planilhas, evidências e relatórios ficam nos seus Documentos.
- **Relatórios prontos** — PDF e HTML com resumo, distribuição de resultados e evidências. Caso reprovado? Um clique gera o PDF da falha e copia o prompt de bug.
- **Reteste sem retrabalho** — reexecute um caso sem perder as execuções anteriores, filtre por pasta ou enxergue tudo no modo Kanban.

## Requisitos

- **Executável:** Windows 10/11, nada mais.
- **Código-fonte:** Python 3.12+ com `pip`.

## Instalação

Baixe o artefato `TestAiZe-windows` gerado pelo workflow **Build exe** na aba [Actions](https://github.com/devphpaulo/TestAiZe/actions) e descompacte em qualquer pasta.

Ou rode a partir do código-fonte:

```
git clone https://github.com/devphpaulo/TestAiZe.git
cd TestAiZe
pip install -r requirements.txt
```

## Uso

```
TestAiZe.exe        # ou: python launcher.py
```

Importar planilha → executar casos no Test Player → exportar relatório. O passo a passo completo está no [manual de uso](docs/manual.md).

> Por enquanto os casos de teste entram somente via planilha. A criação e edição manual de casos dentro do app está em idealização para uma versão futura.

## Planilha de casos

O app importa `.xlsx` ou CSV UTF-8 no layout do Zephyr Scale: 8 colunas fixas (`Nome`, `Precondição`, `Status`, `Prioridade`, `Passo`, `Resultado Esperado`, `Dados do teste`, `Pasta`), uma linha por passo, com os dados do caso preenchidos só na primeira linha. O guia completo — colunas, formato das linhas, nomenclatura por trilha e formatação — está em [docs/planilha.md](docs/planilha.md).

## Contribuição

Contribuições são muito bem-vindas — em código ou em issues com sugestões de melhoria. Abra issues com intenção clara, objetivo e valor real, sem fugir da ideia principal do projeto: ser uma ferramenta 100% local. Para contribuir com código: faça um fork, crie um branch, commite e abra o PR.

## Autor

**Paulo Henrique** — [@devphpaulo](https://github.com/devphpaulo)
