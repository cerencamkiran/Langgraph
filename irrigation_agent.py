"""
Fault-Tolerant Irrigation Decision Agent — Free LLM (Colab-ready) Edition

Graph flow:
                        START
                          │
                    retrieve_field
                    /            \
              [found]          [not found]
                │                   │
           fetch_sensor         maintenance_decision
           /    |    \               │
      [ok] [retry] [fail]            │
        │            │               │
     validate    maintenance_decision│
        │                 │          │
        └────────┬─────────┘         │
                 │                   │
           llm_reasoning  ◄──────────┘
      (HF local model + rule-based fallback)
                 │
                END

- Deterministic decision: tools + thresholds (NO LLM in decision).
- LLM runs on ALL terminal paths (success or failure) to explain & recommend.
- Uses a NON-GATED HuggingFace model by default (no HF token needed).
"""

import random
import logging
import operator
from enum import Enum
from typing import TypedDict, Annotated
from datetime import datetime

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

# ---------------------------------------------------------------------
# Prevent langchain debug import warning from breaking anything
# ---------------------------------------------------------------------
try:
    import langchain  # type: ignore
    if not hasattr(langchain, "debug"):
        langchain.debug = False  # type: ignore
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# Enums & Models
# ============================================================================

class IrrigationDecision(str, Enum):
    IRRIGATE = "IRRIGATE"
    DO_NOT_IRRIGATE = "DO_NOT_IRRIGATE"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"


class CropType(str, Enum):
    WHEAT = "wheat"
    CORN = "corn"
    TOMATO = "tomato"
    COTTON = "cotton"
    POTATO = "potato"


class FieldInfo(BaseModel):
    field_id: int
    crop_type: CropType
    min_moisture: float
    max_moisture: float
    optimal_moisture: float
    soil_type: str


class LLMResult(BaseModel):
    provider: str
    reasoning: str
    recommendation: str
    success: bool
    error: str | None = None


class DecisionOutput(BaseModel):
    field_id: int
    decision: IrrigationDecision
    current_moisture: float | None
    optimal_range: tuple[float, float] | None
    reason: str
    confidence: str
    sensor_attempts: int

    llm_results: list[dict] = Field(default_factory=list)
    llm_consensus: str | None = None
    llm_recommendation: str | None = None
    llm_providers_used: list[str] = Field(default_factory=list)

    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    errors: list[str] = Field(default_factory=list)

# ============================================================================
# Agent State
# ============================================================================

class AgentState(TypedDict):
    field_id: int
    field_info: FieldInfo | None
    moisture_reading: float | None
    decision: IrrigationDecision | None
    reason: str

    errors: Annotated[list[str], operator.add]
    sensor_attempts: int
    max_sensor_retries: int
    stage: str

    llm_results: list[dict]
    llm_consensus: str | None
    llm_recommendation: str | None
    llm_providers_used: list[str]

# ============================================================================
# Mock Tools
# ============================================================================

class MockDatabase:
    FIELDS = {
        1:  {"crop_type": CropType.WHEAT,  "min_moisture": 25.0, "max_moisture": 45.0, "optimal_moisture": 35.0, "soil_type": "loamy"},
        2:  {"crop_type": CropType.CORN,   "min_moisture": 30.0, "max_moisture": 50.0, "optimal_moisture": 40.0, "soil_type": "clay"},
        12: {"crop_type": CropType.TOMATO, "min_moisture": 35.0, "max_moisture": 60.0, "optimal_moisture": 47.5, "soil_type": "sandy-loam"},
        15: {"crop_type": CropType.COTTON, "min_moisture": 20.0, "max_moisture": 40.0, "optimal_moisture": 30.0, "soil_type": "sandy"},
        20: {"crop_type": CropType.POTATO, "min_moisture": 40.0, "max_moisture": 65.0, "optimal_moisture": 52.5, "soil_type": "loamy"},
    }

    @classmethod
    def get_field_info(cls, field_id: int) -> FieldInfo | None:
        logger.info(f"[DB] Querying field #{field_id}")
        data = cls.FIELDS.get(field_id)
        if not data:
            logger.warning(f"[DB] Field #{field_id} not found")
            return None
        info = FieldInfo(field_id=field_id, **data)
        logger.info(f"[DB] Found: {info.crop_type.value} (optimal: {info.optimal_moisture}%)")
        return info


