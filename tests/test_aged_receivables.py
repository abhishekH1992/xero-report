import datetime
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.util.report_helper import process_financial_item, generate_bucket_names, calculate_aging_bucket

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

def test_calculate_aging_bucket_periods():
    """Test that calculate_aging_bucket works correctly with different periods values"""
    report_date = datetime.date(2024, 6, 30)
    
    # Test with periods=4 (should have 4 buckets: < 1 Month, 1 Month, 2 Months, 3 Months)
    due_date_1_month = datetime.date(2024, 5, 30)  # 1 month ago
    due_date_2_months = datetime.date(2024, 4, 30)  # 2 months ago
    due_date_3_months = datetime.date(2024, 3, 30)  # 3 months ago
    due_date_4_months = datetime.date(2024, 2, 29)  # 4 months ago
    due_date_5_months = datetime.date(2024, 1, 30)  # 5 months ago
    
    # Test periods=4
    assert calculate_aging_bucket(report_date, due_date_1_month, 4, 1, "Month") == "1 Month"
    assert calculate_aging_bucket(report_date, due_date_2_months, 4, 1, "Month") == "2 Months"
    assert calculate_aging_bucket(report_date, due_date_3_months, 4, 1, "Month") == "3 Months"
    assert calculate_aging_bucket(report_date, due_date_4_months, 4, 1, "Month") == "Older"
    assert calculate_aging_bucket(report_date, due_date_5_months, 4, 1, "Month") == "Older"
    
    # Test periods=3 (should have 3 buckets: < 1 Month, 1 Month, 2 Months)
    assert calculate_aging_bucket(report_date, due_date_1_month, 3, 1, "Month") == "1 Month"
    assert calculate_aging_bucket(report_date, due_date_2_months, 3, 1, "Month") == "2 Months"
    assert calculate_aging_bucket(report_date, due_date_3_months, 3, 1, "Month") == "Older"
    assert calculate_aging_bucket(report_date, due_date_4_months, 3, 1, "Month") == "Older"
    assert calculate_aging_bucket(report_date, due_date_5_months, 3, 1, "Month") == "Older"

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
    assert "failed_connections" in data
    assert "connection_summary" in data
    
    # Check connection summary structure
    connection_summary = data["connection_summary"]
    assert "total_connections_attempted" in connection_summary
    assert "successful_connections" in connection_summary
    assert "failed_connections_count" in connection_summary
    assert "success_rate" in connection_summary
    
    # Verify failed_connections is a list
    assert isinstance(data["failed_connections"], list)

def test_aged_receivables_with_failed_connections(api_key):
    """Test that failed connections are properly tracked when invalid connection IDs are provided"""
    response = client.get(
        "/api/v1/reports/aged-receivables?connection_id=invalid_id_1,invalid_id_2",
        headers={"X-API-Key": api_key}
    )
    
    # Should still return 200 even with failed connections
    assert response.status_code == 200
    data = response.json()
    
    # Check that failed connections are tracked
    assert "failed_connections" in data
    assert "connection_summary" in data
    
    failed_connections = data["failed_connections"]
    connection_summary = data["connection_summary"]
    
    # Should have 2 failed connections
    assert len(failed_connections) == 2
    assert connection_summary["failed_connections_count"] == 2
    assert connection_summary["total_connections_attempted"] == 2
    assert connection_summary["successful_connections"] == 0
    assert connection_summary["success_rate"] == "0%"
    
    # Check structure of failed connection entries
    for failed_conn in failed_connections:
        assert "connection_id" in failed_conn
        assert "tenant_id" in failed_conn
        assert "tenant_name" in failed_conn
        assert "app_id" in failed_conn
        assert "error" in failed_conn
        assert "error_details" in failed_conn

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