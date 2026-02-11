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

    def run_all(self):
        self.test_normal_operation()
        self.test_field_not_found()
        self.test_sensor_timeout()
        self.test_hardware_error()
        self.test_multiple_fields()
        self.summary()

    def test_normal_operation(self):
        result = self.agent.decide_json(12)

        assert result["decision"] in [d.value for d in IrrigationDecision]
        assert result["current_moisture"] is not None
        assert result["optimal_range"] is not None

        self.results.append("Normal Operation")

    def test_field_not_found(self):
        result = self.agent.decide_json(999)

        assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
        assert len(result["errors"]) > 0

        self.results.append("Field Not Found")

    def test_sensor_timeout(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_timeout(field_id):
            return None

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_timeout)

        try:
            result = self.agent.decide_json(12)

            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert result["sensor_attempts"] >= 3

            self.results.append("Sensor Timeout + Retry")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    def test_hardware_error(self):
        original = MockSensorNetwork.get_soil_moisture

        def mock_error(field_id):
            return -50.0

        MockSensorNetwork.get_soil_moisture = staticmethod(mock_error)

        try:
            result = self.agent.decide_json(12)

            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert any("error" in e.lower() or "impossible" in e.lower()
                       for e in result["errors"])

            self.results.append("Hardware Error")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    def test_multiple_fields(self):
        fields = [1, 2, 12, 15, 20]

        for field_id in fields:
            result = self.agent.decide_json(field_id)
            assert result["decision"] in [d.value for d in IrrigationDecision]

        self.results.append("Multiple Fields")

    def summary(self):
        print("\nTest Summary")
        print("----------------")
        for test in self.results:
            print(f"{test}: PASS")
        print(f"\nTotal: {len(self.results)}")
        print("All tests passed.")


if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