class MockSensorNetwork:
    CURRENT_READINGS = {1: 28.5, 2: 45.2, 12: 32.1, 15: 35.8, 20: 55.3}

    @classmethod
    def get_soil_moisture(cls, field_id: int) -> float | None:
        logger.info(f"[SENSOR] Reading moisture for field #{field_id}")

        # 20% timeout
        if random.random() < 0.2:
            logger.warning("[SENSOR] Timeout - sensor did not respond")
            return None

        # 5% hardware error
        if random.random() < 0.05:
            error_value = random.choice([-50.0, -99.9, 150.0, 999.0])
            logger.error(f"[SENSOR] Hardware error - invalid reading: {error_value}%")
            return error_value

        if field_id not in cls.CURRENT_READINGS:
            logger.warning(f"[SENSOR] No sensor installed for field #{field_id}")
            return None

        reading = cls.CURRENT_READINGS[field_id] + random.uniform(-1.5, 1.5)
        logger.info(f"[SENSOR] Moisture: {reading:.1f}%")
        return reading

# ============================================================================
# Free LLM Reasoning (NON-GATED HF model) + fallback
# ============================================================================

# Non-gated, good instruction-following for Colab.
HF_MODEL_NAME = "Qwen/Qwen2.5-1.5B-Instruct"
_HF_MODEL = None
_HF_TOKENIZER = None
_HF_TRIED_LOAD = False
_HF_PROVIDER_NAME = f"hf:{HF_MODEL_NAME}"


def _load_hf_model():
    """
    Lazy-load the HF model once.
    If it fails once, we don't keep retrying.
    """
    global _HF_MODEL, _HF_TOKENIZER, _HF_TRIED_LOAD

    if _HF_MODEL is not None and _HF_TOKENIZER is not None:
        return _HF_MODEL, _HF_TOKENIZER

    if _HF_TRIED_LOAD:
        return None, None

    _HF_TRIED_LOAD = True

    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        logger.info(f"[LLM] Loading HuggingFace model: {HF_MODEL_NAME}")
        _HF_TOKENIZER = AutoTokenizer.from_pretrained(HF_MODEL_NAME)
        dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        _HF_MODEL = AutoModelForCausalLM.from_pretrained(
            HF_MODEL_NAME,
            torch_dtype=dtype,
            device_map="auto",
        )
        logger.info("[LLM] HF model loaded successfully")
        return _HF_MODEL, _HF_TOKENIZER

    except Exception as e:
        logger.warning(f"[LLM] HF model load failed, fallback will be used. error={e}")
        _HF_MODEL, _HF_TOKENIZER = None, None
        return None, None


def _build_prompt(state: AgentState) -> str:
    decision = state.get("decision") or IrrigationDecision.MAINTENANCE_REQUIRED
    field = state.get("field_info")
    moisture = state.get("moisture_reading")
    errors = state.get("errors", [])
    attempts = state.get("sensor_attempts", 0)

    if field:
        field_section = (
            "## Field Information\n"
            f"- Field ID     : {field.field_id}\n"
            f"- Crop         : {field.crop_type.value}\n"
            f"- Soil type    : {field.soil_type}\n"
            f"- Min moisture : {field.min_moisture}%\n"
            f"- Max moisture : {field.max_moisture}%\n"
            f"- Optimal      : {field.optimal_moisture}%"
        )
    else:
        field_section = "## Field Information\n- Field not found in database"

    if moisture is not None and 0 <= moisture <= 100:
        sensor_section = (
            "## Sensor Reading\n"
            f"- Current moisture: {moisture:.1f}%\n"
            f"- Sensor attempts : {attempts}"
        )
    else:
        sensor_section = (
            "## Sensor Reading\n"
            "- No valid reading obtained\n"
            f"- Sensor attempts : {attempts}"
        )

    error_section = ""
    if errors:
        error_section = "\n## System Errors\n" + "\n".join(f"- {e}" for e in errors)

    return f"""You are an expert agricultural advisor reviewing an automated irrigation decision.

{field_section}

{sensor_section}
{error_section}

## Automated Decision (DO NOT override)
{decision.value}

## Task
Return exactly:
REASONING: 2-3 simple sentences explaining the outcome using the given data or failures.
RECOMMENDATION: ONE concrete next action (technician/farmer).

REASONING:
RECOMMENDATION:
"""


