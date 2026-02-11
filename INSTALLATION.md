# Installation & Setup Guide

## Prerequisites

- Python 3.11 or higher
- pip 24.0 or higher
- Git
- Internet connection (for dependency installation)

---

## Quick Start Guide

### 1. Clone the Repository

```bash
# Create a private repository on GitHub
# Invite collaborators: adelibasi, muratonnet

# Clone locally
git clone <your-repository-url>
cd topraq-irrigation-agent
```

### 2. Set Up Python Virtual Environment (Recommended)

```bash
# Create virtual environment
python3 -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate
```

### 3. Install Dependencies

```bash
# Install all required packages
pip install -r requirements.txt
```

This will install:
- `langgraph==0.2.60` - State graph orchestration
- `langchain-core==0.3.36` - Core LangChain components
- `pydantic==2.10.6` - Data validation
- `typing-extensions==4.12.2` - Type hints support

### 4. Verify Installation

```bash
# Check Python version
python --version
# Should output: Python 3.11.x or higher

# Check installed packages
pip list | grep -E "langgraph|pydantic"
# Should show the installed versions
```

---

## Running the Agent

### Basic Usage

```bash
# Run for Field #12 (default)
python irrigation_agent.py

# Run for specific field
python irrigation_agent.py 12
python irrigation_agent.py 1
python irrigation_agent.py 999  # Non-existent field
```

### Expected Output

```
############################################################
# IRRIGATION AGENT STARTED
# Query: Should we irrigate Field #12?
############################################################

============================================================
STAGE 1: Retrieving Field Data
============================================================
[DB] Querying field info for Field #12
[DB] ✓ Found: tomato (optimal: 47.5%)

============================================================
STAGE 2: Fetching Sensor Data (Attempt 1)
============================================================
[SENSOR] Reading moisture for Field #12...
[SENSOR] ✓ Moisture: 32.1%

============================================================
STAGE 3: Validation & Decision Logic
============================================================
[LOGIC] Current Moisture: 32.1%
[LOGIC] Optimal Range: 35.0% - 60.0%
[LOGIC] Optimal Point: 47.5%
[DECISION] IRRIGATE
[REASON] Moisture 32.1% is below minimum threshold 35.0%

############################################################
# FINAL DECISION
############################################################
Field ID: 12
Decision: IRRIGATE
Current Moisture: 32.1%
Optimal Range: (35.0, 60.0)
Reason: Moisture 32.1% is below minimum threshold 35.0%
Sensor Attempts: 1
############################################################

============================================================
JSON OUTPUT:
============================================================
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

---

## Running Tests

### Automated Test Suite

```bash
# Run all tests
python test_agent.py
```

This will execute:
1. ✓ Normal operation test
2. ✓ Field not found test
3. ✓ Sensor timeout with retry test
4. ✓ Hardware error test
5. ✓ Multiple fields test

Expected output:
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

### Interactive Demo

```bash
# Run interactive demonstration
python test_agent.py --interactive
```

This will walk you through:
- Demo 1: Dry field needs irrigation
- Demo 2: Well-watered field
- Demo 3: Invalid field handling

---

## Using Jupyter Notebook

### Start Jupyter

```bash
# Install Jupyter if not already installed
pip install jupyter

# Launch Jupyter
jupyter notebook
```

### Open Demo Notebook

1. Navigate to `demo_notebook.ipynb`
2. Run all cells to see:
   - Setup and initialization
   - Normal operation demo
   - Field not found handling
   - Sensor timeout with retry
   - Hardware error detection
   - Multiple fields comparison

---

## Project Structure

```
topraq-irrigation-agent/
├── irrigation_agent.py        # Main agent implementation
├── test_agent.py              # Comprehensive test suite
├── demo_notebook.ipynb        # Interactive Jupyter demo
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
├── ARCHITECTURE.md            # Architecture diagrams
├── EXAMPLE_OUTPUT.txt         # Sample outputs
├── .gitignore                # Git ignore rules
└── venv/                     # Virtual environment (created by you)
```

---

## Configuration Options

### Customizing Retry Behavior

```python
# In your code
from irrigation_agent import IrrigationAgent

# Default: 3 retries
agent = IrrigationAgent(max_sensor_retries=3)

# More aggressive: 5 retries
agent = IrrigationAgent(max_sensor_retries=5)

# Conservative: 1 retry only
agent = IrrigationAgent(max_sensor_retries=1)
```

### Adding New Fields

Edit `irrigation_agent.py` and modify the `MockDatabase.FIELDS` dictionary:

```python
class MockDatabase:
    FIELDS = {
        # ... existing fields ...
        
        # Add your new field
        99: {
            "crop_type": CropType.WHEAT,
            "min_moisture": 25.0,
            "max_moisture": 45.0,
            "optimal_moisture": 35.0,
            "soil_type": "loamy"
        }
    }
