import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """Le rate limiting DRF est stocké dans le cache Django (LocMemCache,
    partagé pour tout le process pytest) : sans ce reset, les compteurs
    d'un test fuient vers les suivants et déclenchent des 429 imprévisibles."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _disable_clamav_by_default(settings):
    """Force CLAMAV_ENABLED=False dans la suite entière, quoi qu'il y ait dans
    .env. Les tests qui veulent vérifier le comportement scanner activé le
    réactivent explicitement via @override_settings(CLAMAV_ENABLED=True).
    Sans ça, un dev qui met CLAMAV_ENABLED=True dans son .env pour tester
    manuellement casse toute la suite (le vrai daemon devient prérequis).
    Utilise la fixture `settings` de pytest-django qui gère proprement le
    LazySettings proxy Django et restaure la valeur en teardown."""
    settings.CLAMAV_ENABLED = False




@pytest.fixture
def api_client():
    return APIClient()
