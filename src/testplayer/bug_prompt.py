from __future__ import annotations

from pathlib import Path


PROMPT_FILENAME = "prompt-report-bug.txt"
DEFAULT_PROMPT = """Crie um relatório de incidente a partir dos dados abaixo. Use este formato:

Título: (BUG [área]) - [resumo do problema]
Relatório de Incidente
Sistema: [preencher]

Informações complementares:
- Usuário logado: [preencher]
- Versão do sistema utilizada: [preencher]
- Banco de dados utilizado: [preencher]
- Versão do banco de dados: [preencher]
- Aplicação remota ou via servidor? [preencher]
- Servidor de hospedagem: [preencher]
- Funcionalidade utilizada: [preencher]
- Caminho no sistema: [preencher]
- Nível de acesso do usuário utilizado no teste: [preencher]

Descrição do Incidente:
[Descreva o erro sem inventar informações.]

Pré-condições de reprodução:
[Liste as pré-condições do caso.]

Passo a passo de reprodução do erro:
[Liste os passos executados.]

Resultado obtido (com erro):
[Use o resultado observado e as evidências.]

Resultado esperado:
[Use o resultado esperado do caso.]

Evidências:
[Liste imagens, URLs, payloads, logs e demais dados fornecidos.]

Se algum dado não estiver disponível, mantenha [preencher] e não suponha valores.

Dados da execução atual:
{{DADOS_DO_CASO}}
"""


def failed_case(case: dict) -> bool:
    return case["status"] == "reprovado" and any(step["status"] == "reprovado" for step in case["steps"])


def _blocks(blocks: list[dict]) -> str:
    items = []
    for block in blocks:
        if block["type"] == "text" and block.get("text", "").strip():
            items.append(block["text"].strip())
        elif block["type"] == "image":
            items.append(f"[Imagem: {block['item']['original_name']}]")
    return "\n".join(items)


def build_prompt(root: Path, case: dict) -> str:
    source = (root / PROMPT_FILENAME).read_text(encoding="utf-8")
    lines = [f"Caso: {case['name']}", f"Pasta: {case['folder'] or 'Sem pasta'}",
             f"Prioridade: {case['priority'] or 'Não informada'}",
             f"Pré-condições da planilha: {case['precondition'] or 'Não informadas'}"]
    notes = _blocks(case["precondition_notes_blocks"])
    if notes:
        lines.append(f"Anotações nas pré-condições:\n{notes}")
    for step in case["steps"]:
        lines.extend([f"Passo {step['position']} [{step['status']}]: {step['action']}",
                      f"Dados de teste: {step['test_data']}", f"Resultado esperado: {step['expected']}",
                      f"Resultado observado: {_blocks(step['actual_blocks']) or 'Não informado'}"])
        if step.get("attachments"):
            lines.append("Arquivos anexados: " + ", ".join(item["original_name"] for item in step["attachments"]))
    comment = _blocks(case["comment_blocks"])
    if comment:
        lines.append(f"Comentário do caso:\n{comment}")
    context = "\n".join(lines)
    return source.replace("{{DADOS_DO_CASO}}", context) if "{{DADOS_DO_CASO}}" in source else source + "\n\n" + context
