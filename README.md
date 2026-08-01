# 🧭 People Ops Copilot

Asistente de IA para procesos de selección, diseñado como **soporte a la decisión** del
recruiter — no como decisor automático. Toda recomendación del modelo viene justificada
con evidencia citada textualmente del CV, y el puntaje final se calcula en código de
forma determinística y auditable.

## Cómo funciona (MVP 1 — núcleo de recruiting)

1. **Descripción del puesto → rúbrica.** La IA extrae una rúbrica de competencias
   (técnicas, blandas, idiomas) con pesos, criterios de evidencia y requisitos
   excluyentes — al estilo de una entrevista estructurada. El recruiter la **edita**
   antes de evaluar: la rúbrica es del humano, no del modelo.
2. **CV → evaluación con evidencia.** Cada CV (PDF o texto) se evalúa de forma
   **independiente** contra la rúbrica. Por competencia, el modelo devuelve uno de tres
   estados — *evidencia encontrada*, *evidencia parcial* o *sin evidencia* — junto con
   **citas textuales** del CV y una justificación breve. «Sin evidencia» significa que el
   CV no lo menciona, no que el candidato carezca de la competencia.
3. **Ranking calculado en código.** El puntaje es una suma ponderada determinística de
   los juicios por competencia (`core/scoring.py`). El LLM nunca genera el número: juzga
   evidencia; la aritmética es reproducible y auditable.

### Decisiones de diseño responsable

- **Human-in-the-loop**: la herramienta informa, el recruiter decide. La rúbrica es
  editable y cada informe expone el razonamiento completo para revisión.
- **Sin números mágicos**: no se le pide al modelo un "% de match" (los LLMs generan
  precisión aparente sin sustento). El score sale de pesos definidos por el recruiter.
- **Evaluación independiente**: cada candidato se juzga contra la rúbrica, nunca
  comparándolo con otros (evita efectos de orden).
- **Datos sintéticos**: los CVs de `sample_data/` son ficticios. Nunca subas CVs reales
  a un repositorio.

El marco regulatorio va en esta dirección: el EU AI Act clasifica los sistemas de IA
para reclutamiento como de alto riesgo, y normas como la Local Law 144 de NYC exigen
auditorías de herramientas automatizadas de selección.

## Motores de IA: nube u open source local

La capa de LLM está abstraída detrás de una interfaz común (`core/providers/`), con dos
motores intercambiables desde la barra lateral:

| | **Claude (Anthropic)** | **Ollama (local, open source)** |
|---|---|---|
| Privacidad | Los CVs viajan a la API | 🔒 Los CVs nunca salen de tu máquina |
| Costo | Pago por token | Gratis (corre en tu hardware) |
| Calidad del juicio de evidencia | Alta | Depende del modelo (Llama 3.1 8B es notablemente menos preciso) |
| PDFs | Lectura nativa de documentos | Extracción de texto local (`pypdf`); no lee escaneos |
| Salida estructurada | Garantizada por la API | Decoding restringido de Ollama + validación Pydantic con reintento |

Para RRHH la opción local importa: los CVs son datos personales sensibles, y poder
procesar todo on-premise es un requisito real en muchas organizaciones. El diseño
mitiga la menor calidad del modelo local: la rúbrica siempre es editable por el
recruiter, y el puntaje se calcula en código — el modelo local solo aporta los juicios
de evidencia, que el informe expone con citas para revisión humana.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Opción A — Claude (recomendado por calidad):
export ANTHROPIC_API_KEY="tu-api-key"   # o autenticate con `ant auth login`

# Opción B — modelo local open source (sin API key):
#   1. Instalá Ollama: https://ollama.com
#   2. ollama pull llama3.1

.venv/bin/streamlit run app.py
```

Para probar rápido: creá una búsqueda pegando `sample_data/puesto_customer_success.txt`
y subí los tres CVs sintéticos de `sample_data/`.

## Stack

- **Python + Anthropic API** (`claude-opus-4-8`) con salidas estructuradas
  (`messages.parse` + Pydantic), prompt caching sobre el contexto de la búsqueda y
  lectura nativa de PDFs.
- **Ollama** como motor alternativo open source local (Llama 3.1 por defecto,
  configurable), con salida estructurada vía JSON Schema.
- **Streamlit** para la UI, **SQLite** para persistencia.

## Estructura

```
app.py                    # UI Streamlit (selector de motor incluido)
core/models.py            # Esquemas Pydantic (rúbrica, evaluaciones)
core/prompts.py           # Prompts compartidos entre motores
core/llm.py               # Fachada de proveedores
core/providers/base.py    # Interfaz común (LLMProvider) y LLMError
core/providers/claude.py  # Motor Claude (API de Anthropic)
core/providers/ollama.py  # Motor local open source (Ollama)
core/scoring.py           # Puntaje determinístico + detección de excluyentes faltantes
core/db.py                # Persistencia SQLite
sample_data/              # JD y CVs sintéticos de demo
```

## Roadmap

- **MVP 2**: screening ciego (anonimización de CVs antes de evaluar), preguntas de
  entrevista conductuales (STAR) generadas a partir de los gaps detectados, resumen
  ejecutivo pre-entrevista, emails de invitación/rechazo/seguimiento, log de decisiones
  del recruiter, chequeo de consistencia test-retest de las evaluaciones.
- **MVP 3 (People Ops Copilot)**: generador de descripciones de puesto, matrices de
  competencias, planes de onboarding y desarrollo — como módulos sobre la misma base.
