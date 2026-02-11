# Topraq Irrigation Agent - Architecture Diagrams

## 1. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         IRRIGATION AGENT                             │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    LangGraph Orchestrator                     │   │
│  │                                                                │   │
│  │  ┌─────────────┐      ┌──────────────┐      ┌─────────────┐  │   │
│  │  │   State     │─────>│  Graph       │─────>│  Decision   │  │   │
│  │  │   Manager   │      │  Executor    │      │  Output     │  │   │
│  │  └─────────────┘      └──────────────┘      └─────────────┘  │   │
│  │         │                     │                     │          │   │
│  │         └─────────────────────┴─────────────────────┘          │   │
│  │                               │                                 │   │
│  └───────────────────────────────┼─────────────────────────────────┘   │
│                                  │                                     │
│  ┌───────────────────────────────┼─────────────────────────────────┐   │
│  │                        Agent State                              │   │
│  │  ┌────────────────────────────────────────────────────────┐    │   │
│  │  │ field_id          | int                                │    │   │
│  │  │ field_info        | FieldInfo | None                  │    │   │
│  │  │ moisture_reading  | float | None                      │    │   │
│  │  │ decision          | IrrigationDecision | None         │    │   │
│  │  │ errors            | list[str]                         │    │   │
│  │  │ sensor_attempts   | int                                │    │   │
│  │  │ stage             | str                                │    │   │
│  │  └────────────────────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                       │
└───────────────────────┬───────────────────┬───────────────────────────┘
                        │                   │
                        │                   │
        ┌───────────────┴──────┐   ┌────────┴──────────┐
        │                       │   │                    │
        v                       v   v                    v
┌──────────────┐      ┌──────────────┐        ┌──────────────┐
│ MockDatabase │      │MockSensor    │        │  Validation  │
│   (Tool)     │      │  Network     │        │    Logic     │
│              │      │   (Tool)     │        │              │
│ - get_field  │      │ - get_soil   │        │ - compare    │
│   _info()    │      │   _moisture()│        │ - decide     │
│              │      │              │        │              │
│ Returns:     │      │ Returns:     │        │ Returns:     │
│ FieldInfo or │      │ float or     │        │ IRRIGATE     │
│ None         │      │ None         │        │ DO_NOT       │
│              │      │              │        │ MAINTENANCE  │
└──────────────┘      └──────────────┘        └──────────────┘
```

---

## 2. LangGraph State Flow

```
                              START
                                │
                                │ Initialize State
                                │
                                v
                    ┌───────────────────────┐
                    │   retrieve_field      │
                    │   (Node 1)            │
                    │                       │
                    │ - Query MockDatabase  │
                    │ - Get FieldInfo       │
                    └───────────┬───────────┘
                                │
                    ┌───────────┴──────────┐
                    │                      │
              [field_info != None]   [field_info == None]
                    │                      │
                    v                      v
        ┌───────────────────────┐   ┌──────────────────┐
        │   fetch_sensor        │   │  maintenance     │
        │   (Node 2)            │   │  (Node 4)        │
        │                       │   │                  │
        │ - Query Sensor        │   │ - Set decision   │
        │ - Handle timeouts     │   │ - Log errors     │
        │ - Retry logic         │   └─────────┬────────┘
        └───────────┬───────────┘             │
                    │                         │
        ┌───────────┴──────────┬──────────────┼─────────┐
        │                      │              │         │
    [Valid]              [Timeout]     [Hardware]       │
    [0-100%]            [None]         [<0 or >100]     │
        │                      │              │         │
        v                      v              v         │
┌──────────────┐    ┌──────────────┐   ┌─────────────┐ │
│  validate    │    │ retry_sensor │   │ maintenance │ │
│  (Node 3)    │    │ (Loop back)  │   │ (Node 4)    │ │
│              │    │              │   │             │ │
│ - Compare    │    │ attempts++   │   │ Safe state  │ │
│ - Decide     │    │ if < max     │   │             │ │
└──────┬───────┘    └──────┬───────┘   └──────┬──────┘ │
       │                   │                  │        │
       │                   │ [retry]          │        │
       │                   └──────────────────┘        │
       │                                                │
       │                                                │
       └────────────────────┬───────────────────────────┘
                            │
                            v
                          END
                            │
                            v
                  ┌─────────────────┐
                  │ DecisionOutput  │
                  │                 │
                  │ - field_id      │
                  │ - decision      │
                  │ - moisture      │
                  │ - reason        │
                  │ - errors[]      │
                  │ - attempts      │
                  └─────────────────┘
