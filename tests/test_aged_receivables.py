import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.util.report_helper import process_financial_item, generate_bucket_names

client = TestClient(app)

# --- UNIT TEST ---
def test_aged_receivables_unit():
    report = {}
    bucket_names = generate_bucket_names(4, "Month")
    
    # Create a mock invoice object
    fake_invoice = type("Invoice", (), {
        "contact": type("Contact", (), {"name": "Test Customer"})(),
        "due_date": datetime.date(2024, 6, 1),
        "amount_due": 1000
    })()
    
    report_date = datetime.date(2024, 6, 30)
    
    process_financial_item(
        item=fake_invoice,
        report_date=report_date,
        periods=4,
        period_of=1,
        period_type="Month",
        bucket_names=bucket_names,
        report=report,
        amount_field="amount_due",
        date_field="due_date",
        is_negative=False,
        connection_name="Test Company",
        business_type="Test Unit"
    )
    
    # Verify the result
    key = "Test Unit|Test Company|Test Customer"
    assert key in report
    assert report[key]["< 1 Month"] == 1000
    assert report[key]["business_unit"] == "Test Unit"
    assert report[key]["company"] == "Test Company"
    assert report[key]["contact"] == "Test Customer"

# --- INTEGRATION TEST ---
@pytest.fixture
def api_key():
    if not settings.api_key_list:
        pytest.skip("No API keys configured")
    return settings.api_key_list[0]

def test_aged_receivables_integration(api_key):
    response = client.get(
        "/api/v1/reports/aged-receivables",
        headers={"X-API-Key": api_key}
    )
    
    # Check response structure
    assert response.status_code == 200
    data = response.json()
    assert "aged_receivables" in data
    assert "excel_file" in data
    assert "aging_config" in data
    assert "generated_at" in data
    assert "total_invoices" in data

def test_aged_receivables_unauthorized():
    response = client.get("/api/v1/reports/aged-receivables")
    assert response.status_code == 401
    assert "Invalid or missing API Key" in response.text 

def test_aged_receivables_invalid_api_key():
    response = client.get(
        "/api/v1/reports/aged-receivables",
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401
    assert "Invalid or missing API Key" in response.text 