"""Vérification d'email par code OTP à 6 chiffres.

Le code est généré avec ``secrets.randbelow`` (CSPRNG), stocké hashé en DB
(SHA-256) et vérifié en temps constant via ``secrets.compare_digest``.
Expiration ``OTP_TTL_MINUTES`` + plafond ``OTP_MAX_ATTEMPTS`` pour éviter
le brute-force.
"""

import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone


OTP_TTL_MINUTES = 15
OTP_MAX_ATTEMPTS = 5


def _hash_otp(code: str) -> str:
    """SHA-256 hex du code OTP (64 caractères)."""
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def generate_and_set_user_otp(user) -> str:
    """Génère un code 6 chiffres, le persiste HASHÉ sur ``user`` et le renvoie
    en clair pour envoi par email.

    Reset le compteur de tentatives à 0 à chaque nouvelle génération.
    """
    code = f"{secrets.randbelow(1_000_000):06d}"
    user.verification_otp_hash = _hash_otp(code)
    user.verification_otp_expires_at = timezone.now() + timedelta(minutes=OTP_TTL_MINUTES)
    user.verification_otp_attempts = 0
    user.save(update_fields=[
        'verification_otp_hash',
        'verification_otp_expires_at',
        'verification_otp_attempts',
        'updated_at',
    ])
    return code


def verify_user_otp(user, code: str) -> tuple[bool, str]:
    """Vérifie ``code`` contre l'OTP de ``user``.

    Renvoie ``(ok, reason)`` :
    - ``(True, "")`` si valide → le caller doit activer le compte + nettoyer les champs OTP.
    - ``(False, "<raison>")`` sinon. ``reason`` ∈ {"no_otp", "expired", "too_many_attempts", "invalid"}.

    Incrémente le compteur de tentatives sur chaque mismatch.
    """
    if not user.verification_otp_hash or not user.verification_otp_expires_at:
        return False, 'no_otp'

    if user.verification_otp_attempts >= OTP_MAX_ATTEMPTS:
        return False, 'too_many_attempts'

    if timezone.now() > user.verification_otp_expires_at:
        return False, 'expired'

    expected = user.verification_otp_hash
    actual = _hash_otp(code or '')
    if not secrets.compare_digest(expected, actual):
        user.verification_otp_attempts += 1
        user.save(update_fields=['verification_otp_attempts', 'updated_at'])
        return False, 'invalid'

    return True, ''


def clear_user_otp(user) -> None:
    """Nettoie les champs OTP après une vérification réussie (ou un reset admin)."""
    user.verification_otp_hash = ''
    user.verification_otp_expires_at = None
    user.verification_otp_attempts = 0
    user.save(update_fields=[
        'verification_otp_hash',
        'verification_otp_expires_at',
        'verification_otp_attempts',
        'updated_at',
    ])