```

---

## 3. Error Handling Flow

```
                    Sensor Reading
                          │
                          v
                    ┌─────────────┐
                    │  Get Value  │
                    └─────┬───────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          v               v               v
    [None/Timeout]  [Valid: 0-100]  [Invalid: <0 or >100]
          │               │               │
          v               v               v
    ┌──────────┐    ┌──────────┐    ┌──────────────┐
    │ attempts │    │ Continue │    │   HARDWARE   │
    │    ++    │    │    to    │    │    ERROR     │
    └────┬─────┘    │ Validate │    └──────┬───────┘
         │          └──────────┘           │
         v                                 v
    ┌─────────┐                      ┌──────────────┐
    │attempts │                      │ MAINTENANCE  │
    │  < 3?   │                      │   REQUIRED   │
    └────┬────┘                      │              │
         │                           │ NO RETRY     │
    ┌────┴────┐                      └──────────────┘
    │         │
   YES       NO
    │         │
    v         v
  RETRY   ┌──────────────┐
   (Loop) │ MAINTENANCE  │
          │   REQUIRED   │
          │              │
          │ Max attempts │
          └──────────────┘


Decision Logic (No Errors):
────────────────────────────

    moisture < min_threshold?
              │
        ┌─────┴─────┐
       YES           NO
        │             │
        v             v
    IRRIGATE    moisture > max_threshold?
                      │
                ┌─────┴─────┐
               YES           NO
                │             │
                v             v
          DO_NOT_IRRIGATE  moisture < optimal?
                                  │
                            ┌─────┴─────┐
                           YES           NO
                            │             │
                            v             v
                        IRRIGATE    DO_NOT_IRRIGATE
                      (preventive)    (maintain)
```

---

## 4. Data Flow Diagram

```
User Query: "Should we irrigate Field #12?"
    │
    v
┌─────────────────────────────────────────┐
│  IrrigationAgent.decide(field_id=12)    │
└───────────────┬─────────────────────────┘
                │
                v
┌─────────────────────────────────────────┐
│  LangGraph.invoke(initial_state)        │
└───────────────┬─────────────────────────┘
                │
                v
    Step 1: retrieve_field_data
                │
                v
┌─────────────────────────────────────────┐
│  MockDatabase.get_field_info(12)        │
│                                          │
│  Returns:                                │
│  {                                       │
│    field_id: 12,                         │
│    crop_type: TOMATO,                    │
│    min_moisture: 35.0,                   │
│    max_moisture: 60.0,                   │
│    optimal_moisture: 47.5                │
│  }                                       │
└───────────────┬─────────────────────────┘
                │
                v
    Step 2: fetch_sensor_data
                │
                v
┌─────────────────────────────────────────┐
│  MockSensorNetwork.get_soil_moisture(12)│
│                                          │
│  Attempt 1: [Network I/O]               │
│                                          │
│  20% chance → None (timeout)             │
│  5% chance → -50.0 (hardware error)      │
│  75% chance → 32.1 (valid reading)       │
│                                          │
│  Returns: 32.1                           │
└───────────────┬─────────────────────────┘
                │
                v
    Step 3: validate_and_decide
                │
                v
┌─────────────────────────────────────────┐
│  Decision Logic (Pure Comparison)       │
│                                          │
│  IF 32.1 < 35.0 (min_moisture):          │
│    decision = IRRIGATE                   │
│    reason = "Below minimum threshold"    │
│    confidence = HIGH                     │
│                                          │
└───────────────┬─────────────────────────┘
                │
                v
┌─────────────────────────────────────────┐
│  DecisionOutput (Pydantic Model)        │
│                                          │
│  {                                       │
│    "field_id": 12,                       │
│    "decision": "IRRIGATE",               │
│    "current_moisture": 32.1,             │
│    "optimal_range": [35.0, 60.0],        │
│    "reason": "Moisture 32.1% is below...",│
│    "confidence": "HIGH",                 │
│    "sensor_attempts": 1,                 │
│    "errors": []                          │
│  }                                       │
└───────────────┬─────────────────────────┘
                │
                v
    JSON Serialization (.model_dump())
                │
                v
