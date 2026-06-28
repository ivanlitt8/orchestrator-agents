import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from dotenv import load_dotenv
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

COLECCION_MEMORIAS = "ejecuciones_exitosas"
RUTA_PERSISTENCIA = Path(__file__).resolve().parent.parent / "data" / "chroma_db"
MODELO_EMBEDDING = "gemini-embedding-001"
MAX_RESULTADO_RESUMIDO = 1200

CAMPOS_MEMORIA_PRINCIPALES = frozenset(
    {"tarea_original", "enfoque_exitoso", "resultado_resumido"}
)
CAMPOS_METADATOS_FILTRABLES = frozenset(
    {"fecha", "sector", "tipo_tarea", "tags", "agentes_utilizados", "aprobado_por_humano"}
)


class _GeminiEmbeddingFunction(EmbeddingFunction):
    """Adaptador de embeddings Gemini compatible con ChromaDB."""

    def __init__(self, api_key: str) -> None:
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=MODELO_EMBEDDING,
            google_api_key=api_key,
        )

    def __call__(self, input: Documents) -> Embeddings:
        return self._embeddings.embed_documents(list(input))


def _obtener_api_key() -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta la variable de entorno GEMINI_API_KEY. "
            "Configúrala en el archivo .env para usar la memoria vectorial."
        )
    return api_key


def _construir_texto_indexacion(tarea_original: str, enfoque_exitoso: str) -> str:
    return (
        f"Tarea: {tarea_original.strip()}\n"
        f"Enfoque exitoso: {enfoque_exitoso.strip()}"
    )


def _serializar_valor_metadato(valor: Any) -> str | int | float | bool:
    """Convierte valores a tipos primitivos soportados por ChromaDB."""
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, list):
        return ", ".join(str(item).strip() for item in valor if str(item).strip())
    return str(valor).strip()


def normalizar_metadatos_memoria(metadatos: dict[str, Any] | None) -> dict[str, str | int | float | bool]:
    """
    Normaliza metadatos para persistencia en ChromaDB.

    ChromaDB solo admite str, int, float y bool. Las listas se serializan
    como strings separados por comas (p. ej. tags).
    """
    if not metadatos:
        return {}

    normalizados: dict[str, str | int | float | bool] = {}
    for clave, valor in metadatos.items():
        if valor is None:
            continue
        texto = _serializar_valor_metadato(valor)
        if texto == "" and not isinstance(texto, bool):
            continue
        normalizados[str(clave)] = texto
    return normalizados


def construir_filtro_chroma(
    filtros: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    Construye cláusula `where` de ChromaDB a partir de filtros de metadatos.

    Soporta claves conocidas: fecha, sector, tipo_tarea, tags, agentes_utilizados.
    Valores de lista (p. ej. tags) se unen con comas antes de filtrar.
    """
    if not filtros:
        return None

    condiciones: list[dict[str, Any]] = []
    for clave, valor in filtros.items():
        if valor is None or valor == "":
            continue
        if clave not in CAMPOS_METADATOS_FILTRABLES:
            continue
        valor_serializado = _serializar_valor_metadato(valor)
        if valor_serializado == "" and not isinstance(valor_serializado, bool):
            continue
        condiciones.append({clave: valor_serializado})

    if not condiciones:
        return None
    if len(condiciones) == 1:
        return condiciones[0]
    return {"$and": condiciones}


@lru_cache(maxsize=1)
def _obtener_coleccion():
    """Cliente persistente de ChromaDB con embeddings Gemini (singleton)."""
    RUTA_PERSISTENCIA.mkdir(parents=True, exist_ok=True)
    cliente = chromadb.PersistentClient(path=str(RUTA_PERSISTENCIA))
    embedding_function = _GeminiEmbeddingFunction(_obtener_api_key())
    return cliente.get_or_create_collection(
        name=COLECCION_MEMORIAS,
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"},
    )


def guardar_memoria(
    tarea_original: str,
    enfoque_exitoso: str,
    resultado_resumido: str,
    metadatos: dict[str, Any] | None = None,
) -> str:
    """
    Persiste una ejecución exitosa en ChromaDB.

    Args:
        tarea_original: Solicitud del usuario.
        enfoque_exitoso: Estrategia/agentes que funcionaron.
        resultado_resumido: Informe final (truncado internamente).
        metadatos: Metadatos adicionales (fecha, sector, tipo_tarea, tags, etc.).

    Returns:
        ID del documento almacenado.
    """
    if not tarea_original.strip():
        raise ValueError("La tarea original no puede estar vacía.")

    coleccion = _obtener_coleccion()
    documento_id = str(uuid.uuid4())
    texto_indexado = _construir_texto_indexacion(tarea_original, enfoque_exitoso)
    resumen = resultado_resumido.strip()[:MAX_RESULTADO_RESUMIDO]

    payload_metadatos = {
        "tarea_original": tarea_original.strip(),
        "enfoque_exitoso": enfoque_exitoso.strip(),
        "resultado_resumido": resumen,
        **normalizar_metadatos_memoria(metadatos),
    }

    coleccion.add(
        ids=[documento_id],
        documents=[texto_indexado],
        metadatas=[payload_metadatos],
    )
    return documento_id


def _extraer_metadatos_secundarios(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        clave: valor
        for clave, valor in metadata.items()
        if clave not in CAMPOS_MEMORIA_PRINCIPALES
    }


def buscar_memorias_similares(
    query_tarea: str,
    limite: int = 3,
    filtros: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Recupera experiencias pasadas semánticamente similares a la nueva solicitud.

    Args:
        query_tarea: Texto de búsqueda semántica (solicitud del usuario).
        limite: Máximo de resultados.
        filtros: Filtros opcionales por metadatos (sector, tipo_tarea, tags, fecha, etc.).

    Returns:
        Lista de memorias con metadatos, campos enriquecidos y score de similitud.
    """
    if not query_tarea.strip():
        return []

    coleccion = _obtener_coleccion()
    if coleccion.count() == 0:
        return []

    filtro_chroma = construir_filtro_chroma(filtros)
    parametros_query: dict[str, Any] = {
        "query_texts": [query_tarea.strip()],
        "n_results": min(limite, coleccion.count()),
        "include": ["metadatas", "distances", "documents"],
    }
    if filtro_chroma is not None:
        parametros_query["where"] = filtro_chroma

    resultados = coleccion.query(**parametros_query)

    memorias: list[dict[str, Any]] = []
    metadatos = resultados.get("metadatas", [[]])[0]
    distancias = resultados.get("distances", [[]])[0]
    documentos = resultados.get("documents", [[]])[0]

    for indice, metadata in enumerate(metadatos):
        if not metadata:
            continue
        distancia = distancias[indice] if indice < len(distancias) else None
        similitud = None if distancia is None else max(0.0, 1.0 - float(distancia))
        metadatos_secundarios = _extraer_metadatos_secundarios(metadata)
        memorias.append(
            {
                "tarea_original": metadata.get("tarea_original", ""),
                "enfoque_exitoso": metadata.get("enfoque_exitoso", ""),
                "resultado_resumido": metadata.get("resultado_resumido", ""),
                "sector": metadata.get("sector", ""),
                "tipo_tarea": metadata.get("tipo_tarea", ""),
                "tags": metadata.get("tags", ""),
                "fecha": metadata.get("fecha", ""),
                "metadatos": metadatos_secundarios,
                "similitud": similitud,
                "documento_indexado": documentos[indice] if indice < len(documentos) else "",
            }
        )

    return memorias
