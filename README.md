# Fault-Tolerant Irrigation Decision Agent

A stateful decision agent built with LangGraph.

This project demonstrates deterministic, tool-based reasoning with retry
handling and safe fallback behavior.

------------------------------------------------------------------------

## Overview

The agent determines whether a field should be irrigated.

It performs the following steps:

1.  Retrieve field information\
2.  Fetch soil moisture data\
3.  Validate the reading\
4.  Produce a structured JSON decision
------------------------------------------------------------------------

## Architecture


```
┌─────────────────────────────────────────────────────────────┐
│                    Irrigation Agent                         │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐  │
│  │  LangGraph   │────>│ State Graph  │────>│   Decision  │  │
│  │ Orchestrator │     │  Execution   │     │   Output    │  │
│  └──────────────┘     └──────────────┘     └─────────────┘  │
│         │                     │                     │       │
│         v                     v                     v       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Agent State (TypedDict)                 │   │
│  │  - field_id, field_info, moisture_reading            │    │
│  │  - decision, errors, retry_count, stage              │    │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         v                    v                    v
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Mock DB     │     │ Sensor Mock  │     │ Validation   │
│  (Tool)      │     │  (Tool)      │     │   Logic      │
└──────────────┘     └──────────────┘     └──────────────┘
```

### State Graph Flow

```
                    START
                      │
                      v
              ┌───────────────┐
              │ Retrieve      │
              │ Field Data    │
              └───────┬───────┘
                      │
              ┌───────┴────────┐
              │                │
         [Found]          [Not Found]
              │                │
              v                v
      ┌───────────────┐   ┌──────────────┐
      │ Fetch Sensor  │   │ Maintenance  │
      │    Data       │   │   Required   │
      └───────┬───────┘   └──────┬───────┘
              │                  │
    ┌─────────┼─────────┐        │
    │         │         │        │
[Success] [Timeout] [Error]      │ 
    │         │         │        │
    v         v         v        v
┌────────┐ ┌────┐  ┌────────┐    │
│Validate│ │Retry│  │Maint.  │   │
│& Decide│ │(3x)│  │Required│    │
└───┬────┘ └──┬─┘  └───┬────┘    │
    │         │        │         │
    └─────────┴────────┴─────────┘
              │
              v
             END
```

---

## 🔧 Technical Implementation

### Core Components

#### 1. **State Management** (LangGraph)
```python
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
```

**Why LangGraph?**
- Explicit state transitions (no hidden state)
- Built-in retry mechanisms via loops
- Clear error propagation
- Debuggable execution paths

#### 2. **Tool Layer** (Mocked but Production-Ready)

**MockDatabase**
- Simulates field information storage
- Returns `None` for non-existent fields
- Provides crop-specific moisture ranges

**MockSensorNetwork**
- 20% random timeout rate (returns `None`)
- 5% hardware error rate (impossible values: -50.0, 999.0)
- Realistic latency simulation
- Field-specific readings

#### 3. **Error Handling Strategy**

| Error Type | Detection | Response | Fallback |
|------------|-----------|----------|----------|
| Field Not Found | `field_info == None` | Immediate escalation | MAINTENANCE_REQUIRED |
| Sensor Timeout | Reading `== None` | Retry up to 3x | MAINTENANCE_REQUIRED |
| Hardware Error | Reading `< 0` or `> 100` | Immediate escalation | MAINTENANCE_REQUIRED |
| Max Retries | Attempts `>= 3` | No further retries | MAINTENANCE_REQUIRED |

#### 4. **Decision Logic** (Pure Logic, No LLM Guessing)

```python
if moisture < min_threshold:
    decision = IRRIGATE
elif moisture > max_threshold:
    decision = DO_NOT_IRRIGATE
else:
    # Within range - optimize toward ideal
    if moisture < optimal:
        decision = IRRIGATE  # Preventive
    else:
        decision = DO_NOT_IRRIGATE  # Maintain
```

**Critical: NO LLM INVOLVEMENT IN DECISION**
- All decisions based on explicit comparisons
- No probabilistic reasoning
- Deterministic outcomes for same inputs

---

## Installation & Usage

### Prerequisites
```bash
python 3.11+
pip 24.0+
```

