# Planilha de casos de teste

Guia de como montar a planilha que o TestAiZe importa (`.xlsx` ou CSV UTF-8), no mesmo layout usado pelo Zephyr Scale.

## Colunas

Colunas fixas, nesta ordem exata (linha 1 = cabeçalho):

| Col | Cabeçalho | Regra de preenchimento |
|-----|-----------|------------------------|
| A | Nome | Título do caso. Preenchido **somente na 1ª linha do caso**. |
| B | Precondição | Multilinha ("- item" por linha). Somente na 1ª linha do caso. |
| C | Status | `Rascunho` ou `Não Executado`. Somente na 1ª linha do caso. |
| D | Prioridade | `Alta`, `Normal` ou `Média`. Somente na 1ª linha do caso. |
| E | Passo | Uma ação por linha (uma linha por passo). |
| F | Resultado Esperado | Somente em passos de validação relevante. |
| G | Dados do teste | Caminho de navegação ou dados de entrada, quando houver. |
| H | Pasta | Caminho `/Produto/.../Card`. Somente na 1ª linha do caso. |

## Formato das linhas (long-format)

- Cada caso ocupa N linhas, uma por passo.
- Na 1ª linha do caso: preencher A, B, C, D, H (além de E/F/G do primeiro passo).
- Nas linhas seguintes: preencher apenas E (Passo) e, quando aplicável, F e G.
- **Não repetir** Nome/Precondição/Status/Prioridade/Pasta nas linhas de passo.

## Nomenclatura e passos padrão

Prefixo de trilha no **Nome** do caso: `Tela -`, `API -`, `WebService -` ou `Batch -`.

Passos iniciais por trilha:

- **Tela:** 1) Realizar login na aplicação · 2) Navegar até [tela] (caminho em Dados do teste)
- **API:** 1) Realizar login e salvar token · 2) Localizar endpoint de [operação]
- **WebService:** 1) Obter token/credencial do serviço · 2) Localizar a operação [nome]
- **Batch:** 1) Preparar massa/parâmetros · 2) Executar processamento · 3) Validar arquivo/registro · 4) Consultar log

## Regras de conteúdo

- Resultado Esperado somente em passos com validação; múltiplos resultados em passos distintos.
- Caminhos de navegação com separador `>` e sem abreviar (ex.: `Configurações > Parâmetros Gerais`).
- Massa de teste explícita nas precondições quando houver regra por status.
- Somente cenários funcionais; nenhum detalhe técnico de desenvolvimento.

## Formatação (para ficar igual ao modelo)

- Cabeçalho: fonte Calibri 14, negrito, preenchimento amarelo (`FFFF00`).
- Corpo: fonte Aptos Narrow 11, quebra de texto ativa, alinhamento vertical central.
- Larguras das colunas: A=58 · B=53 · C=10 · D=13 · E=123 · F=80 · G=22 · H=29.
- Uma aba por agrupamento (card/funcionalidade) quando fizer sentido; ou aba única para um conjunto coeso.

## Exemplo

| Nome | Precondição | Status | Prioridade | Passo | Resultado Esperado | Dados do teste | Pasta |
|------|-------------|--------|------------|-------|--------------------|----------------|-------|
| Tela - Login com credenciais válidas | - Usuário cadastrado e ativo | Não Executado | Alta | Acessar a tela de login | | URL da aplicação | /Produto/Autenticação/Login |
| | | | | Informar usuário e senha válidos | | usuário: qa.teste; senha: •••••• | |
| | | | | Acionar o botão Entrar | | | |
| | | | | Validar o acesso à aplicação | Usuário é autenticado e redirecionado para a tela inicial | | |
| Tela - Login com senha incorreta | - Usuário cadastrado e ativo | Não Executado | Alta | Acessar a tela de login | | URL da aplicação | /Produto/Autenticação/Login |
| | | | | Informar usuário válido e senha incorreta | | usuário: qa.teste; senha: "senhaerrada123" | |
| | | | | Acionar o botão Entrar | | | |
| | | | | Validar a mensagem exibida | Sistema exibe mensagem de credenciais inválidas e não autentica o usuário | | |
