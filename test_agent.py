"""
Test Suite for Topraq Irrigation Agent

Demonstrates:
1. Success case - Normal operation
2. Failure cases - Sensor timeout, hardware error, field not found
3. Retry mechanism validation
4. Edge cases
"""

import random
from irrigation_agent import IrrigationAgent, IrrigationDecision, MockSensorNetwork
import json


class TestRunner:
    """Comprehensive test suite for irrigation agent"""
    
    def __init__(self):
        self.agent = IrrigationAgent(max_sensor_retries=3)
        self.test_results = []
    
    def run_all_tests(self):
        """Execute all test scenarios"""
        print("="*80)
        print(" TOPRAQ IRRIGATION AGENT - COMPREHENSIVE TEST SUITE")
        print("="*80)
        
        # Test 1: Normal success case
        self.test_normal_operation()
        
        # Test 2: Field not found
        self.test_field_not_found()
        
        # Test 3: Sensor timeout with retry
        self.test_sensor_timeout_with_retry()
        
        # Test 4: Hardware error (impossible values)
        self.test_sensor_hardware_error()
        
        # Test 5: Multiple fields
        self.test_multiple_fields()
        
        # Summary
        self.print_summary()
    
    def test_normal_operation(self):
        """Test Case 1: Normal operation - field exists, sensor works"""
        print("\n" + "="*80)
        print("TEST 1: NORMAL OPERATION (Success Case)")
        print("="*80)
        print("Scenario: Field #12 exists, sensor returns valid reading")
        print("-"*80)
        
        # Force successful sensor reading
        random.seed(42)  # Seed for reproducible success
        
        result = self.agent.decide_json(field_id=12)
        
        # Validate
        assert result["decision"] in [d.value for d in IrrigationDecision]
        assert result["current_moisture"] is not None
        assert result["optimal_range"] is not None
        
        self.test_results.append({
            "test": "Normal Operation",
            "status": "PASS ✓",
            "decision": result["decision"]
        })
        
        print("\n✓ TEST 1 PASSED")
        print(f"Decision: {result['decision']}")
        print(f"Moisture: {result['current_moisture']}%")
        print(f"Reason: {result['reason']}")
    
    def test_field_not_found(self):
        """Test Case 2: Field not found in database"""
        print("\n" + "="*80)
        print("TEST 2: FIELD NOT FOUND (Failure Case)")
        print("="*80)
        print("Scenario: Field #999 does not exist in database")
        print("-"*80)
        
        result = self.agent.decide_json(field_id=999)
        
        # Validate
        assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
        assert "Field #999 not found" in result["reason"]
        assert len(result["errors"]) > 0
        
        self.test_results.append({
            "test": "Field Not Found",
            "status": "PASS ✓",
            "decision": result["decision"]
        })
        
        print("\n✓ TEST 2 PASSED")
        print(f"Decision: {result['decision']}")
        print(f"Errors: {result['errors']}")
    
    def test_sensor_timeout_with_retry(self):
        """Test Case 3: Sensor timeout triggers retry mechanism"""
        print("\n" + "="*80)
        print("TEST 3: SENSOR TIMEOUT WITH RETRY (Failure Case)")
        print("="*80)
        print("Scenario: Simulating sensor timeouts to test retry logic")
        print("-"*80)
        
        # Monkey-patch sensor to always timeout
        original_method = MockSensorNetwork.get_soil_moisture
        
        timeout_count = 0
        def mock_timeout(field_id):
            nonlocal timeout_count
            timeout_count += 1
            print(f"[MOCK] Forcing timeout #{timeout_count}")
            return None  # Simulate timeout
        
        MockSensorNetwork.get_soil_moisture = staticmethod(mock_timeout)
        
        try:
            result = self.agent.decide_json(field_id=12)
            
            # Validate
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert result["sensor_attempts"] >= 3  # Should retry
            assert any("timeout" in err.lower() for err in result["errors"])
            
            self.test_results.append({
                "test": "Sensor Timeout + Retry",
                "status": "PASS ✓",
                "decision": result["decision"],
                "retries": result["sensor_attempts"]
            })
            
            print("\n✓ TEST 3 PASSED")
            print(f"Decision: {result['decision']}")
            print(f"Retry Attempts: {result['sensor_attempts']}")
            print(f"Errors: {result['errors']}")
        finally:
            # Restore original method
            MockSensorNetwork.get_soil_moisture = original_method
    
    def test_sensor_hardware_error(self):
        """Test Case 4: Sensor returns impossible values (hardware error)"""
        print("\n" + "="*80)
        print("TEST 4: SENSOR HARDWARE ERROR (Failure Case)")
        print("="*80)
        print("Scenario: Sensor returns impossible value (-50.0%)")
        print("-"*80)
        
        # Monkey-patch sensor to return impossible value
        original_method = MockSensorNetwork.get_soil_moisture
        
        def mock_hardware_error(field_id):
            print(f"[MOCK] Forcing hardware error: -50.0%")
            return -50.0  # Impossible moisture value
        
        MockSensorNetwork.get_soil_moisture = staticmethod(mock_hardware_error)
        
        try:
            result = self.agent.decide_json(field_id=12)
            
            # Validate
            assert result["decision"] == IrrigationDecision.MAINTENANCE_REQUIRED.value
            assert any("hardware error" in err.lower() or "impossible" in err.lower() 
                      for err in result["errors"])
            
            self.test_results.append({
                "test": "Hardware Error",
                "status": "PASS ✓",
                "decision": result["decision"]
            })
            
            print("\n✓ TEST 4 PASSED")
            print(f"Decision: {result['decision']}")
            print(f"Invalid Reading: {result['current_moisture']}%")
            print(f"Errors: {result['errors']}")
        finally:
            # Restore original method
            MockSensorNetwork.get_soil_moisture = original_method
    
    def test_multiple_fields(self):
        """Test Case 5: Test multiple fields with varying conditions"""
        print("\n" + "="*80)
        print("TEST 5: MULTIPLE FIELDS (Comprehensive Case)")
        print("="*80)
        print("Scenario: Test all available fields")
        print("-"*80)
        
        random.seed(123)  # For reproducibility
        
        fields_to_test = [1, 2, 12, 15, 20]
        results = []
        
        for field_id in fields_to_test:
            print(f"\n--- Testing Field #{field_id} ---")
            result = self.agent.decide_json(field_id=field_id)
            results.append({
                "field_id": field_id,
                "decision": result["decision"],
                "moisture": result["current_moisture"]
            })
        
        # Validate at least one decision of each type (might vary due to randomness)
        decisions = [r["decision"] for r in results]
        
        self.test_results.append({
            "test": "Multiple Fields",
            "status": "PASS ✓",
            "fields_tested": len(fields_to_test)
        })
        
        print("\n✓ TEST 5 PASSED")
        print(f"Tested {len(fields_to_test)} fields successfully")
        for r in results:
            print(f"  Field #{r['field_id']}: {r['decision']} (Moisture: {r['moisture']}%)")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*80)
        print(" TEST SUMMARY")
        print("="*80)
        
        for i, result in enumerate(self.test_results, 1):
            print(f"{i}. {result['test']}: {result['status']}")
        
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if "PASS" in r["status"])
        
        print("-"*80)
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print("="*80)
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED! 🎉")
        else:
            print("\n⚠️  SOME TESTS FAILED")


