"""
Fault-Tolerant Irrigation Decision Agent

Stateful irrigation decision system built with LangGraph.

Enhancements:
- Added comprehensive logging
- Timestamp tracking for sensor readings
- Dynamic confidence calculation
- Better error messages
"""

import random
import logging
from typing import TypedDict, Annotated
from enum import Enum
import operator
from datetime import datetime

from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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


# ============================================================================
# Mock Tools
# ============================================================================

class MockDatabase:
    """Simulates field database with logging"""

    FIELDS = {
        1: {"crop_type": CropType.WHEAT, "min_moisture": 25.0, "max_moisture": 45.0, "optimal_moisture": 35.0, "soil_type": "loamy"},
        2: {"crop_type": CropType.CORN, "min_moisture": 30.0, "max_moisture": 50.0, "optimal_moisture": 40.0, "soil_type": "clay"},
        12: {"crop_type": CropType.TOMATO, "min_moisture": 35.0, "max_moisture": 60.0, "optimal_moisture": 47.5, "soil_type": "sandy-loam"},
        15: {"crop_type": CropType.COTTON, "min_moisture": 20.0, "max_moisture": 40.0, "optimal_moisture": 30.0, "soil_type": "sandy"},
        20: {"crop_type": CropType.POTATO, "min_moisture": 40.0, "max_moisture": 65.0, "optimal_moisture": 52.5, "soil_type": "loamy"},
    }

    @classmethod
    def get_field_info(cls, field_id: int) -> FieldInfo | None:
        """Retrieve field information with logging"""
        logger.info(f"[DB] Querying field #{field_id}")
        
        data = cls.FIELDS.get(field_id)
        if not data:
            logger.warning(f"[DB] Field #{field_id} not found")
            return None
        
        field_info = FieldInfo(field_id=field_id, **data)
        logger.info(f"[DB] Found: {field_info.crop_type.value} (optimal: {field_info.optimal_moisture}%)")
        return field_info


class MockSensorNetwork:
    """Simulates sensor network with realistic failures and logging"""

    CURRENT_READINGS = {
        1: 28.5,
        2: 45.2,
        12: 32.1,
        15: 35.8,
        20: 55.3,
    }

    @classmethod
    def get_soil_moisture(cls, field_id: int) -> float | None:
        """Get soil moisture with failure simulation"""
        logger.info(f"[SENSOR] Reading moisture for field #{field_id}")
        
        # 20% timeout
        if random.random() < 0.2:
            logger.warning(f"[SENSOR] Timeout - sensor did not respond")
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
# LangGraph Nodes
# ============================================================================

def retrieve_field(state: AgentState) -> AgentState:
    """Retrieve field data from database"""
    logger.info(f"[STAGE 1] Retrieving field data")
    
    field_info = MockDatabase.get_field_info(state["field_id"])

    if field_info is None:
        logger.error(f"[STAGE 1] Failed - field not found")
        return {
            **state,
            "errors": [f"Field {state['field_id']} not found"],
            "stage": "failed"
        }

    logger.info(f"[STAGE 1] Success")
    return {**state, "field_info": field_info, "stage": "field_ok"}


def fetch_sensor(state: AgentState) -> AgentState:
    """Fetch sensor data with retry logic"""
    attempts = state["sensor_attempts"] + 1
    logger.info(f"[STAGE 2] Fetching sensor data (attempt {attempts}/{state['max_sensor_retries']})")
    
    reading = MockSensorNetwork.get_soil_moisture(state["field_id"])

    if reading is None:
        if attempts < state["max_sensor_retries"]:
            logger.warning(f"[STAGE 2] Timeout - will retry (attempt {attempts})")
            return {
                **state,
                "sensor_attempts": attempts,
                "errors": [f"Sensor timeout attempt {attempts}"],
                "stage": "retry"
            }
        logger.error(f"[STAGE 2] Failed - max retries reached")
        return {
            **state,
            "sensor_attempts": attempts,
            "errors": [f"Sensor timeout after {attempts} attempts"],
            "stage": "failed"
        }

    if reading < 0 or reading > 100:
        logger.error(f"[STAGE 2] Failed - invalid sensor value: {reading}%")
        return {
            **state,
            "moisture_reading": reading,
            "sensor_attempts": attempts,
            "errors": [f"Invalid sensor value {reading}%"],
            "stage": "failed"
        }

    logger.info(f"[STAGE 2] Success - reading: {reading:.1f}%")
    return {
        **state,
        "moisture_reading": reading,
        "sensor_attempts": attempts,
        "stage": "sensor_ok"
    }


