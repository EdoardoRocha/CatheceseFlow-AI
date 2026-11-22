import json
from langchain_core.tools import tool

from helpers.rag_service import search_knowledge_chunks


@tool
async def search_formation_knowledge(
    query: str,
    parish_id: int | None = None,
    category: str | None = None,
    top_k: int = 5,
) -> str:
    """Pesquisa na base RAG de PDFs de formações anteriores da paróquia para estruturar novas formações com referências e estilo já utilizados.

    Orientações:
    - Passe sempre `parish_id` do contexto do usuário para buscar apenas documentos da paróquia atual.
    - Use `query` descritivo com o tema da formação solicitada (ex.: "Eucaristia", "Dons do Espírito Santo", "Maria").
    - Opcionalmente filtre por `category` ("Geral", "Primeira Comunhão", "Perseverança" ou "Crisma").
    """
    if parish_id is None:
        return json.dumps(
            {
                "matches": [],
                "total": 0,
                "detail": "parish_id não informado no contexto para consultar a base RAG da paróquia.",
            },
            ensure_ascii=False,
        )

    try:
        search_mode, matches = await search_knowledge_chunks(
            query=query,
            parish_id=parish_id,
            category=category,
            top_k=top_k,
        )
        formatted = [
            {
                "document_title": item["document_title"],
                "category": item.get("category", "Geral"),
                "page_number": item["page_number"],
                "score": item["score"],
                "content": item["content"][:1200],
            }
            for item in matches
        ]
        return json.dumps(
            {
                "search_mode": search_mode,
                "total": len(formatted),
                "matches": formatted,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return f"Erro temporário ao consultar a base RAG de formações no MongoDB: {exc}"
