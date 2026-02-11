"""
Topraq Irrigation Agent - Production-Grade LangGraph Implementation

This agent determines if a specific field needs irrigation through:
1. Multi-step reasoning with fault tolerance
2. Tool-based decision making (no LLM guessing)
3. Proper error handling and retry logic
4. State management through LangGraph
"""

import random
import time
from typing import TypedDict, Annotated, Literal
from enum import Enum
import operator
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field


# ============================================================================
# Data Models and Enums
# ============================================================================

class IrrigationDecision(str, Enum):
    """Possible irrigation decisions"""
    IRRIGATE = "IRRIGATE"
    DO_NOT_IRRIGATE = "DO_NOT_IRRIGATE"
    MAINTENANCE_REQUIRED = "MAINTENANCE_REQUIRED"


class CropType(str, Enum):
    """Supported crop types"""
    WHEAT = "wheat"
    CORN = "corn"
    TOMATO = "tomato"
    COTTON = "cotton"
    POTATO = "potato"


class FieldInfo(BaseModel):
    """Field metadata"""
    field_id: int
    crop_type: CropType
    min_moisture: float = Field(description="Minimum acceptable moisture %")
    max_moisture: float = Field(description="Maximum acceptable moisture %")
    optimal_moisture: float = Field(description="Optimal moisture %")
    soil_type: str


class SensorReading(BaseModel):
    """Sensor data response"""
    field_id: int
    moisture_level: float
    timestamp: str
    sensor_status: str = "OK"


class DecisionOutput(BaseModel):
    """Final decision output"""
    field_id: int
    decision: IrrigationDecision
    current_moisture: float | None
    optimal_range: tuple[float, float] | None
    reason: str
    confidence: str
    sensor_attempts: int = 0
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# Agent State
# ============================================================================

class AgentState(TypedDict):
    """LangGraph state for the irrigation agent"""
    field_id: int
    field_info: FieldInfo | None
    moisture_reading: float | None
    decision: IrrigationDecision | None
    reason: str
    errors: Annotated[list[str], operator.add]
    sensor_attempts: int
    max_sensor_retries: int
    stage: str  # Current processing stage


# ============================================================================
# Mock Database and Sensor Tools
# ============================================================================

class MockDatabase:
    """Simulates field database with realistic data"""
    
    FIELDS = {
        1: {"crop_type": CropType.WHEAT, "min_moisture": 25.0, "max_moisture": 45.0, 
            "optimal_moisture": 35.0, "soil_type": "loamy"},
        2: {"crop_type": CropType.CORN, "min_moisture": 30.0, "max_moisture": 50.0,
            "optimal_moisture": 40.0, "soil_type": "clay"},
        12: {"crop_type": CropType.TOMATO, "min_moisture": 35.0, "max_moisture": 60.0,
             "optimal_moisture": 47.5, "soil_type": "sandy-loam"},
        15: {"crop_type": CropType.COTTON, "min_moisture": 20.0, "max_moisture": 40.0,
             "optimal_moisture": 30.0, "soil_type": "sandy"},
        20: {"crop_type": CropType.POTATO, "min_moisture": 40.0, "max_moisture": 65.0,
             "optimal_moisture": 52.5, "soil_type": "loamy"},
    }
    
    @classmethod
    def get_field_info(cls, field_id: int) -> FieldInfo | None:
        """
        Retrieve field information from database.
        Twist: Sometimes returns None for non-existent fields.
        """
        print(f"[DB] Querying field info for Field #{field_id}")
        
        if field_id not in cls.FIELDS:
            print(f"[DB] ❌ Field #{field_id} not found")
            return None
        
        data = cls.FIELDS[field_id]
        field = FieldInfo(
            field_id=field_id,
            crop_type=data["crop_type"],
            min_moisture=data["min_moisture"],
            max_moisture=data["max_moisture"],
            optimal_moisture=data["optimal_moisture"],
            soil_type=data["soil_type"]
        )
        print(f"[DB] ✓ Found: {field.crop_type.value} (optimal: {field.optimal_moisture}%)")
        return field


class MockSensorNetwork:
    """
    Simulates sensor network with realistic failures.
    Implements 20% random failure rate and hardware errors.
    """
    
    # Realistic moisture readings by field
    CURRENT_READINGS = {
        1: 28.5,   # Wheat - slightly dry
        2: 45.2,   # Corn - good
        12: 32.1,  # Tomato - needs water
        15: 35.8,  # Cotton - good
        20: 55.3,  # Potato - good
    }
    
    @classmethod
    def get_soil_moisture(cls, field_id: int) -> float | None:
        """
        Get current soil moisture reading.
        Twist: 20% failure rate + occasional hardware errors
        """
        print(f"[SENSOR] Reading moisture for Field #{field_id}...")
        time.sleep(0.1)  # Simulate network latency
        
        # 20% chance of timeout (None)
        if random.random() < 0.2:
            print(f"[SENSOR] ⏱️ Timeout - sensor did not respond")
            return None
        
        # 5% chance of hardware error (impossible values)
        if random.random() < 0.05:
            error_value = random.choice([-50.0, -99.9, 150.0, 999.0])
            print(f"[SENSOR] ⚠️ Hardware error - invalid reading: {error_value}%")
            return error_value
        
        # Normal reading
        if field_id in cls.CURRENT_READINGS:
            reading = cls.CURRENT_READINGS[field_id]
            # Add small random variance
            reading += random.uniform(-1.5, 1.5)
            print(f"[SENSOR] ✓ Moisture: {reading:.1f}%")
            return reading
        
        print(f"[SENSOR] ❌ No sensor installed for Field #{field_id}")
        return None


