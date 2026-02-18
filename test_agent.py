"""
Integration-style test suite for irrigation decision agent.
Covers:
- Success case
- Field not found
- Sensor timeout + retry
- Hardware corruption
- Multi-field validation
"""

import random
from irrigation_agent import IrrigationAgent, IrrigationDecision, MockSensorNetwork
import json


class TestRunner:
    def __init__(self):
        self.agent = IrrigationAgent(max_sensor_retries=3)
        self.results = []
        self.failures = []

    def run_all(self):
        tests = [
            self.test_normal_operation,
            self.test_field_not_found,
            self.test_sensor_timeout,
            self.test_hardware_error,
            self.test_multiple_fields,
        ]
        for test in tests:
            try:
                test()
            except AssertionError as e:
                test_name = test.__name__.replace("test_", "").replace("_", " ").title()
                self.failures.append((test_name, str(e)))
        self.summary()

    # ------------------------------------------------------------------
    # Test: Normal Operation
    # ------------------------------------------------------------------
    def test_normal_operation(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_clean(field_id):
            # Return a deterministic, valid moisture value
            readings = {1: 28.5, 2: 45.2, 12: 32.1, 15: 35.8, 20: 55.3}
            return readings.get(field_id, 40.0)

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_clean)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] in [d.value for d in IrrigationDecision], \
                f"Unexpected decision: {result['decision']}"
            assert result["current_moisture"] is not None, \
                "current_moisture should not be None"
            assert result["optimal_range"] is not None, \
                "optimal_range should not be None"
            self.results.append("Normal Operation")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    # Test: Field Not Found
    # ------------------------------------------------------------------
    def test_field_not_found(self):
        result = self.agent.decide_json(999)
        assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value, \
            f"Expected MAINTENANCE_REQUIRED, got {result['decision']}"
        assert len(result["errors"]) > 0, \
            "errors list should not be empty for unknown field"
        self.results.append("Field Not Found")

    # ------------------------------------------------------------------
    # Test: Sensor Timeout + Retry
    # ------------------------------------------------------------------
    def test_sensor_timeout(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_timeout(field_id):
            return None

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_timeout)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value, \
                f"Expected MAINTENANCE_REQUIRED, got {result['decision']}"
            assert result["sensor_attempts"] >= 3, \
                f"Expected >= 3 attempts, got {result['sensor_attempts']}"
            self.results.append("Sensor Timeout + Retry")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    # Test: Hardware Error (impossible sensor value)
    # ------------------------------------------------------------------
    def test_hardware_error(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_error(field_id):
            return -50.0

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_error)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value, \
                f"Expected MAINTENANCE_REQUIRED, got {result['decision']}"
            assert len(result["errors"]) > 0, \
                "errors list should not be empty for hardware error"
            assert any(
                "error" in e.lower() or "impossible" in e.lower()
                for e in result["errors"]
            ), f"No descriptive error message found. errors={result['errors']}"
            self.results.append("Hardware Error")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    # Test: Multiple Fields
    # ------------------------------------------------------------------
    def test_multiple_fields(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_clean(field_id):
            readings = {1: 28.5, 2: 45.2, 12: 32.1, 15: 35.8, 20: 55.3}
            return readings.get(field_id, 40.0)

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_clean)
        try:
            fields = [1, 2, 12, 15, 20]
            for field_id in fields:
                result = self.agent.decide_json(field_id)
                assert result["decision"] in [d.value for d in IrrigationDecision], \
                    f"Field {field_id}: unexpected decision {result['decision']}"
            self.results.append("Multiple Fields")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def summary(self):
        print("\nTest Summary")
        print("----------------")
        for test in self.results:
            print(f"  ✓ {test}: PASS")
        for name, err in self.failures:
            print(f"  ✗ {name}: FAIL — {err}")
        print(f"\nPassed: {len(self.results)} / {len(self.results) + len(self.failures)}")
        if self.failures:
            raise SystemExit(1)
        print("All tests passed.")


if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
