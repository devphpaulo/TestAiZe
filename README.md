# TestAiZe

![GitHub repo size](https://img.shields.io/github/repo-size/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub last commit](https://img.shields.io/github/last-commit/devphpaulo/TestAiZe?style=for-the-badge)

Executor local de testes manuais para Windows. Importa planilhas de casos (`.xlsx` / CSV), permite executar passo a passo com status, anotações e evidências, e exporta relatórios em PDF ou HTML. Roda 100% offline em `127.0.0.1`, com ícone na bandeja — usando o `.exe`, não precisa instalar Python.

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

O navegador abre e o app fica na bandeja do Windows. Fluxo básico: importar planilha → executar casos no Test Player → exportar relatório (PDF/HTML). O passo a passo completo está no [manual de uso](docs/manual.md).

## Contribuição

Issues e pull requests são bem-vindos: faça um fork, crie um branch, commite e abra o PR.

## Autor

**Paulo Henrique** — [@devphpaulo](https://github.com/devphpaulo)
