from fpdf import FPDF


def safe_latin1(text: str) -> str:
    """Normaliza caracteres tipográficos fora de Latin-1 para fontes padrão do FPDF."""
    replacements = {
        "—": "-",
        "–": "-",
        "•": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
    }
    normalized = str(text or "")
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    return normalized.encode("latin-1", errors="replace").decode("latin-1")


class _SummaryPDF(FPDF):
    header_subtitle = "CatheceseFlow - Resumo de Formacao"

    def header(self) -> None:
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(90, 90, 90)
        self.cell(0, 8, safe_latin1(self.header_subtitle), align="R")
        self.ln(10)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, safe_latin1(f"Pagina {self.page_no()}"), align="C")


class _FormationPDF(_SummaryPDF):
    header_subtitle = "CatheceseFlow - Roteiro de Formacao"


def _write_section_title(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 8, safe_latin1(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(203, 213, 225)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)


def _write_paragraph(pdf: FPDF, text: str) -> None:
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(51, 65, 85)
    pdf.multi_cell(0, 6, safe_latin1(text))
    pdf.ln(4)


def _write_bullets(pdf: FPDF, items: list[str]) -> None:
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(51, 65, 85)
    for item in items:
        pdf.multi_cell(0, 6, safe_latin1(f"- {item}"))
        pdf.ln(1)
    pdf.ln(3)


def build_summary_pdf(doc: dict) -> bytes:
    """Constrói o PDF formatado a partir do documento salvo no MongoDB."""
    summary = doc.get("summary") or {}
    pdf = _SummaryPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    title = summary.get("title") or doc.get("theme") or "Resumo da Formacao"
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(0, 9, safe_latin1(title))
    pdf.ln(3)

    # Bloco de metadados do encontro
    pdf.set_fill_color(248, 250, 252)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(71, 85, 105)
    catequistas = ", ".join(doc.get("catequistas") or []) or "Nao informado"
    meta_lines = [
        f"Tema: {doc.get('theme', '-')}",
        f"Data: {doc.get('date', '-')}",
        f"Local: {doc.get('location') or 'Nao informado'}",
        f"Catequistas: {catequistas}",
    ]
    for line in meta_lines:
        pdf.cell(0, 6, safe_latin1(line), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(6)

    if summary.get("objective"):
        _write_section_title(pdf, "Objetivo do Encontro")
        _write_paragraph(pdf, summary["objective"])

    if summary.get("full_summary"):
        _write_section_title(pdf, "Resumo da Formacao")
        _write_paragraph(pdf, summary["full_summary"])

    key_points = summary.get("key_points") or []
    if key_points:
        _write_section_title(pdf, "Pontos-Chave")
        _write_bullets(pdf, key_points)

    refs = summary.get("biblical_references") or []
    if refs:
        _write_section_title(pdf, "Referencias Biblicas e Catequeticas")
        _write_bullets(pdf, refs)

    if summary.get("practical_application"):
        _write_section_title(pdf, "Aplicacao Pratica")
        _write_paragraph(pdf, summary["practical_application"])

    output = pdf.output()
    return bytes(output)


def build_formation_plan_pdf(doc: dict) -> bytes:
    """Constrói o PDF formatado de um roteiro completo de formação gerado pela Marta."""
    pdf = _FormationPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    title = doc.get("title") or doc.get("theme") or "Roteiro de Formacao"
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(0, 9, safe_latin1(title))
    pdf.ln(3)

    pdf.set_fill_color(248, 250, 252)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(71, 85, 105)
    duration = doc.get("duration_minutes")
    duration_text = f"{duration} minutos" if duration else "A definir"
    meta_lines = [
        f"Tema: {doc.get('theme', '-')}",
        f"Publico / Etapa: {doc.get('target_audience') or 'Catequizandos'}",
        f"Duracao Estimada: {duration_text}",
    ]
    if doc.get("created_by"):
        meta_lines.append(f"Elaborado para: {doc['created_by']}")

    for line in meta_lines:
        pdf.cell(0, 6, safe_latin1(line), new_x="LMARGIN", new_y="NEXT", fill=True)
    pdf.ln(6)

    if doc.get("objective"):
        _write_section_title(pdf, "Objetivo do Encontro")
        _write_paragraph(pdf, doc["objective"])

    if doc.get("opening_prayer"):
        _write_section_title(pdf, "Oracao Inicial")
        _write_paragraph(pdf, doc["opening_prayer"])

    refs = doc.get("biblical_references") or []
    if refs:
        _write_section_title(pdf, "Referencias Biblicas e Catequeticas")
        _write_bullets(pdf, refs)

    sections = doc.get("development_sections") or []
    if sections:
        _write_section_title(pdf, "Desenvolvimento da Formacao")
        for idx, section in enumerate(sections, start=1):
            sec_title = section.get("title") or f"Parte {idx}"
            sec_duration = section.get("duration_minutes")
            heading = f"{idx}. {sec_title}" + (f" ({sec_duration} min)" if sec_duration else "")
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(30, 41, 59)
            pdf.multi_cell(0, 6, safe_latin1(heading))
            pdf.ln(1)
            if section.get("content"):
                _write_paragraph(pdf, section["content"])

    if doc.get("activity_or_dynamic"):
        _write_section_title(pdf, "Dinamica / Atividade Pratica")
        _write_paragraph(pdf, doc["activity_or_dynamic"])

    questions = doc.get("reflection_questions") or []
    if questions:
        _write_section_title(pdf, "Perguntas para Partilha")
        _write_bullets(pdf, questions)

    if doc.get("closing_prayer"):
        _write_section_title(pdf, "Oracao Final e Compromisso")
        _write_paragraph(pdf, doc["closing_prayer"])

    rag_sources = doc.get("rag_sources_used") or []
    if rag_sources:
        _write_section_title(pdf, "Base de Formacoes Consultada (RAG)")
        _write_bullets(pdf, rag_sources)

    output = pdf.output()
    return bytes(output)