# ============================================================================
# LangGraph Node Functions
# ============================================================================

def retrieve_field_data(state: AgentState) -> AgentState:
    """
    Node 1: Retrieve field information from database.
    Handles field-not-found errors.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 1: Retrieving Field Data")
    print(f"{'='*60}")
    
    field_info = MockDatabase.get_field_info(state["field_id"])
    
    if field_info is None:
        return {
            **state,
            "field_info": None,
            "errors": [f"Field #{state['field_id']} not found in database"],
            "stage": "field_lookup_failed"
        }
    
    return {
        **state,
        "field_info": field_info,
        "stage": "field_data_retrieved"
    }


def fetch_sensor_data(state: AgentState) -> AgentState:
    """
    Node 2: Fetch soil moisture from sensor network.
    Implements retry logic for timeouts.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 2: Fetching Sensor Data (Attempt {state['sensor_attempts'] + 1})")
    print(f"{'='*60}")
    
    reading = MockSensorNetwork.get_soil_moisture(state["field_id"])
    attempts = state["sensor_attempts"] + 1
    
    # Handle timeout (None response)
    if reading is None:
        if attempts < state["max_sensor_retries"]:
            print(f"[RETRY] Attempting retry {attempts}/{state['max_sensor_retries']}")
            return {
                **state,
                "sensor_attempts": attempts,
                "errors": [f"Sensor timeout on attempt {attempts}"],
                "stage": "sensor_retry"
            }
        else:
            print(f"[RETRY] Max retries reached. Escalating to maintenance.")
            return {
                **state,
                "sensor_attempts": attempts,
                "errors": [f"Sensor timeout after {attempts} attempts"],
                "stage": "sensor_failed"
            }
    
    # Handle hardware errors (impossible values)
    if reading < 0 or reading > 100:
        print(f"[ERROR] Sensor hardware malfunction detected: {reading}%")
        return {
            **state,
            "moisture_reading": reading,
            "sensor_attempts": attempts,
            "errors": [f"Sensor hardware error: impossible value {reading}%"],
            "stage": "sensor_hardware_error"
        }
    
    # Valid reading
    return {
        **state,
        "moisture_reading": reading,
        "sensor_attempts": attempts,
        "stage": "sensor_data_retrieved"
    }


def validate_and_decide(state: AgentState) -> AgentState:
    """
    Node 3: Validate sensor data against crop requirements.
    Make irrigation decision based on logic, not LLM guessing.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 3: Validation & Decision Logic")
    print(f"{'='*60}")
    
    field_info = state["field_info"]
    moisture = state["moisture_reading"]
    
    print(f"[LOGIC] Current Moisture: {moisture:.1f}%")
    print(f"[LOGIC] Optimal Range: {field_info.min_moisture}% - {field_info.max_moisture}%")
    print(f"[LOGIC] Optimal Point: {field_info.optimal_moisture}%")
    
    # Decision logic
    if moisture < field_info.min_moisture:
        decision = IrrigationDecision.IRRIGATE
        reason = f"Moisture {moisture:.1f}% is below minimum threshold {field_info.min_moisture}%"
        confidence = "HIGH"
    elif moisture > field_info.max_moisture:
        decision = IrrigationDecision.DO_NOT_IRRIGATE
        reason = f"Moisture {moisture:.1f}% exceeds maximum threshold {field_info.max_moisture}%"
        confidence = "HIGH"
    else:
        # Within acceptable range - check if closer to min or optimal
        if moisture < field_info.optimal_moisture:
            decision = IrrigationDecision.IRRIGATE
            reason = f"Moisture {moisture:.1f}% is within range but below optimal {field_info.optimal_moisture}%"
            confidence = "MEDIUM"
        else:
            decision = IrrigationDecision.DO_NOT_IRRIGATE
            reason = f"Moisture {moisture:.1f}% is optimal (target: {field_info.optimal_moisture}%)"
            confidence = "HIGH"
    
    print(f"[DECISION] {decision.value}")
    print(f"[REASON] {reason}")
    
    return {
        **state,
        "decision": decision,
        "reason": reason,
        "stage": "decision_made"
    }


def handle_maintenance_required(state: AgentState) -> AgentState:
    """
    Node 4: Handle maintenance-required scenarios.
    Called when sensors fail or return invalid data.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 4: Maintenance Mode")
    print(f"{'='*60}")
    
    print("[FALLBACK] Entering safe state - MAINTENANCE_REQUIRED")
    
    error_summary = "; ".join(state["errors"])
    
    return {
        **state,
        "decision": IrrigationDecision.MAINTENANCE_REQUIRED,
        "reason": f"System error requires manual intervention: {error_summary}",
        "stage": "maintenance_mode"
    }