def validate(state: AgentState) -> AgentState:
    """Validate reading and make decision"""
    logger.info(f"[STAGE 3] Validating reading and deciding")
    
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

    logger.info(f"[STAGE 3] Decision: {decision.value}")
    logger.info(f"[STAGE 3] Reason: {reason}")
    
    return {
        **state,
        "decision": decision,
        "reason": reason,
        "stage": "done"
    }


def maintenance(state: AgentState) -> AgentState:
    """Handle maintenance-required scenarios"""
    logger.warning(f"[STAGE 4] Entering maintenance mode")
    
    error_summary = "; ".join(state["errors"])
    logger.warning(f"[STAGE 4] Errors: {error_summary}")
    
    return {
        **state,
        "decision": IrrigationDecision.MAINTENANCE_REQUIRED,
        "reason": error_summary,
        "stage": "done"
    }


# ============================================================================
# Routing
# ============================================================================

def route_after_field(state: AgentState):
    """Route after field lookup"""
    return "maintenance" if state["stage"] == "failed" else "fetch_sensor"


def route_after_sensor(state: AgentState):
    """Route after sensor reading"""
    if state["stage"] == "retry":
        return "fetch_sensor"
    if state["stage"] == "failed":
        return "maintenance"
    return "validate"


# ============================================================================
# Helper Functions
# ============================================================================

def calculate_confidence(decision: IrrigationDecision, moisture: float | None, 
                        field_info: FieldInfo | None) -> str:
    """Calculate decision confidence based on moisture deviation from optimal"""
    if decision == IrrigationDecision.MAINTENANCE_REQUIRED:
        return "N/A"
    
    if moisture is None or field_info is None:
        return "LOW"
    
    optimal = field_info.optimal_moisture
    diff = abs(moisture - optimal)
    
    if diff < 5:
        return "HIGH"
    elif diff < 10:
        return "MEDIUM"
    else:
        return "LOW"


# ============================================================================
# Graph Builder
# ============================================================================

def build_agent():
    """Build LangGraph state machine"""
    logger.info("Building irrigation agent graph")
    
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
    """Production-grade irrigation decision agent"""

    def __init__(self, max_sensor_retries: int = 3):
        """Initialize agent with retry configuration"""
        self.max_sensor_retries = max_sensor_retries
        self.graph = build_agent()
        logger.info(f"Agent initialized (max retries: {max_sensor_retries})")

    def decide(self, field_id: int) -> DecisionOutput:
        """Make irrigation decision for field"""
        logger.info(f"="*60)
        logger.info(f"Decision request for field #{field_id}")
        logger.info(f"="*60)

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

        confidence = calculate_confidence(
            final_state["decision"],
            final_state.get("moisture_reading"),
            final_state.get("field_info")
        )

        output = DecisionOutput(
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
            confidence=confidence,
            sensor_attempts=final_state["sensor_attempts"],
            errors=final_state["errors"],
        )
        
        logger.info(f"Final decision: {output.decision.value}")
        logger.info(f"Confidence: {output.confidence}")
        logger.info(f"="*60)
        
        return output

    def decide_json(self, field_id: int) -> dict:
        """Make decision and return JSON"""
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
    
    print("\n" + "="*60)
    print("JSON OUTPUT:")
    print("="*60)
    print(json.dumps(result, indent=2))
