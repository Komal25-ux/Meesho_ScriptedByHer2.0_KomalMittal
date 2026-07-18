import logging
from typing import Optional, Type, TypeVar
import google.generativeai as genai
from pydantic import BaseModel, Field
from backend.config import settings

logger = logging.getLogger("sakhi-backend")

class AgentResponse(BaseModel):
    """Dual-output schema: one Gemini call produces both the Hinglish text
    shown in the chat UI and a pure Devanagari translation for Sarvam TTS,
    instead of a second translation call or feeding Sarvam romanized Hindi
    (which it reads back stilted/mispronounced).

    IMAGE POLICY (default-null / whitelist): note that no schema in this file
    has an `image_url` field, and that's deliberate, not an oversight. Asking
    an LLM to reproduce a ~70-character CDN URL byte-for-byte in JSON is a real
    fidelity risk (truncation, "helpful" reformatting) - worse than the bug it
    would be trying to prevent. Every image_url shown to a user is therefore
    Python-controlled and defaults to None; it is only explicitly set by
    orchestrator.py inside one of the whitelisted moments (see each agent's
    node for its specific condition), never emitted by the model itself. Where
    an agent's *reasoning* affects whether an image should show (e.g. did it
    actually answer from context, or is this an apology), that agent gets its
    own boolean flag below - the flag is whitelist-framed (default false,
    explicitly true only for the allowed case) rather than the reverse."""
    ui_text: str = Field(description="The conversational response written in Hinglish (Hindi via English alphabet).")
    tts_text: str = Field(description=(
        "The exact same response translated into pure Hindi Devanagari script for the TTS engine. "
        "Strict rules: never write 'AI Sakhi' - spell it phonetically as 'ए आई सखी'. "
        "Never use currency symbols like '₹' - always spell out the number followed by 'रुपये' "
        "(e.g. '799 रुपये', not '₹799'). Do not include any markdown formatting (*, _, #) or emojis - "
        "Devanagari and basic punctuation only."
    ))

class CatalogCaptionResponse(AgentResponse):
    """Catalog-specific dual output. Adds a phonetic Devanagari transliteration
    of the product name, generated in the same call as the caption, so callers
    that echo the product name back in a tts_text wrapper (e.g. "Didi, <name>
    ke liye ... ready hai") never have to embed the raw Latin-script name -
    which Sarvam reads with English stress patterns even inside an otherwise
    Devanagari sentence."""
    product_name_tts: str = Field(description=(
        "The exact product name transliterated phonetically into Devanagari script, preserving "
        "how it sounds in English - NOT a meaning-based translation. E.g. 'Blue Cotton Kurti' -> "
        "'ब्लू कॉटन कुर्ती', not a translated equivalent like 'नीली सूती कुर्ती'."
    ))

class CustomerAgentResponse(AgentResponse):
    """Customer-agent-specific dual output. Whitelist Condition 2 for images:
    ONLY when the customer explicitly asks about a product and the agent
    successfully retrieves and answers from matching RAG context. Everything
    else - apology/fallback, Order Handoff purchase confirmations, greetings,
    tangents - must NOT show an image. Framed as a positive (default-false)
    flag rather than a fallback-only flag, so every non-whitelisted case is
    excluded by default instead of having to be individually enumerated."""
    answered_from_product_context: bool = Field(description=(
        "True ONLY if you successfully answered the customer's specific product question using the "
        "retrieved context (e.g. confirmed availability, stated price/size/color from context). "
        "False for EVERY other case, with no exceptions: the zero-hallucination apology/fallback, "
        "the Order Handoff purchase-intent response, greetings, or anything not a grounded product answer."
    ))
    return_retention_triggered: bool = Field(description=(
        "True ONLY if the Priority 1 Return Retention Hook applied this turn (the customer asked about "
        "returning, refunding, or exchanging an item, or expressed dissatisfaction with size/fit/quality). "
        "False for every other case. This is read by the orchestrator to hand the conversation off to the "
        "Returns Agent for the customer's next reply - it is not just a descriptive label."
    ))
    purchase_intent_detected: bool = Field(description=(
        "True ONLY if the customer's wording confirms/finalizes a purchase decision on one specific, "
        "already-identified item (e.g. 'ye wali pack kardo', 'iska order kardo') AND the product context "
        "given to you resolves to exactly one product. False for a general/category-level desire to buy or "
        "browse (e.g. 'saree leni hai', 'kurti chahiye') - that is exploratory, not confirmation, and must "
        "fall through to a normal product answer instead. Also False if the wording sounds confirmatory but "
        "no single specific item can be identified from context - ask which item they mean instead of "
        "guessing. Read by the orchestrator to stop immediately with the reseller-notified confirmation, "
        "bypassing any further product search. NOTE: do not add a Python-side default here - Gemini's "
        "response_schema conversion rejects Pydantic Field 'default' metadata outright ('Unknown field for "
        "Schema: default'), which silently fails every model in the fallback chain and returns None."
    ))

