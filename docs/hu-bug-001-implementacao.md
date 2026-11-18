# HU-BUG-001 — entrega de implementação

Data: 04/11/2026. Base: `dev` em `9873804ff4fc2352754cab267f8157cccb0e73f2`.

Implementação dos cards DEV-01 a DEV-08 do plano consolidado de Report de Bugs.

| Card | Entrega |
|---|---|
| DEV-01 | Banco global versionado, migração transacional, coordenador reentrante por raiz, journal de intenções e recuperação antes de novas operações. |
| DEV-02 | Autosave de texto separado de status; revisão e geração obrigatórias na ação de status; restrição compartilhada por resultados, sincronização e nova execução; resposta canônica no Player/Mini Player. |
| DEV-03 | Cadastro multipart integral, nome separado, documento único com texto/imagens, edição e evidências próprias com validação de formato, limites, hash, ownership e contenção. |
| DEV-04 | Prévia e vínculo por caso/pasta da sessão atual; recusas individuais de aprovados; vínculo/desvínculo idempotentes; recuperação entre bancos. |
| DEV-05 | Estados do bug, token novo por reteste, prova atual obrigatória e finalização exclusivamente no store global, sem restauração de status. |
| DEV-06 | Move/delete recuperáveis, inclusive exclusão parcial do banco; rerun sem vínculos herdados; backup coordenado com snapshots SQLite e evidências. |
| DEV-07 | Entrada pelo Player e pré-condição, área de bugs por sessão, detalhe, modal acessível por teclado e Kanban global independente. |
| DEV-08 | Relatório próprio com evidências embutidas, snapshot antes de renderizar fora do lock e publicação atômica de PDF validado, independente da sessão. |

## Contratos relevantes

- Finalizar ou desvincular não escreve no status dos casos. O usuário ajusta depois que não houver outro vínculo ativo.
- A restrição permite reprovação, inclusive por passos anteriores ao vínculo. Nova execução preserva o histórico, troca a geração e reaplica bloqueado.
- Autosave legado com tentativa implícita de mudar status salva os textos válidos, preserva o status e responde 409 com orientação de recarga. O cliente atual envia apenas texto nessa rota.
- Conflitos de revisão/geração devolvem 409. Respostas antigas não reaplicam estado obsoleto no navegador. Exportação, reteste e finalização aguardam status pendente.
- Falhas entre recursos deixam uma intenção durável. Uma falha transitória é retomada sob o coordenador; persistência da falha bloqueia operações e informa `operation_id`.
- Provas de outro token não permitem finalizar. Imagem e nota enviadas juntas são preservadas.
- O backup mantém `integridade.json`, snapshots de todos os bancos e arquivos de bugs.

## Validação

- 110 testes Python: `python -m unittest discover -s tests -p 'test_*.py'`.
- 7 testes JavaScript de captura/status: `node --test tests/capture_sync.test.cjs tests/bugs_status.test.cjs`.
- 8 testes do recorder: `npm --prefix src/playwright-recorder test`.
- Casos de bugs incluem migração repetida e rollback, propriedade de imagens, traversal, lote misto, autosave legado, geração/revisão, dois bugs por caso, prova atual, concorrência, recuperação de vínculo e exclusão parcial, move após rename, rerun, sincronização e restauração de backup concorrente com upload.
- Navegador: criar com imagem colada fora do Player → salvar/reabrir → selecionar pasta no vínculo → aprovado desabilitado → iniciar reteste → recusar finalização sem prova → salvar prova → finalizar → vínculos inativos e status preservado → ajustar status manualmente no Player.
- PDF real de bug após apagar a sessão de origem e remover todos os vínculos: campos, ordem, largura proporcional das imagens e prova com imagem/nota conferidos na extração e nas duas páginas renderizadas. Evidência corrompida produz erro explícito.
- Build: `python scripts/build_executable.py`; smoke: `python scripts/smoke_executable.py dist/TestAiZe-01.005.000.exe`. O smoke verifica servidor, Kanban de bugs, assets, store global e inicialização do host Qt.
- Revisão independente com `dan-delivery-review`: **SEM ACHADOS BLOQUEANTES**, após correções dos achados. O revisor inspecionou código/testes; a execução das validações foi responsabilidade do implementador.

O ambiente local exige executar testes com sockets/navegador fora do sandbox e direcionar temporários a uma pasta gravável. Isso não altera as permissões da aplicação.

## Empacotamento

O script prioriza `SystemRoot/System32` no PATH durante a análise do PyInstaller. Foi reproduzida uma falha de QtCore causada pela inclusão da `icuuc.dll` de um Poppler disponível no PATH de desenvolvimento, sem os símbolos exigidos pelo Qt. A prioridade das bibliotecas do Windows elimina essa dependência incompatível. O smoke confirmou a inicialização do host Qt após a correção.

Os novos templates e assets entram pelo empacotamento por diretório já existente. Não há dependência nova de serviço externo ou tela de restauração.
