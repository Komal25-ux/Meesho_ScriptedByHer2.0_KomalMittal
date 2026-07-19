import logging
from typing import Literal, Optional, Type, TypeVar
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
        "Set to true ONLY if the user is confirming they want to buy a SPECIFIC, currently discussed item. "
        "Captures Hinglish checkout phrases like 'ye lena hai', 'isko pack kar do', 'final karo', or 'ye "
        "order karna hai'. MUST be false for general browsing like 'saree leni hai'. Note the trap: 'leni'/"
        "'lena' are just gender-agreement forms of the same verb, so 'saree leni hai' and 'ye lena hai' look "
        "almost identical on the surface but mean opposite things - the deciding signal is what comes "
        "immediately before it. A CATEGORY NOUN there ('saree', 'kurti') means exploratory browsing, false. "
        "A DEMONSTRATIVE PRONOUN there ('ye', 'isko', 'yehi'), pointing at something already shown or "
        "discussed, means checkout - true, PROVIDED the product context given to you actually resolves to "
        "exactly one specific item; if the wording sounds confirmatory but no single item can be identified "
        "from context, this must still be false (ask which item they mean instead of guessing). Read by the "
        "orchestrator to stop immediately with the reseller-notified confirmation, bypassing any further "
        "product search. NOTE: do not add a Python-side default here - Gemini's response_schema conversion "
        "rejects Pydantic Field 'default' metadata outright ('Unknown field for Schema: default'), which "
        "silently fails every model in the fallback chain and returns None."
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

class IntentRouter(BaseModel):
    """Structured routing decision for the top-level Orchestrator classifier
    (see detect_intent in orchestrator.py). Uses Gemini's native structured-
    output mode (response_schema, via generate_structured_with_fallback) so
    the model is constrained to emit exactly one of the five valid routes,
    instead of the old free-text-JSON approach where a malformed or
    creatively-worded response could fail json.loads entirely or drift
    outside the valid intent set.

    route_to's allowed values are expressed as a Literal (not a Python Enum
    class) - Pydantic maps Literal to a JSON Schema enum constraint exactly
    the same way it would an Enum for Gemini's response_schema conversion,
    and every other classifier schema in this file already uses this pattern
    successfully, so this stays consistent rather than introducing a second
    convention for no behavioral difference. Per-value guidance lives in this
    field's description below, since that's the only part of a Pydantic enum
    field Gemini's schema conversion actually transmits to the model in
    either case - a Python Enum member's docstring/comment is never seen by
    the model, only the field-level description and the literal value list.
    """
    route_to: Literal["CATALOG", "CUSTOMER", "GROWTH", "GENERAL", "RETURNS"] = Field(description=(
        "The single agent this message should be routed to. Decide by evaluating the user's underlying "
        "SEMANTIC GOAL - what they are actually trying to accomplish - rather than matching specific "
        "keywords or exact phrasing. Hindi/Hinglish messages vary enormously in wording for the same "
        "goal (e.g. 'dikha do', 'dikhao', 'kya hai', 'kuch naya hai kya' can all express the same "
        "underlying 'show me products' goal despite sharing almost no words).\n\n"
        "CATALOG: select this if the user wants to browse, view, list, explore options, or see "
        "products, add/list an item for sale, or set a price for something they are selling. Covers "
        "Hinglish phrasing implying visual inspection or inventory checks, direct or indirect, including "
        "bare continuation requests with no product named (asking to see more of what was already being "
        "shown). Only ever valid when the speaker is the RESELLER managing their own shop - never an "
        "end customer.\n\n"
        "CUSTOMER: select this for a buyer's product question (size, material, color, delivery, COD, "
        "return policy, availability), a return/exchange/complaint a buyer raised, a buyer's purchase or "
        "order confirmation (however short, even with no product detail in it), or a buyer's own request "
        "to browse/see more products (including a bare continuation naming nothing new). This is the "
        "buyer-side counterpart of CATALOG's browsing goal, and the correct route for a return/refund/"
        "exchange discussion regardless of how it's phrased.\n\n"
        "GROWTH: select this for sales advice, performance metrics, weekly profit or revenue figures, or "
        "general business-growth coaching for the reseller.\n\n"
        "GENERAL: select this for greetings, small talk, or a question about what Sakhi herself can do - "
        "nothing here implies a product, a sale, or a business metric.\n\n"
        "RETURNS: reserved. A customer can never self-initiate a return through chat text in this system "
        "- returns only ever start via a backend system event, never a message. If a return, refund, or "
        "exchange is being discussed via chat, that is a CUSTOMER-side conversation (the Customer agent "
        "owns return handling), not a reason to select RETURNS."
    ))

T = TypeVar("T", bound=BaseModel)

_CURRENT_KEY_INDEX = 0

def configure_gemini() -> bool:
    global _CURRENT_KEY_INDEX
    keys = [k for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FALLBACK] if k and "YOUR_GEMINI" not in k]
    if not keys:
        logger.error("No valid Gemini API keys found in settings.")
        return False
    try:
        current_key = keys[_CURRENT_KEY_INDEX % len(keys)]
        genai.configure(api_key=current_key)
        return True
    except Exception as e:
        logger.error(f"Gemini API configuration failed with key index {_CURRENT_KEY_INDEX}: {e}")
        return False

def rotate_gemini_key():
    global _CURRENT_KEY_INDEX
    keys = [k for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FALLBACK] if k and "YOUR_GEMINI" not in k]
    if keys:
        _CURRENT_KEY_INDEX = (_CURRENT_KEY_INDEX + 1) % len(keys)
        logger.info(f"Rotating Gemini API Key index to: {_CURRENT_KEY_INDEX}")
        configure_gemini()

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
    """Tries each model in the fallback chain in order. If all models fail due to
    quota exhaustion or invalid keys, rotates to the fallback API key and retries."""
    keys = [k for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FALLBACK] if k and "YOUR_GEMINI" not in k]
    num_keys = len(keys) if keys else 1
    
    last_error = None
    for key_attempt in range(num_keys):
        if not configure_gemini():
            return None
            
        for model_name in _model_chain():
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(parts)
                text = response.text.strip()
                if text:
                    return text
            except Exception as e:
                last_error = e
                logger.warning(f"Gemini model '{model_name}' failed: {e}")
                err_msg = str(e).lower()
                # If it's a quota or credential issue, rotate key immediately
                if any(w in err_msg for w in ["quota", "exhausted", "429", "403", "invalid", "limit"]):
                    break
                continue
                
        # If we exhausted all models with this key, rotate to the next key
        if num_keys > 1:
            rotate_gemini_key()
            
    logger.error(f"All Gemini fallback models and keys failed. Last error: {last_error}")
    return None

def generate_structured_with_fallback(prompt: str, schema: Type[T]) -> Optional[T]:
    """Same fallback chain and key rotation as generate_with_fallback, but
    constrains each model's output to the given Pydantic schema."""
    keys = [k for k in [settings.GEMINI_API_KEY, settings.GEMINI_API_KEY_FALLBACK] if k and "YOUR_GEMINI" not in k]
    num_keys = len(keys) if keys else 1
    
    last_error = None
    for key_attempt in range(num_keys):
        if not configure_gemini():
            return None
            
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
                logger.warning(f"Gemini model '{model_name}' structured call failed: {e}")
                err_msg = str(e).lower()
                if any(w in err_msg for w in ["quota", "exhausted", "429", "403", "invalid", "limit"]):
                    break
                continue
                
        if num_keys > 1:
            rotate_gemini_key()
            
    logger.error(f"All Gemini fallback models and keys failed for structured output. Last error: {last_error}")
    return None