class ReturnsAgentResponse(AgentResponse):
    """Returns-agent-specific dual output. Whitelist Condition 3 for images:
    ONLY when the agent is actively naming and recommending one specific
    alternative product from the catalog to replace the returned/problematic
    item. The general "we'll offer a free exchange" response, with no specific
    item named, must NOT show an image."""
    suggests_alternative: bool = Field(description=(
        "True ONLY if an ALTERNATIVE_PRODUCT was provided in the prompt context AND you are actively "
        "naming and recommending that specific product in ui_text as a replacement. False for the "
        "general exchange/refund offer where no specific alternative product is named."
    ))

T = TypeVar("T", bound=BaseModel)

def configure_gemini() -> bool:
    if settings.GEMINI_API_KEY and "YOUR_GEMINI" not in settings.GEMINI_API_KEY:
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            return True
        except Exception as e:
            logger.error(f"Gemini API configuration failed: {e}")
    return False

# The free tier enforces a per-model daily request quota, not a per-key one -
# trying several models in order means one model running dry doesn't stall
# every agent, since each model has its own separate quota bucket.
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-2.0-flash-lite"]

def _model_chain():
    chain = [settings.GEMINI_MODEL]
    for m in FALLBACK_MODELS:
        if m not in chain:
            chain.append(m)
    return chain

def generate_with_fallback(parts):
    """Tries each model in the fallback chain in order, moving to the next on
    any failure (quota exhaustion, retirement, transient error). `parts` is
    whatever genai.GenerativeModel.generate_content accepts - a prompt string,
    or a list mixing text with {"mime_type": ..., "data": ...} blocks for
    multimodal input. Returns the response text, or None if every model failed."""
    if not configure_gemini():
        return None
    last_error = None
    for model_name in _model_chain():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(parts)
            text = response.text.strip()
            if text:
                return text
        except Exception as e:
            last_error = e
            logger.warning(f"Gemini model '{model_name}' failed, trying next fallback: {e}")
            continue
    logger.error(f"All Gemini fallback models failed. Last error: {last_error}")
    return None

def generate_structured_with_fallback(prompt: str, schema: Type[T]) -> Optional[T]:
    """Same fallback chain as generate_with_fallback, but constrains each
    model's output to the given Pydantic schema via Gemini's native
    structured-output mode (response_schema), then validates the parsed
    result. Returns None if every model fails or returns invalid JSON."""
    if not configure_gemini():
        return None
    last_error = None
    for model_name in _model_chain():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=schema
                )
            )
            return schema.model_validate_json(response.text)
        except Exception as e:
            last_error = e
            logger.warning(f"Gemini model '{model_name}' structured call failed, trying next fallback: {e}")
            continue
    logger.error(f"All Gemini fallback models failed for structured output. Last error: {last_error}")
    return None