def _parse_llm_text(text: str) -> tuple[str, str]:
    reasoning = ""
    recommendation = ""
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()
        elif line.startswith("RECOMMENDATION:"):
            recommendation = line.replace("RECOMMENDATION:", "").strip()

    if not reasoning:
        reasoning = (text.strip()[:400] if text.strip() else "")
    if not recommendation:
        recommendation = "Inspect sensors / connectivity and re-run the check."
    return reasoning, recommendation


def _call_hf_llm(prompt: str) -> LLMResult:
    model, tokenizer = _load_hf_model()
    if model is None or tokenizer is None:
        return LLMResult(
            provider=_HF_PROVIDER_NAME,
            reasoning="",
            recommendation="",
            success=False,
            error="HF model not available (load failed).",
        )

    try:
        import torch

        inputs = tokenizer(prompt, return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=180,
                temperature=0.2,
                do_sample=True,
            )

        text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        reasoning, recommendation = _parse_llm_text(text)

        return LLMResult(
            provider=_HF_PROVIDER_NAME,
            reasoning=reasoning,
            recommendation=recommendation,
            success=bool(reasoning),
        )

    except Exception as e:
        return LLMResult(
            provider=_HF_PROVIDER_NAME,
            reasoning="",
            recommendation="",
            success=False,
            error=str(e),
        )


def _rule_based_fallback(state: AgentState) -> LLMResult:
    decision = state.get("decision") or IrrigationDecision.MAINTENANCE_REQUIRED
    field = state.get("field_info")
    moisture = state.get("moisture_reading")
    errors = state.get("errors", [])

    if decision == IrrigationDecision.MAINTENANCE_REQUIRED:
        summary = "; ".join(errors) if errors else "unknown error"
        reasoning = (
            "System could not make a safe decision because required data is missing or invalid. "
            f"Errors: {summary}. Human check is required."
        )
        recommendation = "Send a technician to inspect the sensor and field configuration before irrigating."
    elif decision == IrrigationDecision.IRRIGATE and field and moisture is not None:
        reasoning = (
            f"Soil moisture ({moisture:.1f}%) is below the target range "
            f"({field.min_moisture}%–{field.max_moisture}%) for {field.crop_type.value}."
        )
        recommendation = "Start irrigation and monitor until moisture reaches the optimal target."
    elif field and moisture is not None:
        reasoning = (
            f"Soil moisture ({moisture:.1f}%) is within the safe range "
            f"({field.min_moisture}%–{field.max_moisture}%) for {field.crop_type.value}."
        )
        recommendation = "Do not irrigate now. Re-check sensor data later."
    else:
        reasoning = "Insufficient data to generate explanation."
        recommendation = "Check system configuration and retry."

    return LLMResult(
        provider="rule-based-fallback",
        reasoning=reasoning,
        recommendation=recommendation,
        success=True,
    )


def call_reasoner(state: AgentState) -> list[LLMResult]:
    prompt = _build_prompt(state)
    results = []
    results.append(_call_hf_llm(prompt))
    results.append(_rule_based_fallback(state))
    return results