```

Also add to `MockSensorNetwork.CURRENT_READINGS`:

```python
class MockSensorNetwork:
    CURRENT_READINGS = {
        # ... existing readings ...
        
        99: 42.5  # Current moisture %
    }
```

### Adding New Crop Types

Edit the `CropType` enum in `irrigation_agent.py`:

```python
class CropType(str, Enum):
    WHEAT = "wheat"
    CORN = "corn"
    TOMATO = "tomato"
    COTTON = "cotton"
    POTATO = "potato"
    BARLEY = "barley"  # NEW
    RICE = "rice"      # NEW
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'langgraph'"

**Solution:**
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # or .\venv\Scripts\activate on Windows

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: "Python version too old"

**Solution:**
```bash
# Check Python version
python --version

# If < 3.11, install newer Python
# Then create venv with newer version
python3.11 -m venv venv
```

### Issue: Tests failing intermittently

**Solution:**
This is expected! The mock sensors have built-in randomness (20% timeout rate, 5% hardware error rate). Run tests multiple times to see different scenarios:

```bash
# Run tests 3 times
for i in {1..3}; do python test_agent.py; done
```

### Issue: Import errors in Jupyter notebook

**Solution:**
```bash
# Install Jupyter in the same virtual environment
source venv/bin/activate
pip install jupyter ipykernel

# Register kernel
python -m ipykernel install --user --name=topraq-agent

# Launch Jupyter and select "topraq-agent" kernel
jupyter notebook
```

---

## Development Workflow

### 1. Make Changes

```bash
# Edit files
vim irrigation_agent.py
# or use your preferred editor
```

### 2. Run Tests

```bash
# Verify changes don't break existing functionality
python test_agent.py
```

### 3. Test Manually

```bash
# Test specific scenarios
python irrigation_agent.py 12
python irrigation_agent.py 999
```

### 4. Commit Changes

```bash
git add .
git commit -m "Add new feature: ..."
git push origin main
```

---

## Production Deployment Checklist

When moving from mock to production:

- [ ] Replace `MockDatabase` with PostgreSQL connection
- [ ] Replace `MockSensorNetwork` with real IoT sensor APIs
- [ ] Add authentication/authorization
- [ ] Implement rate limiting
- [ ] Add comprehensive logging (structured JSON logs)
- [ ] Set up monitoring (Prometheus + Grafana)
- [ ] Configure alerting (PagerDuty, Slack)
- [ ] Add audit trail (immutable decision log)
- [ ] Implement caching (Redis for sensor readings)
- [ ] Add API endpoints (FastAPI or Flask)
- [ ] Set up CI/CD pipeline
- [ ] Write integration tests
- [ ] Load testing
- [ ] Security audit
- [ ] Documentation for operations team

---

## Getting Help

### Documentation

- **README.md**: Project overview and architecture
- **ARCHITECTURE.md**: Detailed diagrams and design decisions
- **EXAMPLE_OUTPUT.txt**: Sample outputs for reference
- **demo_notebook.ipynb**: Interactive examples

### Code Comments

The code is heavily commented. Look for:
- `"""Docstrings"""` for function/class documentation
- `# Inline comments` for complex logic
- Type hints for parameter/return types

### Debugging

Enable verbose logging:

```python
# Add to irrigation_agent.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

Visualize the LangGraph (requires graphviz):

```python
# In Python shell
from irrigation_agent import build_irrigation_agent
graph = build_irrigation_agent()

# Export graph visualization
from langgraph.graph import visualize
visualize(graph)  # Opens in browser
```

---

## Submission Checklist

Before submitting:

- [ ] Code runs without errors
- [ ] All tests pass
- [ ] README.md is complete
- [ ] Architecture documentation included
- [ ] Example outputs provided
- [ ] .gitignore configured
- [ ] requirements.txt up to date
- [ ] Repository is private
- [ ] Collaborators invited (adelibasi, muratonnet)
- [ ] Code is well-commented
- [ ] No hardcoded credentials
- [ ] Type hints present
- [ ] Pydantic models for data validation

---

## Timeline

**Deadline:** February 17, 2026, 17:00 TSI

Recommended schedule:
- Day 1-2: Setup, implementation, basic testing
- Day 3-4: Advanced testing, error handling, documentation
- Day 5: Final review, polish, submission

---

## Contact

For questions or issues:
- GitHub Issues: Create an issue in the repository
- Email: [Your contact email]

---

**Good luck! 🚀**
