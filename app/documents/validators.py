import magic
from django.core.exceptions import ValidationError
from django.conf import settings


def validate_file_extension(file):
    """Valider l'extension du fichier"""
    ext = file.name.split('.')[-1].lower()
    if ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise ValidationError(
            f"Extension '{ext}' non autorisée. Extensions valides: {', '.join(settings.ALLOWED_FILE_EXTENSIONS)}"
        )


def validate_file_size(file):
    """Valider la taille du fichier (max 10MB)"""
    if file.size > settings.MAX_UPLOAD_SIZE:
        max_mb = settings.MAX_UPLOAD_SIZE / (1024 * 1024)
        raise ValidationError(
            f"Fichier trop volumineux. Taille max: {max_mb}MB"
        )


def validate_file_content(file):
    """SÉCURITÉ: Valider le contenu réel du fichier (magic bytes)"""
    # Lire les premiers bytes
    file.seek(0)
    file_content = file.read(2048)
    file.seek(0)
    
    # Détecter le type MIME réel
    mime = magic.from_buffer(file_content, mime=True)
    
    # Extensions autorisées et leurs types MIME correspondants
    allowed_mimes = {
        'pdf': ['application/pdf'],
        'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
        'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        'txt': ['text/plain'],
        'png': ['image/png'],
        'jpg': ['image/jpeg'],
        'jpeg': ['image/jpeg'],
    }
    
    ext = file.name.split('.')[-1].lower()
    
    if ext not in allowed_mimes:
        raise ValidationError(f"Extension non autorisée: {ext}")
    
    if mime not in allowed_mimes[ext]:
        raise ValidationError(
            f"Type de fichier invalide. Extension '{ext}' mais contenu réel: '{mime}'"
        )