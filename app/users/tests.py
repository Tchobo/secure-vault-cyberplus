
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from backend.users.models import User
import pytest

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def create_user():
    def _create_user(**kwargs):
        defaults = {
            'email': 'test@example.com',
            'password': 'SecurePass123!',
            'firstname': 'John',
            'lastname': 'Doe',
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)
    return _create_user



@pytest.mark.django_db
class TestUserRegistration:
    """RED: Tests pour la création de compte - doivent échouer d'abord"""
    
    def test_register_user_success(self, api_client):
        """Test: Créer un compte avec données valides"""
        url = reverse('user-register')
        data = {
            'email': 'newuser@example.com',
            'password': 'SecurePass123!',
            'firstname': 'Jane',
            'lastname': 'Smith'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['email'] == 'newuser@example.com'
        assert 'password' not in response.data  # Ne pas retourner le password
        
        # Vérification en base
        user = User.objects.get(email='newuser@example.com')
        assert user.firstname == 'Jane'
        assert user.is_active is False  # Pas activé tant que email non vérifié
        assert user.is_verified is False

    def test_register_user_missing_fields(self, api_client):
        """Test: Échec si champs manquants"""
        url = reverse('user-register')
        data = {'email': 'incomplete@example.com'}
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'password' in response.data
        assert 'firstname' in response.data
    
    def test_register_user_duplicate_email(self, api_client, create_user):
        """Test: Impossible de créer 2 comptes avec même email"""
        create_user(email='existing@example.com')
        
        url = reverse('user-register')
        data = {
            'email': 'existing@example.com',
            'password': 'SecurePass123!',
            'firstname': 'Jane',
            'lastname': 'Smith'
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'email' in response.data

