import pytest
from unittest.mock import patch
from src.dashboard.components import render_ai_response

# Diccionario de idioma simulado para evitar errores de traducción
MOCK_LANG_DICT = {"insights_title": "Key Insights"}

@pytest.mark.parametrize("malformed_payload", [
    # 1. Completamente vacío
    {}, 
    
    # 2. Solo tiene intent, le falta todo lo demás
    {"intent": "ranking"}, 
    
    # 3. Intent desconocido/no soportado
    {
        "intent": "unknown_intent_xyz",
        "title": "Some Title",
        "executive_summary": "Summary"
    }, 
    
    # 4. Datos del gráfico vacíos
    {
        "intent": "ranking",
        "chart": {"type": "horizontal_bar", "data": []}
    }, 
    
    # 5. Esquema de datos del gráfico totalmente roto
    {
        "intent": "comparison",
        "chart": {"type": "grouped_bar", "data": [{"bad_key": 1, "other_bad_key": "A"}]}
    }, 
    
    # 6. Métrica principal nula (debe saltarla, no fallar)
    {
        "intent": "ranking",
        "main_metric": None 
    },
    
    # 7. Insights y followups nulos o malformados
    {
        "intent": "trend",
        "insights": None,
        "followups": "Esto deberia ser una lista, no un string"
    },
    
    # 8. Gráfico nulo explícito
    {
        "intent": "geographic",
        "chart": None
    } 
])
@patch("src.dashboard.components.st")
def test_render_ai_response_resilience(mock_st, malformed_payload):
    """
    Validates that the main visualization router NEVER raises an uncaught exception,
    even when the AI generates completely broken or missing JSON structures.
    """
    try:
        # Ejecutamos el renderizador con el payload malformado y el mock de Streamlit
        render_ai_response(malformed_payload, MOCK_LANG_DICT)
    except Exception as e:
        pytest.fail(f"render_ai_response raised an exception on malformed payload: {e}")