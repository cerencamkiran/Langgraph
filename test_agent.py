"""
Integration-style test suite for irrigation decision agent.

Covers:
- Success case
- Field not found          → MAINTENANCE_REQUIRED + LLM still runs
- Sensor timeout + retry   → MAINTENANCE_REQUIRED + LLM still runs
- Hardware error           → MAINTENANCE_REQUIRED + LLM still runs
- Multi-field validation
- LLM fields present on success
- LLM fields present on failure
"""

from irrigation_agent import IrrigationAgent, IrrigationDecision, MockSensorNetwork


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
            self.test_llm_on_success,
            self.test_llm_on_sensor_failure,
            self.test_llm_on_field_not_found,
        ]
        for test in tests:
            try:
                test()
            except AssertionError as e:
                name = test.__name__.replace("test_", "").replace("_", " ").title()
                self.failures.append((name, str(e)))
        self.summary()

    # ------------------------------------------------------------------
    def test_normal_operation(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(
            lambda fid: {1: 28.5, 2: 45.2, 12: 32.1, 15: 35.8, 20: 55.3}.get(fid, 40.0)
        )
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] in [d.value for d in IrrigationDecision]
            assert result["current_moisture"] is not None
            assert result["optimal_range"] is not None
            self.results.append("Normal Operation")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_field_not_found(self):
        result = self.agent.decide_json(999)
        assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
        assert len(result["errors"]) > 0
        self.results.append("Field Not Found")

    # ------------------------------------------------------------------
    def test_sensor_timeout(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(lambda fid: None)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert result["sensor_attempts"] >= 3
            self.results.append("Sensor Timeout + Retry")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_hardware_error(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(lambda fid: -50.0)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert any("error" in e.lower() or "impossible" in e.lower() for e in result["errors"]), \
                f"No descriptive error. errors={result['errors']}"
            self.results.append("Hardware Error")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_multiple_fields(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(
            lambda fid: {1: 28.5, 2: 45.2, 12: 32.1, 15: 35.8, 20: 55.3}.get(fid, 40.0)
        )
        try:
            for fid in [1, 2, 12, 15, 20]:
                result = self.agent.decide_json(fid)
                assert result["decision"] in [d.value for d in IrrigationDecision]
            self.results.append("Multiple Fields")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_llm_on_success(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(lambda fid: 32.1)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] in [d.value for d in IrrigationDecision]
            self._assert_llm_fields(result, context="success path")
            self.results.append("LLM on Success")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_llm_on_sensor_failure(self):
        original = MockSensorNetwork.get_soil_moisture
        MockSensorNetwork.get_soil_moisture = staticmethod(lambda fid: None)
        try:
            result = self.agent.decide_json(12)
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            self._assert_llm_fields(result, context="sensor failure path")
            self.results.append("LLM on Sensor Failure")
        finally:
            MockSensorNetwork.get_soil_moisture = original

    # ------------------------------------------------------------------
    def test_llm_on_field_not_found(self):
        result = self.agent.decide_json(999)
        assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
        self._assert_llm_fields(result, context="field not found path")
        self.results.append("LLM on Field Not Found")

    # ------------------------------------------------------------------
    def _assert_llm_fields(self, result: dict, context: str = ""):
        prefix = f"[{context}] " if context else ""
        assert result.get("llm_consensus"), f"{prefix}llm_consensus should be non-empty"
        assert result.get("llm_recommendation"), f"{prefix}llm_recommendation should be non-empty"
        assert isinstance(result.get("llm_providers_used"), list) and result["llm_providers_used"], \
            f"{prefix}llm_providers_used should be a non-empty list"
        assert isinstance(result.get("llm_results"), list) and result["llm_results"], \
            f"{prefix}llm_results should be a non-empty list"

    # ------------------------------------------------------------------
    def summary(self):
        print("\nTest Summary")
        print("=" * 55)
        for test in self.results:
            print(f"  ✓ {test}: PASS")
        for name, err in self.failures:
            print(f"  ✗ {name}: FAIL — {err}")
        print("-" * 55)
        print(f"Passed: {len(self.results)} / {len(self.results) + len(self.failures)}")
        if self.failures:
            raise SystemExit(1)
        print("All tests passed.")


if __name__ == "__main__":
    runner = TestRunner()
    runner.run_all()
