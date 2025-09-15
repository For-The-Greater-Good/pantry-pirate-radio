"""Tests for state name to code mapping utilities."""

import pytest
from app.core.state_mapping import (
    normalize_state_to_code,
    is_valid_state_code,
    VALID_STATE_CODES,
    STATE_NAME_TO_CODE,
)


class TestNormalizeStateToCode:
    """Test normalize_state_to_code function."""

    def test_empty_input(self):
        """Test with empty or None input."""
        assert normalize_state_to_code(None) == ""
        assert normalize_state_to_code("") == ""
        assert normalize_state_to_code("   ") == ""

    def test_valid_state_codes(self):
        """Test with already valid 2-letter state codes."""
        assert normalize_state_to_code("CA") == "CA"
        assert normalize_state_to_code("ny") == "NY"
        assert normalize_state_to_code("Tx") == "TX"
        assert normalize_state_to_code(" FL ") == "FL"

    def test_full_state_names(self):
        """Test with full state names."""
        assert normalize_state_to_code("California") == "CA"
        assert normalize_state_to_code("TEXAS") == "TX"
        assert normalize_state_to_code("new york") == "NY"
        assert normalize_state_to_code("florida") == "FL"
        assert normalize_state_to_code("ILLINOIS") == "IL"

    def test_multi_word_states(self):
        """Test with multi-word state names."""
        assert normalize_state_to_code("New York") == "NY"
        assert normalize_state_to_code("NEW JERSEY") == "NJ"
        assert normalize_state_to_code("north carolina") == "NC"
        assert normalize_state_to_code("SOUTH DAKOTA") == "SD"
        assert normalize_state_to_code("West Virginia") == "WV"
        assert normalize_state_to_code("Rhode Island") == "RI"
        assert normalize_state_to_code("New Mexico") == "NM"
        assert normalize_state_to_code("New Hampshire") == "NH"
        assert normalize_state_to_code("North Dakota") == "ND"
        assert normalize_state_to_code("South Carolina") == "SC"

    def test_district_of_columbia_variations(self):
        """Test various DC representations."""
        assert normalize_state_to_code("District of Columbia") == "DC"
        assert normalize_state_to_code("WASHINGTON DC") == "DC"
        assert normalize_state_to_code("Washington D.C.") == "DC"
        assert normalize_state_to_code("D.C.") == "DC"
        assert normalize_state_to_code("DC") == "DC"

    def test_territories(self):
        """Test US territories."""
        assert normalize_state_to_code("Puerto Rico") == "PR"
        assert normalize_state_to_code("Virgin Islands") == "VI"
        assert normalize_state_to_code("US Virgin Islands") == "VI"
        assert normalize_state_to_code("U.S. Virgin Islands") == "VI"
        assert normalize_state_to_code("Guam") == "GU"
        assert normalize_state_to_code("American Samoa") == "AS"
        assert normalize_state_to_code("Northern Mariana Islands") == "MP"

    def test_abbreviations_with_periods(self):
        """Test abbreviations with periods."""
        assert normalize_state_to_code("D.C.") == "DC"
        assert normalize_state_to_code("U.S. Virgin Islands") == "VI"

    def test_partial_multi_word_states(self):
        """Test partial multi-word state names."""
        # These should work if the prefix is recognized
        assert normalize_state_to_code("New") == ""  # Ambiguous
        assert normalize_state_to_code("North") == ""  # Ambiguous
        assert normalize_state_to_code("South") == ""  # Ambiguous

    def test_invalid_inputs(self):
        """Test with invalid state names."""
        assert normalize_state_to_code("NotAState") == ""
        assert normalize_state_to_code("XX") == ""
        assert normalize_state_to_code("123") == ""
        assert normalize_state_to_code("Canada") == ""
        assert normalize_state_to_code("United Kingdom") == ""

    def test_case_insensitivity(self):
        """Test case insensitivity."""
        assert normalize_state_to_code("california") == "CA"
        assert normalize_state_to_code("CALIFORNIA") == "CA"
        assert normalize_state_to_code("CaLiFoRnIa") == "CA"
        assert normalize_state_to_code("ca") == "CA"
        assert normalize_state_to_code("CA") == "CA"
        assert normalize_state_to_code("Ca") == "CA"

    def test_whitespace_handling(self):
        """Test handling of extra whitespace."""
        assert normalize_state_to_code("  California  ") == "CA"
        assert normalize_state_to_code("\tNew York\n") == "NY"
        assert normalize_state_to_code("  CA  ") == "CA"

    def test_all_states_covered(self):
        """Test that all states in mapping are valid."""
        for state_name, expected_code in STATE_NAME_TO_CODE.items():
            assert normalize_state_to_code(state_name) == expected_code
            assert expected_code in VALID_STATE_CODES

    def test_all_valid_codes_work(self):
        """Test that all valid state codes return themselves."""
        for state_code in VALID_STATE_CODES:
            assert normalize_state_to_code(state_code) == state_code
            assert normalize_state_to_code(state_code.lower()) == state_code


