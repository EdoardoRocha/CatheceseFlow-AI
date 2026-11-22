from tools.classes_tool import get_classes_overview
from tools.faq_tool import get_platform_faq
from tools.formation_pdf_tool import generate_formation_pdf
from tools.knowledge_tool import search_formation_knowledge
from tools.students_age_tool import get_students_age
from tools.students_tool import get_student_attendance
from tools.summaries_tool import search_lecture_summaries

MARTA_TOOLS = [
    get_classes_overview,
    get_student_attendance,
    get_students_age,
    search_lecture_summaries,
    search_formation_knowledge,
    generate_formation_pdf,
    get_platform_faq,
]

TOOLS_BY_NAME = {tool.name: tool for tool in MARTA_TOOLS}

__all__ = ["MARTA_TOOLS", "TOOLS_BY_NAME"]
