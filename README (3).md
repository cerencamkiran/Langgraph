# Fault-Tolerant Irrigation Decision Agent
### LLM-Enhanced + Production-Safe Orchestration

A stateful irrigation decision agent built with LangGraph, featuring deterministic control logic and an explainability layer powered by an open-source LLM.

---

## 🎯 Mission

In this system, **LLMs do not directly control physical infrastructure.**
All irrigation decisions are **deterministic and tool-based.**

The LLM is used strictly for:
- Human-readable reasoning
- Operational recommendations
- Transparency on success and failure paths

This ensures:
- No hallucinated "Water On" commands
- No moisture guessing
- Safe fallback to `MAINTENANCE_REQUIRED`

---

## 🔄 High-Level Flow

1. Retrieve field metadata (crop + ideal moisture range)
2. Fetch soil moisture from sensor
3. Validate sensor reading
4. Produce deterministic irrigation decision
5. Generate LLM-based explanation & recommendation
6. Return strict JSON response

---

## 🏗 Architecture

```
LangGraph State Machine
        │
        ▼
Retrieve Field Info
        │
        ▼
Fetch Sensor Data
        │
        ├── Timeout → Retry (max 3x)
        ├── Impossible Value → Maintenance
        └── Valid Reading
                │
                ▼
        Deterministic Validation
                │
                ▼
        Final Decision
                │
                ▼
        LLM Reasoning Layer
                │
                ▼
        Strict JSON Output
```

---

## 🧠 Deterministic Core (Safety-Critical Layer)

All irrigation decisions are **rule-based**.

```python
if moisture < min_threshold:
    decision = IRRIGATE
elif moisture > max_threshold:
    decision = DO_NOT_IRRIGATE
else:
    if moisture < optimal:
        decision = IRRIGATE
    else:
        decision = DO_NOT_IRRIGATE
```

- ✔ No probabilistic reasoning
- ✔ No LLM influence on control logic
- ✔ Same input → same output

---

## 🤖 LLM Layer (Explainability & Recommendation)

**Model used:**
```
Qwen/Qwen2.5-1.5B-Instruct
(Open-source HuggingFace model)
```

The LLM:
- Receives structured state
- Generates `REASONING` and `RECOMMENDATION`
- **Never** guesses moisture
- **Never** overrides deterministic decision

> If the LLM fails → rule-based fallback explanation is used

---

## 🛠 Tool Layer (Mocked Infrastructure)

### 1️⃣ MockDatabase
- Returns crop type + moisture thresholds
- Returns `None` if field not found

### 2️⃣ MockSensorNetwork
- 20% timeout probability (returns `None`)
- 5% hardware error probability (`-50.0` or `999.0`)
- Otherwise returns realistic moisture reading

---

## 🔁 Fault Tolerance Rules

| Scenario | Behavior |
|---|---|
| Field Not Found | `MAINTENANCE_REQUIRED` |
| Sensor Timeout | Retry up to 3 times |
| Sensor Hardware Error | Immediate `MAINTENANCE_REQUIRED` |
| Max Retries Reached | `MAINTENANCE_REQUIRED` |
| LLM Failure | Use rule-based fallback explanation |

---

## 📦 Output Schema (Strict JSON)

```json
{
  "field_id": 12,
  "decision": "IRRIGATE",
  "current_moisture": 32.1,
  "optimal_range": [35.0, 60.0],
  "reason": "...",
  "confidence": "HIGH",
  "sensor_attempts": 1,
  "errors": [],
  "llm_consensus": "...",
  "llm_recommendation": "...",
  "llm_providers_used": ["huggingface"]
}
```

---

## 🧪 Test Coverage

**Deterministic Tests**
- Normal Operation
- Field Not Found
- Sensor Timeout + Retry
- Hardware Error
- Multiple Fields

**LLM Tests**
- LLM on Success Path
- LLM on Sensor Failure
- LLM on Field Not Found

```
Passed: 8 / 8
All tests passed.
```

---

## 🔐 Safety Guarantees

- Never guess moisture levels
- Never bypass sensor validation
- LLM cannot issue control commands
- Maximum 3 retries (no infinite loops)
- Impossible sensor values rejected immediately
- Maintenance fallback is safe default

---

## ▶ Running

**Install:**
```bash
pip install -r requirements.txt
```

**Run:**
```bash
python irrigation_agent.py 12
```

**Run tests:**
```bash
python test_agent.py
```

---

## 🧩 Why This Design?

| Concern | Solution |
|---|---|
| LLM hallucination | LLM not in decision path |
| Sensor unreliability | Retry + validation |
| Infrastructure risk | Safe maintenance fallback |
| Observability | Structured JSON + LLM explanation |
| Extensibility | LangGraph state routing |

---

## 🎯 Summary

This agent demonstrates:
- Production-grade state orchestration (LangGraph)
- Deterministic control for physical safety
- Tool-based reasoning
- Fault tolerance
- Open-source LLM integration
- Explainable decisions
- Strict JSON outputs
