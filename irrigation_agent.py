"""
Fault-Tolerant Irrigation Decision Agent

Stateful irrigation decision system built with LangGraph.

- Deterministic tool-driven logic
- Explicit retry mechanism
- Safe fallback state (MAINTENANCE_REQUIRED)
- Structured JSON output
"""

import random
from typing import TypedDict, Annotated
from enum import Enum
import operator

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field


# ============================================================================
# Models
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


class DecisionOutput(BaseModel):
    field_id: int
    decision: IrrigationDecision
    current_moisture: float | None
    optimal_range: tuple[float, float] | None
    reason: str
    confidence: str
    sensor_attempts: int
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


# ============================================================================
# Mock Tools
# ============================================================================

class MockDatabase:

    FIELDS = {
        1: {"crop_type": CropType.WHEAT, "min_moisture": 25.0, "max_moisture": 45.0, "optimal_moisture": 35.0, "soil_type": "loamy"},
        2: {"crop_type": CropType.CORN, "min_moisture": 30.0, "max_moisture": 50.0, "optimal_moisture": 40.0, "soil_type": "clay"},
        12: {"crop_type": CropType.TOMATO, "min_moisture": 35.0, "max_moisture": 60.0, "optimal_moisture": 47.5, "soil_type": "sandy-loam"},
        15: {"crop_type": CropType.COTTON, "min_moisture": 20.0, "max_moisture": 40.0, "optimal_moisture": 30.0, "soil_type": "sandy"},
        20: {"crop_type": CropType.POTATO, "min_moisture": 40.0, "max_moisture": 65.0, "optimal_moisture": 52.5, "soil_type": "loamy"},
    }

    @classmethod
    def get_field_info(cls, field_id: int) -> FieldInfo | None:
        data = cls.FIELDS.get(field_id)
        if not data:
            return None
        return FieldInfo(field_id=field_id, **data)


class MockSensorNetwork:

    CURRENT_READINGS = {
        1: 28.5,
        2: 45.2,
        12: 32.1,
        15: 35.8,
        20: 55.3,
    }

    @classmethod
    def get_soil_moisture(cls, field_id: int) -> float | None:
        # 20% timeout
        if random.random() < 0.2:
            return None

        # 5% hardware error
        if random.random() < 0.05:
            return random.choice([-50.0, -99.9, 150.0, 999.0])

        if field_id not in cls.CURRENT_READINGS:
            return None

        return cls.CURRENT_READINGS[field_id] + random.uniform(-1.5, 1.5)


# ============================================================================
# LangGraph Nodes
# ============================================================================

def retrieve_field(state: AgentState) -> AgentState:
    field_info = MockDatabase.get_field_info(state["field_id"])

    if field_info is None:
        return {
            **state,
            "errors": [f"Field {state['field_id']} not found"],
            "stage": "failed"
        }

    return {**state, "field_info": field_info, "stage": "field_ok"}


def fetch_sensor(state: AgentState) -> AgentState:
    reading = MockSensorNetwork.get_soil_moisture(state["field_id"])
    attempts = state["sensor_attempts"] + 1

    if reading is None:
        if attempts < state["max_sensor_retries"]:
            return {
                **state,
                "sensor_attempts": attempts,
                "errors": [f"Sensor timeout attempt {attempts}"],
                "stage": "retry"
            }
        return {
            **state,
            "sensor_attempts": attempts,
            "errors": [f"Sensor timeout after {attempts} attempts"],
            "stage": "failed"
        }

    if reading < 0 or reading > 100:
        return {
            **state,
            "moisture_reading": reading,
            "sensor_attempts": attempts,
            "errors": [f"Invalid sensor value {reading}"],
            "stage": "failed"
        }

    return {
        **state,
        "moisture_reading": reading,
        "sensor_attempts": attempts,
        "stage": "sensor_ok"
    }


def validate(state: AgentState) -> AgentState:
    field = state["field_info"]
    moisture = state["moisture_reading"]

    if moisture < field.min_moisture:
        return {
            **state,
            "decision": IrrigationDecision.IRRIGATE,
            "reason": f"Moisture {moisture:.1f}% below minimum {field.min_moisture}%",
            "stage": "done"
        }

    if moisture > field.max_moisture:
        return {
            **state,
            "decision": IrrigationDecision.DO_NOT_IRRIGATE,
            "reason": f"Moisture {moisture:.1f}% above maximum {field.max_moisture}%",
            "stage": "done"
        }

    if moisture < field.optimal_moisture:
        return {
            **state,
            "decision": IrrigationDecision.IRRIGATE,
            "reason": f"Moisture {moisture:.1f}% below optimal {field.optimal_moisture}%",
            "stage": "done"
        }

    return {
        **state,
        "decision": IrrigationDecision.DO_NOT_IRRIGATE,
        "reason": f"Moisture {moisture:.1f}% within optimal range",
        "stage": "done"
    }


def maintenance(state: AgentState) -> AgentState:
    return {
        **state,
        "decision": IrrigationDecision.MAINTENANCE_REQUIRED,
        "reason": "; ".join(state["errors"]),
        "stage": "done"
    }


# ============================================================================
# Routing
# ============================================================================

def route_after_field(state: AgentState):
    return "maintenance" if state["stage"] == "failed" else "fetch_sensor"


def route_after_sensor(state: AgentState):
    if state["stage"] == "retry":
        return "fetch_sensor"
    if state["stage"] == "failed":
        return "maintenance"
    return "validate"


# ============================================================================
# Graph Builder
# ============================================================================

def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve_field", retrieve_field)
    graph.add_node("fetch_sensor", fetch_sensor)
    graph.add_node("validate", validate)
    graph.add_node("maintenance", maintenance)

    graph.set_entry_point("retrieve_field")

    graph.add_conditional_edges(
        "retrieve_field",
        route_after_field,
        {"fetch_sensor": "fetch_sensor", "maintenance": "maintenance"},
    )

    graph.add_conditional_edges(
        "fetch_sensor",
        route_after_sensor,
        {
            "fetch_sensor": "fetch_sensor",
            "validate": "validate",
            "maintenance": "maintenance",
        },
    )

    graph.add_edge("validate", END)
    graph.add_edge("maintenance", END)

    return graph.compile()


# ============================================================================
# Agent Interface
# ============================================================================

class IrrigationAgent:

    def __init__(self, max_sensor_retries: int = 3):
        self.max_sensor_retries = max_sensor_retries
        self.graph = build_agent()

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
        }

        final_state = self.graph.invoke(initial_state)

        return DecisionOutput(
            field_id=field_id,
            decision=final_state["decision"],
            current_moisture=final_state.get("moisture_reading"),
            optimal_range=(
                (
                    final_state["field_info"].min_moisture,
                    final_state["field_info"].max_moisture,
                )
                if final_state.get("field_info")
                else None
            ),
            reason=final_state["reason"],
            confidence=(
                "HIGH"
                if final_state["decision"] != IrrigationDecision.MAINTENANCE_REQUIRED
                else "N/A"
            ),
            sensor_attempts=final_state["sensor_attempts"],
            errors=final_state["errors"],
        )

    def decide_json(self, field_id: int) -> dict:
        return self.decide(field_id).model_dump(mode="json")


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    import json

    agent = IrrigationAgent(max_sensor_retries=3)
    field_id = int(sys.argv[1]) if len(sys.argv) > 1 else 12

    result = agent.decide_json(field_id)
    print(json.dumps(result, indent=2))