def _merge_results(results: list[LLMResult]) -> tuple[str, str, list[str]]:
    successful = [r for r in results if r.success and r.reasoning]
    providers_used = [r.provider for r in successful] if successful else ["rule-based-fallback"]

    primary = next((r for r in successful if r.provider.startswith("hf:")), None)
    if primary is None:
        primary = next((r for r in successful if r.provider == "rule-based-fallback"), None)

    if primary:
        consensus = primary.reasoning
        recommendation = primary.recommendation
    else:
        consensus = "No reasoning available."
        recommendation = "Check system configuration."

    extras = [r for r in successful if r is not primary]
    for ex in extras:
        consensus += f"\n\n[{ex.provider}]: {ex.reasoning}"

    return consensus, recommendation, providers_used

# ============================================================================
# LangGraph Nodes
# ============================================================================

def retrieve_field(state: AgentState) -> AgentState:
    logger.info("[STAGE 1] Retrieving field data")
    field_info = MockDatabase.get_field_info(state["field_id"])
    if field_info is None:
        logger.error("[STAGE 1] Failed - field not found")
        return {**state, "errors": [f"Field {state['field_id']} not found"], "stage": "failed"}
    return {**state, "field_info": field_info, "stage": "field_ok"}


def fetch_sensor(state: AgentState) -> AgentState:
    attempts = state["sensor_attempts"] + 1
    logger.info(f"[STAGE 2] Fetching sensor (attempt {attempts}/{state['max_sensor_retries']})")
    reading = MockSensorNetwork.get_soil_moisture(state["field_id"])

    if reading is None:
        if attempts < state["max_sensor_retries"]:
            logger.warning("[STAGE 2] Timeout - retrying")
            return {**state, "sensor_attempts": attempts, "errors": [f"Sensor timeout attempt {attempts}"], "stage": "retry"}
        logger.error("[STAGE 2] Timeout - max retries reached")
        return {**state, "sensor_attempts": attempts, "errors": [f"Sensor timeout after {attempts} attempts"], "stage": "failed"}

    if reading < 0 or reading > 100:
        logger.error(f"[STAGE 2] Hardware error: {reading}%")
        return {
            **state,
            "moisture_reading": reading,
            "sensor_attempts": attempts,
            "errors": [f"Hardware error: impossible sensor value {reading}% (valid range: 0-100%)"],
            "stage": "failed",
        }

    return {**state, "moisture_reading": reading, "sensor_attempts": attempts, "stage": "sensor_ok"}


def validate(state: AgentState) -> AgentState:
    logger.info("[STAGE 3] Validating and deciding")
    field = state["field_info"]
    moisture = state["moisture_reading"]

    if moisture < field.min_moisture:
        decision = IrrigationDecision.IRRIGATE
        reason = f"Moisture {moisture:.1f}% below minimum {field.min_moisture}%"
    elif moisture > field.max_moisture:
        decision = IrrigationDecision.DO_NOT_IRRIGATE
        reason = f"Moisture {moisture:.1f}% above maximum {field.max_moisture}%"
    elif moisture < field.optimal_moisture:
        decision = IrrigationDecision.IRRIGATE
        reason = f"Moisture {moisture:.1f}% below optimal {field.optimal_moisture}%"
    else:
        decision = IrrigationDecision.DO_NOT_IRRIGATE
        reason = f"Moisture {moisture:.1f}% within optimal range"

    logger.info(f"[STAGE 3] {decision.value} — {reason}")
    return {**state, "decision": decision, "reason": reason, "stage": "validated"}


def maintenance_decision(state: AgentState) -> AgentState:
    logger.warning("[STAGE M] Maintenance required")
    error_summary = "; ".join(state["errors"])
    return {**state, "decision": IrrigationDecision.MAINTENANCE_REQUIRED, "reason": error_summary, "stage": "maintenance_set"}


def llm_reasoning(state: AgentState) -> AgentState:
    logger.info("[STAGE LLM] Generating explanation + recommendation (HF + fallback)")
    results = call_reasoner(state)
    consensus, recommendation, providers = _merge_results(results)

    return {
        **state,
        "llm_results": [r.model_dump() for r in results],
        "llm_consensus": consensus,
        "llm_recommendation": recommendation,
        "llm_providers_used": providers,
        "stage": "done",
    }