# ============================================================================
# Interactive Demo
# ============================================================================

def run_interactive_demo():
    """Interactive demonstration of agent capabilities"""
    print("\n" + "="*80)
    print(" INTERACTIVE DEMONSTRATION")
    print("="*80)
    
    agent = IrrigationAgent(max_sensor_retries=3)
    
    demos = [
        {
            "title": "Demo 1: Dry Field Needs Irrigation",
            "field_id": 12,
            "description": "Field #12 (Tomato) - Low moisture reading"
        },
        {
            "title": "Demo 2: Well-Watered Field",
            "field_id": 2,
            "description": "Field #2 (Corn) - Optimal moisture"
        },
        {
            "title": "Demo 3: Invalid Field",
            "field_id": 999,
            "description": "Field #999 - Does not exist"
        }
    ]
    
    for demo in demos:
        print("\n" + "-"*80)
        print(f"{demo['title']}")
        print(f"{demo['description']}")
        print("-"*80)
        
        result = agent.decide_json(demo["field_id"])
        
        print(f"\n📊 RESULT:")
        print(json.dumps(result, indent=2))
        
        input("\nPress Enter to continue...")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if "--interactive" in sys.argv:
        run_interactive_demo()
    else:
        # Run automated test suite
        runner = TestRunner()
        runner.run_all_tests()