### Setup

```bash
# Clone repository
git clone <repository-url>
cd topraq-irrigation-agent

# Install dependencies
pip install -r requirements.txt
```

### Running the Agent

**Basic Usage:**
```bash
python irrigation_agent.py 12
```

**Output (JSON):**
```json
{
  "field_id": 12,
  "decision": "IRRIGATE",
  "current_moisture": 32.1,
  "optimal_range": [35.0, 60.0],
  "reason": "Moisture 32.1% is below minimum threshold 35.0%",
  "confidence": "HIGH",
  "sensor_attempts": 1,
  "errors": []
}
```

### Running Tests

**Automated Test Suite:**
```bash
python test_agent.py
```

**Interactive Demo:**
```bash
python test_agent.py --interactive
```

---

## Test Coverage

### Test Scenarios

| Test # | Scenario | Expected Outcome |
|--------|----------|------------------|
| 1 | Normal Operation | Valid decision (IRRIGATE/DO_NOT_IRRIGATE) |
| 2 | Field Not Found | MAINTENANCE_REQUIRED |
| 3 | Sensor Timeout (3 retries) | MAINTENANCE_REQUIRED after 3 attempts |
| 4 | Hardware Error (-50.0%) | Immediate MAINTENANCE_REQUIRED |
| 5 | Multiple Fields | All fields processed correctly |

### Test Results Preview

```
===============================================================================
 TEST SUMMARY
===============================================================================
1. Normal Operation: PASS ✓
2. Field Not Found: PASS ✓
3. Sensor Timeout + Retry: PASS ✓
4. Hardware Error: PASS ✓
5. Multiple Fields: PASS ✓
-------------------------------------------------------------------------------
Total Tests: 5
Passed: 5
Failed: 0
===============================================================================

🎉 ALL TESTS PASSED! 🎉
```

---

## Error Handling Deep Dive

### 1. Sensor Timeout Handling

**Implementation:**
```python
def fetch_sensor_data(state: AgentState) -> AgentState:
    reading = MockSensorNetwork.get_soil_moisture(state["field_id"])
    attempts = state["sensor_attempts"] + 1
    
    if reading is None:
        if attempts < state["max_sensor_retries"]:
            # Loop back to fetch_sensor node
            return {**state, "sensor_attempts": attempts, "stage": "sensor_retry"}
        else:
            # Max retries reached
            return {**state, "errors": [...], "stage": "sensor_failed"}
```

**Graph Routing:**
```python
workflow.add_conditional_edges(
    "fetch_sensor",
    route_after_sensor,
    {
        "retry_sensor": "fetch_sensor",  # LOOP BACK
        "validate": "validate",
        "maintenance": "maintenance"
    }
)
```

**Why This Works:**
- LangGraph supports cycles (retry loops)
- State carries retry counter
- Automatic loop termination via counter

### 2. Hardware Error Detection

**Validation:**
```python
if reading < 0 or reading > 100:
    # Physical impossibility - sensor malfunction
    return {
        **state,
        "errors": [f"Sensor hardware error: impossible value {reading}%"],
        "stage": "sensor_hardware_error"
    }
```

**Safe Fallback:**
- Never attempt to use impossible data
- Immediate escalation to maintenance
- Preserves error details for debugging

### 3. Field Not Found

**Database Layer:**
```python
class MockDatabase:
    FIELDS = {1: {...}, 2: {...}, 12: {...}}  # Known fields
    
    @classmethod
    def get_field_info(cls, field_id: int) -> FieldInfo | None:
        if field_id not in cls.FIELDS:
            return None  # Field doesn't exist
```

**Agent Response:**
```python
if field_info is None:
    return {
        **state,
        "errors": [f"Field #{field_id} not found"],
        "stage": "field_lookup_failed"
    }
```

---

## Design Decisions

### Why LangGraph vs. Plain Python?

| Aspect | Plain Python | LangGraph |
|--------|--------------|-----------|
| State Management | Manual dict passing | Built-in StateGraph |
| Retry Logic | Nested loops | Graph cycles |
| Error Propagation | Try-catch chains | State routing |
| Debuggability | Print statements | Graph visualization |
| Extensibility | Refactor functions | Add nodes/edges |

