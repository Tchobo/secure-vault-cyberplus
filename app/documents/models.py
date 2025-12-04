import uuid
from django.db import models
from django.conf import settings


# Modèle existant Document (inchangé)
class Document(models.Model):
    """Modèle Document simplifié"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_documents'
    )
    
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='shared_documents',
        blank=True,
        through='DocumentShare'  # ✅ Table intermédiaire pour audit
    )
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'documents'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name


# ✅ NOUVEAU : Table intermédiaire pour audit GDPR
class DocumentShare(models.Model):
    """Audit des partages de documents - GDPR compliant"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    document = models.ForeignKey(
        'Document',
        on_delete=models.CASCADE,
        related_name='shares'
    )
    
    shared_with = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_shares'
    )
    
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='shared_documents_by_me'
    )
    
    # Audit
    shared_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'document_shares'
        unique_together = ['document', 'shared_with']
        ordering = ['-shared_at']
    
    def __str__(self):
        return f"{self.document.name} partagé avec {self.shared_with.email}"


# ✅ NOUVEAU : Journal d'audit complet (GDPR Art. 30)
class AuditLog(models.Model):
    """Journal d'audit - Obligatoire GDPR"""
    
    ACTION_CHOICES = [
        ('upload', 'Upload document'),
        ('download', 'Téléchargement'),
        ('share', 'Partage'),
        ('revoke', 'Révocation accès'),
        ('view', 'Consultation'),
        ('deactivate', 'Désactivation'),
        ('activate', 'Activation'),
        ('delete', 'Suppression'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    user_email = models.EmailField()  # Garder l'email même si user supprimé
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    
    document = models.ForeignKey(
        'Document',
        on_delete=models.SET_NULL,
        null=True
    )
    document_name = models.CharField(max_length=255)
    
    ip_address = models.GenericIPAddressField(null=True)
    user_agent = models.TextField(blank=True, null=True)
    
    details = models.JSONField(default=dict, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.user_email} - {self.action} - {self.timestamp}"