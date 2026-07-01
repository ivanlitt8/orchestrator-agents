"""Proveedor LLM temporal (desarrollo) vía Groq."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

CHAT_MODEL = "llama-3.3-70b-versatile"
STRUCTURED_OUTPUT_METHOD = "json_mode"


def _obtener_groq_api_key() -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno GROQ_API_KEY. "
            "Configúrala en el archivo .env antes de ejecutar el grafo."
        )
    return api_key


def crear_chat_groq(*, temperature: float = 0.2) -> ChatGroq:
    """ChatGroq compartido por todos los agentes del grafo (streaming habilitado)."""
    return ChatGroq(
        model_name=CHAT_MODEL,
        temperature=temperature,
        streaming=True,
        api_key=_obtener_groq_api_key(),
    )
