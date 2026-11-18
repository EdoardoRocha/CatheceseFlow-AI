from langchain_core.tools import tool

_FAQ_ENTRIES: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("turma", "turmas", "criar turma", "horario", "dia"),
        "Turmas",
        (
            "Na tela 'Turmas' (/dashboard), clique em '+ Nova turma' para cadastrar o sacramento "
            "(Primeira Comunhão, Perseverança ou Crisma), local, dia da semana e horários de início/término. "
            "Clique em qualquer turma para acessar seus catequizandos e formações."
        ),
    ),
    (
        ("chamada", "presenca", "presença", "falta", "faltas", "formacao", "formação", "aula"),
        "Formações e Chamada",
        (
            "Dentro de uma turma, cadastre um encontro na seção de formações e clique em 'Fazer chamada'. "
            "Na tela da chamada você marca presença ou registra falta com justificativa para cada catequizando."
        ),
    ),
    (
        ("resumo", "pdf", "transcricao", "transcrição", "ia", "download"),
        "Resumos com IA e PDF",
        (
            "Ao lado do botão 'Fazer chamada' existe o botão 'Gerar resumo'. "
            "Você pode enviar um arquivo .txt ou digitar/colar a transcrição da formação; "
            "a IA gera o resumo estruturado no MongoDB e libera o botão 'Baixar PDF'."
        ),
    ),
    (
        ("aluno", "alunos", "catequizando", "matricular", "excluir", "cpf", "batismo", "comunhao"),
        "Catequizandos (Alunos)",
        (
            "Dentro da turma você pode cadastrar novos alunos (o sistema evita duplicidade por nome ou CPF), "
            "editar telefones, endereço, sacramentos (Batismo e Primeira Comunhão), vincular o catequista "
            "responsável ou excluir o cadastro com confirmação em cascata."
        ),
    ),
    (
        ("painel", "estatistica", "relatorio", "dashboard", "indicador"),
        "Painel Geral",
        (
            "A aba 'Painel' (/painel) exibe os indicadores consolidados de turmas, alunos e frequência "
            "da sua paróquia."
        ),
    ),
]


@tool
def get_platform_faq(topic: str) -> str:
    """Responde dúvidas operacionais sobre como usar funcionalidades do CatheceseFlow (turmas, chamadas, resumos em PDF, alunos e painel)."""
    normalized = topic.strip().lower()
    matches: list[str] = []

    for keywords, title, answer in _FAQ_ENTRIES:
        if any(kw in normalized for kw in keywords):
            matches.append(f"[{title}] {answer}")

    if not matches:
        all_topics = "\n".join(f"- {title}: {answer}" for _, title, answer in _FAQ_ENTRIES)
        return f"Guia geral do CatheceseFlow:\n{all_topics}"

    return "\n\n".join(matches)
