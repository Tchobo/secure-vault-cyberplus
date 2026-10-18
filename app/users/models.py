import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email requis')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Modèle User simplifié - GDPR compliant"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True, help_text="Sert d'identifiant de connexion.")
    firstname = models.CharField(max_length=100, help_text='Prénom.')
    lastname = models.CharField(max_length=100, help_text='Nom de famille.')

    is_active = models.BooleanField(
        default=False,
        help_text='Compte activé (passe à true après vérification de l\'email).'
    )
    is_verified = models.BooleanField(default=False, help_text="Email vérifié via le code OTP envoyé à l'inscription.")
    is_staff = models.BooleanField(default=False)

    # Vérification d'email par code OTP à 6 chiffres.
    # Le code n'est JAMAIS stocké en clair : seul son hash SHA-256 est persisté
    # (cohérent avec le reste du projet "security hardening"). Expiration courte
    # (15 min) + compteur de tentatives (max 5) pour éviter le brute-force.
    verification_otp_hash = models.CharField(max_length=64, blank=True, default='')
    verification_otp_expires_at = models.DateTimeField(null=True, blank=True)
    verification_otp_attempts = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['firstname', 'lastname']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.email