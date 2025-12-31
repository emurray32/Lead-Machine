import pytest
from monitors import common
import config

def test_contains_keywords(mock_config):
    """Test keyword detection."""
    assert common.contains_keywords("This has trans in it") == ['trans']
    assert common.contains_keywords("Nothing here") == []
    # Test case insensitivity
    assert common.contains_keywords("THIS HAS LOC") == ['loc']

def test_is_bot_author(mock_config):
    """Test bot detection."""
    assert common.is_bot_author("dependabot[bot]")
    assert common.is_bot_author("my-bot")
    assert not common.is_bot_author("eric")

def test_is_localization_file(mock_config):
    """Test localization file detection."""
    assert common.is_localization_file("locales/fr.json")
    assert common.is_localization_file("i18n/messages.po")
    # Wrong dir
    assert not common.is_localization_file("src/fr.json")
    # Wrong ext
    assert not common.is_localization_file("locales/config.py")

def test_extract_language_from_file(mock_config):
    """Test language extraction."""
    assert common.extract_language_from_file("locales/fr.json") == "fr"
    assert common.extract_language_from_file("locales/es.json") == "es"
    # Not in config.LANGUAGE_CODES for this test mock
    assert common.extract_language_from_file("locales/de.json") is None

def test_sanitize_filename():
    """Test filename sanitization."""
    assert common.sanitize_filename("hello/world.json") == "hello_world_json"
    assert common.sanitize_filename("cool-file_name.txt") == "cool-file_name_txt"
