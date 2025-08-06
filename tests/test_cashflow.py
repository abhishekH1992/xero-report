import pytest
from datetime import datetime
from app.util.report_helper import (
    calculate_date_ranges,
    filter_bank_accounts,
    format_account_number,
    format_date_range_for_excel
)


class TestCashFlowHelpers:
    """Test cases for CashFlow helper functions."""
    
    def test_calculate_date_ranges_week(self):
        """Test date range calculation for weeks."""
        date_ranges = calculate_date_ranges("2025-07-21", 2, "Week")
        
        assert len(date_ranges) == 2
        assert date_ranges[0] == ("2025-07-15", "2025-07-21")
        assert date_ranges[1] == ("2025-07-08", "2025-07-14")
    
    def test_calculate_date_ranges_month(self):
        """Test date range calculation for months."""
        date_ranges = calculate_date_ranges("2025-07-21", 2, "Month")
        
        assert len(date_ranges) == 2
        # First period should be July 1-21
        assert date_ranges[0][0] == "2025-07-01"
        assert date_ranges[0][1] == "2025-07-21"
        # Second period should be June 1-30
        assert date_ranges[1][0] == "2025-06-01"
        assert date_ranges[1][1] == "2025-06-30"
    
    def test_format_account_number(self):
        """Test account number formatting."""
        # Test 14+ digit number
        assert format_account_number("123113013054200") == "12-3113-013054-200"
        
        # Test 12 digit number
        assert format_account_number("123113013054") == "12-3113-013054"
        
        # Test 8 digit number
        assert format_account_number("12311301") == "12-3113-01"
        
        # Test short number
        assert format_account_number("123") == "123"
        
        # Test empty string
        assert format_account_number("") == ""
    
    def test_format_date_range_for_excel(self):
        """Test date range formatting for Excel."""
        formatted = format_date_range_for_excel("2025-07-21", "2025-07-15")
        assert formatted == "21'Jul 2025 - 15'Jul 2025"
        
        # Test different months
        formatted = format_date_range_for_excel("2025-07-01", "2025-06-30")
        assert formatted == "1'Jul 2025 - 30'Jun 2025"
    
    def test_filter_bank_accounts(self):
        """Test bank account filtering."""
        # Create mock account objects
        class MockAccount:
            def __init__(self, account_number, account_type, status):
                self.bank_account_number = account_number
                self.bank_account_type = account_type
                self.status = status
        
        accounts = [
            MockAccount("1234567890", "BANK", "ACTIVE"),  # ASB
            MockAccount("0123456789", "BANK", "ACTIVE"),  # ANZ
            MockAccount("0612345678", "BANK", "ACTIVE"),  # ANZ
            MockAccount("9876543210", "BANK", "ACTIVE"),  # Other
            MockAccount("1234567890", "CREDIT", "ACTIVE"),  # Wrong type
            MockAccount("1234567890", "BANK", "INACTIVE"),  # Inactive
        ]
        
        filtered = filter_bank_accounts(accounts)
        
        assert len(filtered) == 3
        assert filtered[0].bank_name == "ASB"
        assert filtered[1].bank_name == "ANZ"
        assert filtered[2].bank_name == "ANZ" 