# ============================================================================
# Routing Functions
# ============================================================================

def route_after_field_lookup(state: AgentState) -> str:
    """Route based on field lookup success"""
    if state["stage"] == "field_lookup_failed":
        return "maintenance"
    return "fetch_sensor"


def route_after_sensor(state: AgentState) -> str:
    """Route based on sensor reading result"""
    stage = state["stage"]
    
    if stage == "sensor_retry":
        return "retry_sensor"
    elif stage == "sensor_failed" or stage == "sensor_hardware_error":
        return "maintenance"
    else:  # sensor_data_retrieved
        return "validate"


def route_to_end(state: AgentState) -> str:
    """Always route to END after decision"""
    return END


# ============================================================================
# LangGraph Construction
# ============================================================================

def build_irrigation_agent() -> StateGraph:
    """
    Construct the irrigation decision agent graph.
    
    Graph structure:
    START -> retrieve_field -> fetch_sensor -> validate -> END
                   |               |              
                   v               v              
              maintenance      maintenance
                   |               |
                   +-------+-------+
                           |
                           v
                          END
    """
    
    # Create graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("retrieve_field", retrieve_field_data)
    workflow.add_node("fetch_sensor", fetch_sensor_data)
    workflow.add_node("validate", validate_and_decide)
    workflow.add_node("maintenance", handle_maintenance_required)
    
    # Add edges with routing
    workflow.set_entry_point("retrieve_field")
    
    workflow.add_conditional_edges(
        "retrieve_field",
        route_after_field_lookup,
        {
            "fetch_sensor": "fetch_sensor",
            "maintenance": "maintenance"
        }
    )
    
    workflow.add_conditional_edges(
        "fetch_sensor",
        route_after_sensor,
        {
            "retry_sensor": "fetch_sensor",  # Loop back for retry
            "validate": "validate",
            "maintenance": "maintenance"
        }
    )
    
    workflow.add_edge("validate", END)
    workflow.add_edge("maintenance", END)
    
    return workflow.compile()


# ============================================================================
# Main Agent Interface
# ============================================================================

class IrrigationAgent:
    """
    Production-grade irrigation decision agent.
    Uses LangGraph for orchestration and state management.
    """
    
    def __init__(self, max_sensor_retries: int = 3):
        self.max_sensor_retries = max_sensor_retries
        self.graph = build_irrigation_agent()
    
    def decide(self, field_id: int) -> DecisionOutput:
        """
        Main decision entry point.
        
        Args:
            field_id: The field to evaluate
            
        Returns:
            DecisionOutput with decision and reasoning
        """
        print(f"\n{'#'*60}")
        print(f"# IRRIGATION AGENT STARTED")
        print(f"# Query: Should we irrigate Field #{field_id}?")
        print(f"{'#'*60}")
        
        # Initialize state
        initial_state: AgentState = {
            "field_id": field_id,
            "field_info": None,
            "moisture_reading": None,
            "decision": None,
            "reason": "",
            "errors": [],
            "sensor_attempts": 0,
            "max_sensor_retries": self.max_sensor_retries,
            "stage": "initialized"
        }
        
        # Execute graph
        final_state = self.graph.invoke(initial_state)
        
        # Build output
        output = DecisionOutput(
            field_id=field_id,
            decision=final_state["decision"],
            current_moisture=final_state.get("moisture_reading"),
            optimal_range=(
                (final_state["field_info"].min_moisture, final_state["field_info"].max_moisture)
                if final_state.get("field_info") else None
            ),
            reason=final_state["reason"],
            confidence="HIGH" if final_state["decision"] != IrrigationDecision.MAINTENANCE_REQUIRED else "N/A",
            sensor_attempts=final_state["sensor_attempts"],
            errors=final_state["errors"]
        )
        
        print(f"\n{'#'*60}")
        print(f"# FINAL DECISION")
        print(f"{'#'*60}")
        print(f"Field ID: {output.field_id}")
        print(f"Decision: {output.decision.value}")
        print(f"Current Moisture: {output.current_moisture}%")
        print(f"Optimal Range: {output.optimal_range}")
        print(f"Reason: {output.reason}")
        print(f"Sensor Attempts: {output.sensor_attempts}")
        if output.errors:
            print(f"Errors: {', '.join(output.errors)}")
        print(f"{'#'*60}\n")
        
        return output
    
    def decide_json(self, field_id: int) -> dict:
        """Return decision as strict JSON (API format)"""
        output = self.decide(field_id)
        return output.model_dump(mode='json')


# ============================================================================
# CLI Interface
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Example usage
    agent = IrrigationAgent(max_sensor_retries=3)
    
    if len(sys.argv) > 1:
        field_id = int(sys.argv[1])
    else:
        field_id = 12  # Default to Field #12
    
    # Make decision
    result = agent.decide_json(field_id)
    
    # Output JSON
    import json
    print("\n" + "="*60)
    print("JSON OUTPUT:")
    print("="*60)
    print(json.dumps(result, indent=2))
