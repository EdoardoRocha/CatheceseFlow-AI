from typing import Literal
from pydantic import BaseModel, Field, field_validator


class MartaMessageItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("O conteúdo da mensagem não pode ser vazio.")
        return cleaned


class MartaPageContext(BaseModel):
    current_path: str = "/dashboard"
    class_id: int | None = None
    lecture_id: int | None = None
    user_name: str | None = None
    user_role: str | None = None
    parish_id: int | None = None


class MartaChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[MartaMessageItem] = Field(default_factory=list)
    context: MartaPageContext = Field(default_factory=MartaPageContext)
    stream: bool = True

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A pergunta não pode estar vazia.")
        return cleaned

    @field_validator("history")
    @classmethod
    def limit_history_window(cls, value: list[MartaMessageItem]) -> list[MartaMessageItem]:
        return value[-10:]


class MartaChatResponse(BaseModel):
    reply: str
    tools_used: list[str] = Field(default_factory=list)
