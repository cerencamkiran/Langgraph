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

All decisions rely strictly on tool outputs.\
No values are inferred or guessed.

------------------------------------------------------------------------

## Architecture

The system uses LangGraph to manage state transitions.

Execution flow:

Retrieve Field Data ↓ Fetch Sensor Data ↓ Validate Reading ↓ Decision or
Safe Fallback

Each step updates a typed state object carried through the graph.

------------------------------------------------------------------------

## Failure Handling

The agent handles the following scenarios:

-   Field not found\
-   Sensor timeout (with retry)\
-   Invalid sensor values

If reliable data cannot be obtained, the agent returns:

MAINTENANCE_REQUIRED

The system fails closed to avoid unsafe actions.

------------------------------------------------------------------------

## Decision Logic

The moisture value is compared against the field's defined range.

-   Below minimum → IRRIGATE\
-   Above maximum → DO_NOT_IRRIGATE\
-   Within range → Deterministic rule toward optimal level

The same inputs always produce the same result.

------------------------------------------------------------------------

## Installation

pip install -r requirements.txt

Python 3.11+ recommended.

------------------------------------------------------------------------

## Usage

Run from the command line:

python irrigation_agent.py 12

------------------------------------------------------------------------

## Test Scenarios

1.  Normal operation → IRRIGATE or DO_NOT_IRRIGATE\
2.  Field not found → MAINTENANCE_REQUIRED\
3.  Sensor timeout (max retries) → MAINTENANCE_REQUIRED\
4.  Hardware error → MAINTENANCE_REQUIRED\
5.  Multiple fields → All processed without failure

------------------------------------------------------------------------

## Test Results

## TEST SUMMARY

Normal Operation: PASS Field Not Found: PASS Sensor Timeout + Retry:
PASS Hardware Error: PASS Multiple Fields: PASS

Total: 5 Passed: 5 Failed: 0

Run tests with:

python test_agent.py

------------------------------------------------------------------------

## Agent Output Format

{ "field_id": 12, "decision": "IRRIGATE", "current_moisture": 32.1,
"optimal_range": \[35.0, 60.0\], "reason": "Moisture 32.1% is below
minimum threshold 35.0%", "confidence": "HIGH", "sensor_attempts": 1,
"errors": \[\] }

------------------------------------------------------------------------

## Notes

The tool layer is mocked for demonstration purposes.\
The orchestration layer can be reused with real databases and sensor
integrations.