**Verdict:** LangGraph provides production-grade orchestration with minimal boilerplate.

### Why Pydantic Models?

```python
class DecisionOutput(BaseModel):
    field_id: int
    decision: IrrigationDecision
    current_moisture: float | None
    # ... validation built-in
```

**Benefits:**
- Runtime type checking
- JSON serialization (API-ready)
- Self-documenting schema
- IDE autocomplete support

### Why Strict JSON Output?

**Agent Output Format:**
```json
{
  "field_id": 12,
  "decision": "IRRIGATE",
  "current_moisture": 32.1,
  "optimal_range": [35.0, 60.0],
  "reason": "Moisture 32.1% is below minimum threshold 35.0%",
  "confidence": "HIGH",
  "sensor_attempts": 1,
  "errors": []
}
```

**Rationale:**
- System integration (API contracts)
- Logging and auditing
- No ambiguity (structured data)
- Downstream processing (alerts, reports)

---

### Scaling to Production

**Deployment Options:**
```
Option 1: API Service
  ├── FastAPI endpoint
  ├── POST /decide {"field_id": 12}
  └── Returns DecisionOutput JSON

Option 2: Event-Driven
  ├── Kafka/RabbitMQ consumer
  ├── Processes field events
  └── Publishes decisions to topic

Option 3: Scheduled Jobs
  ├── Kubernetes CronJob
  ├── Runs every 30 minutes
  └── Batch processes all fields
```

## Safety Guarantees

### Critical Safety Rules

1. **Never Guess Moisture Levels**
   - Only use tool-returned data
   - Reject decisions without sensor confirmation
   
2. **Safe Fallback on Error**
   - Unknown state → MAINTENANCE_REQUIRED
   - Human intervention required
   
3. **Explicit Retry Limits**
   - Maximum 3 sensor retries
   - Prevents infinite loops
   
4. **Impossible Value Detection**
   - Moisture < 0% or > 100% → Hardware error
   - Immediate escalation

### What Could Go Wrong (and How We Handle It)

| Risk | Mitigation |
|------|------------|
| LLM hallucinates "Water On" | **No LLM in decision path** |
| Sensor stuck at old value | **Timestamp validation** (future enhancement) |
| Database returns wrong field | **Validate field_id in response** |
| Network partition | **Timeout + retry logic** |
| Race condition (multiple agents) | **Idempotent decisions** |

---

## API Reference

### IrrigationAgent Class

```python
class IrrigationAgent:
    def __init__(self, max_sensor_retries: int = 3)
    
    def decide(self, field_id: int) -> DecisionOutput
        """Returns Pydantic model with full decision details"""
    
    def decide_json(self, field_id: int) -> dict
        """Returns JSON-serializable decision"""
```

### DecisionOutput Schema

```python
{
    "field_id": int,
    "decision": "IRRIGATE" | "DO_NOT_IRRIGATE" | "MAINTENANCE_REQUIRED",
    "current_moisture": float | null,
    "optimal_range": [float, float] | null,
    "reason": str,
    "confidence": "HIGH" | "MEDIUM" | "LOW" | "N/A",
    "sensor_attempts": int,
    "errors": [str]
}
```

---

## Contributing

### Adding New Fields

```python
# In MockDatabase.FIELDS
99: {
    "crop_type": CropType.WHEAT,
    "min_moisture": 25.0,
    "max_moisture": 45.0,
    "optimal_moisture": 35.0,
    "soil_type": "loamy"
}

# In MockSensorNetwork.CURRENT_READINGS
99: 42.5  # Current moisture %
```

### Adding New Sensors

```python
def get_soil_ph(field_id: int) -> float | None:
    """New sensor type"""
    # Implement with same error handling pattern
    pass
```

### Extending Decision Logic

```python
# Add new node to graph
def check_weather_forecast(state: AgentState) -> AgentState:
    # Fetch weather API
    # Adjust decision based on rain forecast
    pass

# Wire into graph
workflow.add_node("weather_check", check_weather_forecast)
workflow.add_edge("validate", "weather_check")
```

---

### Further Reading

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Pydantic Models](https://docs.pydantic.dev/)
- [Production ML Systems](https://martinfowler.com/articles/cd4ml.html)

---
