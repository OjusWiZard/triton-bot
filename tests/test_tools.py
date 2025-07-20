"""Tests for triton.tools module"""
import pytest
from triton.tools import escape_markdown_v2, wei_to_unit, wei_to_olas, str_to_bool


class TestEscapeMarkdownV2:
    """Tests for escape_markdown_v2 function"""
    
    def test_escape_special_characters(self):
        """Test escaping of special markdown characters"""
        special_chars = r"*_[]()~`>#+=|{}.!\\"
        for char in special_chars:
            result = escape_markdown_v2(char)
            assert result == f"\\{char}"
    
    def test_escape_normal_text(self):
        """Test that normal text is not escaped"""
        text = "normal text"
        result = escape_markdown_v2(text)
        assert result == text
    
    def test_escape_mixed_text(self):
        """Test escaping of mixed text with special characters"""
        text = "Hello *world* [link](url)"
        expected = "Hello \\*world\\* \\[link\\]\\(url\\)"
        result = escape_markdown_v2(text)
        assert result == expected
    
    def test_escape_empty_string(self):
        """Test escaping of empty string"""
        result = escape_markdown_v2("")
        assert result == ""


class TestWeiToUnit:
    """Tests for wei_to_unit function"""
    
    def test_wei_to_unit_conversion(self):
        """Test basic wei to unit conversion"""
        wei = 1000000000000000000  # 1 ETH in wei
        result = wei_to_unit(wei)
        assert result == 1.0
    
    def test_wei_to_unit_zero(self):
        """Test conversion of zero wei"""
        result = wei_to_unit(0)
        assert result == 0.0
    
    def test_wei_to_unit_small_amount(self):
        """Test conversion of small wei amount"""
        wei = 1000000000000000  # 0.001 ETH
        result = wei_to_unit(wei)
        assert result == 0.001
    
    def test_wei_to_unit_large_amount(self):
        """Test conversion of large wei amount"""
        wei = 1000000000000000000000  # 1000 ETH
        result = wei_to_unit(wei)
        assert result == 1000.0


class TestWeiToOlas:
    """Tests for wei_to_olas function"""
    
    def test_wei_to_olas_formatting(self):
        """Test wei to OLAS formatting"""
        wei = 1000000000000000000  # 1 OLAS
        result = wei_to_olas(wei)
        assert result == "1.00 OLAS"
    
    def test_wei_to_olas_zero(self):
        """Test formatting of zero OLAS"""
        result = wei_to_olas(0)
        assert result == "0.00 OLAS"
    
    def test_wei_to_olas_decimal(self):
        """Test formatting of decimal OLAS"""
        wei = 1500000000000000000  # 1.5 OLAS
        result = wei_to_olas(wei)
        assert result == "1.50 OLAS"
    
    def test_wei_to_olas_rounding(self):
        """Test rounding in OLAS formatting"""
        wei = 1234567890123456789  # ~1.23 OLAS
        result = wei_to_olas(wei)
        assert result == "1.23 OLAS"


class TestStrToBool:
    """Tests for str_to_bool function"""
    
    def test_str_to_bool_true_values(self):
        """Test true values conversion"""
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]
        for value in true_values:
            result = str_to_bool(value)
            assert result is True
    
    def test_str_to_bool_false_values(self):
        """Test false values conversion"""
        false_values = ["false", "False", "FALSE", "0", "no", "No", "NO", "random"]
        for value in false_values:
            result = str_to_bool(value)
            assert result is False
    
    def test_str_to_bool_empty_string(self):
        """Test empty string conversion"""
        result = str_to_bool("")
        assert result is False
    
    def test_str_to_bool_none(self):
        """Test None conversion"""
        result = str_to_bool(None)
        assert result is False