# TestAiZe

![GitHub repo size](https://img.shields.io/github/repo-size/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub language count](https://img.shields.io/github/languages/count/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub forks](https://img.shields.io/github/forks/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub issues](https://img.shields.io/github/issues/devphpaulo/TestAiZe?style=for-the-badge)
![GitHub pull requests](https://img.shields.io/github/issues-pr/devphpaulo/TestAiZe?style=for-the-badge)

<p align="center">
  <img src="testplayer/static/favicon.svg" alt="Logo TestAiZe" width="128">
</p>

> Executor local de testes manuais para Windows: importe planilhas de casos (`.xlsx` / CSV), execute passo a passo com status, anotações e evidências e exporte relatórios PDF ou HTML.
> Roda 100% offline em `127.0.0.1`, com ícone na bandeja — usando o `.exe`, não é preciso instalar Python.

### Ajustes e melhorias

O projeto continua em evolução; as próximas atualizações miram os limites atuais da versão:

- [ ] Importar imagens embutidas na planilha
- [ ] Mais de um operador simultâneo na mesma máquina

## ❓ Pré-requisitos

Antes de começar, verifique se você atende ao que precisa para o seu caso:

- **Usando o `.exe` (recomendado):** uma máquina Windows 10/11 — nada de Python.
- **Rodando do código-fonte:** Python 3.12+ com `pip`, para instalar as dependências de `requirements.txt`.
- Os dados do aplicativo ficam em **Documentos/Executor Local de Testes**, criados na primeira abertura.

## ⚙ Instalando o TestAiZe

**Pelo executável (GitHub Actions):**

1. Abra a aba [Actions](https://github.com/devphpaulo/TestAiZe/actions) e execute o workflow **Build exe**;
2. Ao final, baixe o artefato `TestAiZe-windows`;
3. Descompacte em qualquer pasta.

**Pelo código-fonte:**

```
git clone https://github.com/devphpaulo/TestAiZe.git
cd TestAiZe
pip install -r requirements.txt
```

Para gerar o seu próprio `.exe` localmente (opcional):

```
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name TestAiZe --add-data "testplayer/templates;testplayer/templates" --add-data "testplayer/static;testplayer/static" launcher.py
```

O resultado fica em `dist\TestAiZe\TestAiZe.exe`.

## 💻 Usando o TestAiZe

Dê dois cliques em `TestAiZe.exe` (ou `python launcher.py`, no código-fonte). O navegador abre e o aplicativo fica na bandeja do Windows. O fluxo básico:

```
Importar planilha (.xlsx / CSV)  →  Executar casos no Test Player  →  Exportar relatório (PDF / HTML)
```

Evidências com `Ctrl+V`, anexos nos passos, retestes, modo Kanban e prompt de bug para reprovados. O passo a passo completo está no **[manual de uso](docs/manual.md)**.

## 📄 Documentação

- [Manual de uso](docs/manual.md) — abertura, execução, evidências, relatórios, dados e backup
- [Workflow de build](.github/workflows/build.yml) — geração do executável com PyInstaller

## 🤝 Contribuindo para o TestAiZe

Para contribuir, siga estas etapas:

1. Bifurque este repositório.
2. Crie um branch: `git checkout -b <nome_branch>`.
3. Faça suas alterações e confirme-as: `git commit -m '<mensagem_commit>'`.
4. Envie para o seu fork: `git push origin <nome_branch>`.
5. Crie a solicitação de pull.

Como alternativa, consulte a documentação do GitHub em [como criar uma solicitação pull](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request).

## 😏 Colaboradores

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/devphpaulo" title="devphpaulo">
        <img src="https://avatars.githubusercontent.com/devphpaulo" width="100px;" alt="Foto do Paulo Henrique no GitHub"/><br>
        <sub>
          <b>Paulo Henrique</b>
        </sub>
      </a>
    </td>
  </tr>
</table>
