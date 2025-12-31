import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture
def mock_config(mocker):
    """Mock configuration values."""
    mocker.patch('config.KEYWORDS', ['trans', 'loc'])
    mocker.patch('config.BOT_PATTERNS', ['bot', 'dependabot'])
    mocker.patch('config.LOCALIZATION_DIRS', ['locales/', 'i18n/'])
    mocker.patch('config.LOCALIZATION_FILE_PATTERNS', ['.json', '.po'])
    mocker.patch('config.LANGUAGE_CODES', ['en', 'fr', 'es'])