class TestIsValidStateCode:
    """Test is_valid_state_code function."""

    def test_valid_state_codes(self):
        """Test with valid state codes."""
        assert is_valid_state_code("CA")
        assert is_valid_state_code("NY")
        assert is_valid_state_code("TX")
        assert is_valid_state_code("FL")
        assert is_valid_state_code("DC")
        assert is_valid_state_code("PR")
        assert is_valid_state_code("VI")

    def test_lowercase_state_codes(self):
        """Test that lowercase codes are accepted."""
        assert is_valid_state_code("ca")
        assert is_valid_state_code("ny")
        assert is_valid_state_code("tx")

    def test_invalid_state_codes(self):
        """Test with invalid state codes."""
        assert not is_valid_state_code("XX")
        assert not is_valid_state_code("ZZ")
        assert not is_valid_state_code("12")
        assert not is_valid_state_code("")
        assert not is_valid_state_code("ABC")
        assert not is_valid_state_code("CAL")

    def test_full_state_names(self):
        """Test that full state names are not valid codes."""
        assert not is_valid_state_code("California")
        assert not is_valid_state_code("New York")
        assert not is_valid_state_code("Texas")

    def test_all_valid_codes(self):
        """Test all codes in VALID_STATE_CODES."""
        for code in VALID_STATE_CODES:
            assert is_valid_state_code(code)
            assert is_valid_state_code(code.lower())

    def test_mixed_case(self):
        """Test mixed case state codes."""
        assert is_valid_state_code("Ca")
        assert is_valid_state_code("nY")
        assert is_valid_state_code("Tx")


class TestStateMappingDataIntegrity:
    """Test the integrity of the state mapping data structures."""

    def test_all_state_codes_are_two_letters(self):
        """Test that all state codes are exactly 2 letters."""
        for code in VALID_STATE_CODES:
            assert len(code) == 2
            assert code.isalpha()
            assert code.isupper()

    def test_no_duplicate_state_names(self):
        """Test that there are no duplicate state names in mapping."""
        seen_codes = set()
        for state_name, state_code in STATE_NAME_TO_CODE.items():
            # Each state code can have multiple names (like DC variations)
            # but we should ensure the mappings are consistent
            if state_name in seen_codes:
                pytest.fail(f"Duplicate state name found: {state_name}")
            seen_codes.add(state_name)

    def test_all_mapped_codes_are_valid(self):
        """Test that all codes in STATE_NAME_TO_CODE are in VALID_STATE_CODES."""
        for state_name, state_code in STATE_NAME_TO_CODE.items():
            assert (
                state_code in VALID_STATE_CODES
            ), f"{state_code} from {state_name} not in VALID_STATE_CODES"

    def test_expected_number_of_states(self):
        """Test that we have the expected number of states and territories."""
        # 50 states + DC + 5 territories (PR, VI, GU, AS, MP)
        assert len(VALID_STATE_CODES) == 56

    def test_critical_states_present(self):
        """Test that major states are present in the mapping."""
        critical_states = [
            ("California", "CA"),
            ("Texas", "TX"),
            ("Florida", "FL"),
            ("New York", "NY"),
            ("Pennsylvania", "PA"),
            ("Illinois", "IL"),
            ("Ohio", "OH"),
            ("Georgia", "GA"),
            ("North Carolina", "NC"),
            ("Michigan", "MI"),
        ]
        for state_name, expected_code in critical_states:
            assert normalize_state_to_code(state_name) == expected_code
