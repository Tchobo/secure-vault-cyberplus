import secrets
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.conf import settings


def generate_verification_token(user):
    """Génère un token de vérification sécurisé"""
    signer = TimestampSigner()
    return signer.sign(str(user.id))


def verify_token(token, max_age=86400):  # 24h
    """Vérifie et décode un token"""
    signer = TimestampSigner()
    try:
        user_id = signer.unsign(token, max_age=max_age)
        return user_id
    except (BadSignature, SignatureExpired):
        return None