# ============================================================================
# Routing
# ============================================================================

def route_after_field(state: AgentState):
    return "maintenance_decision" if state["stage"] == "failed" else "fetch_sensor"


def route_after_sensor(state: AgentState):
    if state["stage"] == "retry":
        return "fetch_sensor"
    if state["stage"] == "failed":
        return "maintenance_decision"
    return "validate"


def route_after_validate(state: AgentState):
    return "llm_reasoning"


def route_after_maintenance(state: AgentState):
    return "llm_reasoning"

# ============================================================================
# Confidence
# ============================================================================

def calculate_confidence(decision: IrrigationDecision, moisture: float | None, field_info: FieldInfo | None) -> str:
    if decision == IrrigationDecision.MAINTENANCE_REQUIRED:
        return "N/A"
    if moisture is None or field_info is None:
        return "LOW"
    diff = abs(moisture - field_info.optimal_moisture)
    return "HIGH" if diff < 5 else "MEDIUM" if diff < 10 else "LOW"

# ============================================================================
# Graph Builder
# ============================================================================

def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_field", retrieve_field)
    graph.add_node("fetch_sensor", fetch_sensor)
    graph.add_node("validate", validate)
    graph.add_node("maintenance_decision", maintenance_decision)
    graph.add_node("llm_reasoning", llm_reasoning)

    graph.set_entry_point("retrieve_field")

    graph.add_conditional_edges("retrieve_field", route_after_field,
        {"fetch_sensor": "fetch_sensor", "maintenance_decision": "maintenance_decision"})

    graph.add_conditional_edges("fetch_sensor", route_after_sensor,
        {"fetch_sensor": "fetch_sensor", "validate": "validate", "maintenance_decision": "maintenance_decision"})

    graph.add_conditional_edges("validate", route_after_validate, {"llm_reasoning": "llm_reasoning"})
    graph.add_conditional_edges("maintenance_decision", route_after_maintenance, {"llm_reasoning": "llm_reasoning"})
    graph.add_edge("llm_reasoning", END)

    return graph.compile()

# ============================================================================
# Agent Interface
# ============================================================================

class IrrigationAgent:
    def __init__(self, max_sensor_retries: int = 3):
        self.max_sensor_retries = max_sensor_retries
        self.graph = build_agent()
        logger.info(f"IrrigationAgent initialized (max_retries={max_sensor_retries})")

    def decide(self, field_id: int) -> DecisionOutput:
        initial_state: AgentState = {
            "field_id": field_id,
            "field_info": None,
            "moisture_reading": None,
            "decision": None,
            "reason": "",
            "errors": [],
            "sensor_attempts": 0,
            "max_sensor_retries": self.max_sensor_retries,
            "stage": "init",
            "llm_results": [],
            "llm_consensus": None,
            "llm_recommendation": None,
            "llm_providers_used": [],
        }

        final = self.graph.invoke(initial_state)

        output = DecisionOutput(
            field_id=field_id,
            decision=final["decision"],
            current_moisture=(final.get("moisture_reading") if (final.get("moisture_reading") is None or 0 <= final["moisture_reading"] <= 100) else None),
            optimal_range=((final["field_info"].min_moisture, final["field_info"].max_moisture) if final.get("field_info") else None),
            reason=final["reason"],
            confidence=calculate_confidence(final["decision"], final.get("moisture_reading"), final.get("field_info")),
            sensor_attempts=final["sensor_attempts"],
            llm_results=final.get("llm_results", []),
            llm_consensus=final.get("llm_consensus"),
            llm_recommendation=final.get("llm_recommendation"),
            llm_providers_used=final.get("llm_providers_used", []),
            errors=final["errors"],
        )
        return output

    def decide_json(self, field_id: int) -> dict:
        return self.decide(field_id).model_dump(mode="json")


if __name__ == "__main__":
    import sys, json
    agent = IrrigationAgent(max_sensor_retries=3)
    field_id = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    print(json.dumps(agent.decide_json(field_id), indent=2))