┌─────────────────────────────────────────┐
│  Return to User / API Response          │
└─────────────────────────────────────────┘
```

---

## 5. Component Interaction Sequence

```
User          Agent         LangGraph      Database       Sensor        Validator
 │              │               │              │            │               │
 │─decide(12)──>│               │              │            │               │
 │              │─invoke()─────>│              │            │               │
 │              │               │              │            │               │
 │              │               │──get_field──>│            │               │
 │              │               │<─FieldInfo───┤            │               │
 │              │               │              │            │               │
 │              │               │──────────get_moisture────>│               │
 │              │               │<────────32.1──────────────┤               │
 │              │               │                           │               │
 │              │               │─────────────────────validate(32.1, 35-60)>│
 │              │               │<──────────IRRIGATE────────────────────────┤
 │              │               │              │            │               │
 │              │<─final_state──┤              │            │               │
 │              │               │              │            │               │
 │<─JSON────────┤               │              │            │               │
 │              │               │              │            │               │


FAILURE SCENARIO (Sensor Timeout):
───────────────────────────────────

User          Agent         LangGraph      Database       Sensor
 │              │               │              │            │
 │─decide(12)──>│               │              │            │
 │              │─invoke()─────>│              │            │
 │              │               │──get_field──>│            │
 │              │               │<─FieldInfo───┤            │
 │              │               │                           │
 │              │               │──get_moisture (attempt 1)>│
 │              │               │<─────None─────────────────┤ (timeout)
 │              │               │                           │
 │              │               │──get_moisture (attempt 2)>│
 │              │               │<─────None─────────────────┤ (timeout)
 │              │               │                           │
 │              │               │──get_moisture (attempt 3)>│
 │              │               │<─────None─────────────────┤ (timeout)
 │              │               │                           │
 │              │               │──maintenance──────────────┤
 │              │<─final_state──┤                           │
 │              │ (MAINTENANCE_REQUIRED)                    │
 │<─JSON────────┤               │                           │
 │              │               │                           │
```

---

## 6. Production Deployment Architecture (Future)

```
                          ┌──────────────────┐
                          │   Load Balancer  │
                          │   (Nginx/ALB)    │
                          └────────┬─────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                              │
                    v                              v
        ┌───────────────────┐         ┌───────────────────┐
        │  API Service 1    │         │  API Service 2    │
        │  (FastAPI)        │         │  (FastAPI)        │
        │                   │         │                   │
        │  - POST /decide   │         │  - POST /decide   │
        │  - GET /health    │         │  - GET /health    │
        └─────────┬─────────┘         └─────────┬─────────┘
                  │                             │
                  └──────────────┬──────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │                          │
                    v                          v
        ┌───────────────────┐      ┌──────────────────┐
        │   PostgreSQL      │      │  Redis Cache     │
        │   (Field Data)    │      │  (Sensor Data)   │
        │                   │      │                  │
        │  - fields         │      │  TTL: 30s        │
        │  - crops          │      │                  │
        │  - audit_log      │      │                  │
        └───────────────────┘      └──────────────────┘
                  │
                  │
                  v
        ┌───────────────────┐
        │  Monitoring       │
        │                   │
        │  - Prometheus     │
        │  - Grafana        │
        │  - Alerts         │
        └───────────────────┘
                  │
                  v
        ┌───────────────────┐
        │  Message Queue    │
        │  (RabbitMQ/Kafka) │
        │                   │
        │  - decisions      │
        │  - alerts         │
        │  - audit_events   │
        └───────────────────┘
```

---

## 7. Technology Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   LangGraph  │  │   Pydantic   │  │    Python    │  │
│  │    0.2.60    │  │    2.10.6    │  │    3.11+     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│                     Tool Layer (Mocked)                  │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ MockDatabase │  │ MockSensor   │  │  Validator   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Production Replacement (Future)             │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  PostgreSQL  │  │  IoT Sensors │  │   Business   │  │
│  │  Database    │  │  (MQTT/HTTP) │  │    Logic     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## Legend

- **→** : Data flow / Function call
- **┌─┐** : Component/Module boundary
- **[condition]** : Decision point
- **v** : Sequential flow direction
- **│** : Vertical connection
- **├─┤** : Parallel options
