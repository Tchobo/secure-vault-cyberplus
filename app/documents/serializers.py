from rest_framework import serializers
from apps.documents.models import Document, DocumentShare, AuditLog
from apps.users.serializers import UserSerializer
from apps.documents.validators import (
    validate_file_extension,
    validate_file_size,
    validate_file_content
)


# Serializers existants (inchangés)
class DocumentSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    file = serializers.FileField(
        validators=[validate_file_extension, validate_file_size, validate_file_content]
    )
    
    class Meta:
        model = Document
        fields = [
            'id', 'name', 'file', 'owner', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


class DocumentListSerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    
    class Meta:
        model = Document
        fields = ['id', 'name', 'owner', 'is_active', 'created_at']


# ✅ NOUVEAUX : Serializers pour le partage
class DocumentShareSerializer(serializers.Serializer):
    """Partager un document avec un utilisateur"""
    user_email = serializers.EmailField()
    
    def validate_user_email(self, value):
        from apps.users.models import User
        
        try:
            user = User.objects.get(email=value, is_active=True, is_verified=True)
        except User.DoesNotExist:
            raise serializers.ValidationError("Utilisateur non trouvé ou inactif")
        
        return value


class SharedUserSerializer(serializers.ModelSerializer):
    """Liste des utilisateurs avec qui le document est partagé"""
    shared_at = serializers.SerializerMethodField()
    
    class Meta:
        model = serializers.ModelSerializer.Meta.model
        fields = ['id', 'email', 'firstname', 'lastname', 'shared_at']
    
    def get_shared_at(self, obj):
        # Récupérer la date de partage depuis DocumentShare
        document = self.context.get('document')
        if document:
            share = DocumentShare.objects.filter(
                document=document,
                shared_with=obj,
                is_active=True
            ).first()
            return share.shared_at if share else None
        return None


class DocumentShareDetailSerializer(serializers.ModelSerializer):
    """Détails d'un partage (pour audit)"""
    shared_with = UserSerializer(read_only=True)
    shared_by = UserSerializer(read_only=True)
    document_name = serializers.CharField(source='document.name', read_only=True)
    
    class Meta:
        model = DocumentShare
        fields = [
            'id', 'document_name', 'shared_with', 'shared_by',
            'shared_at', 'revoked_at', 'is_active'
        ]


class AuditLogSerializer(serializers.ModelSerializer):
    """Serializer pour les logs d'audit"""
    
    class Meta:
        model = AuditLog
        fields = [
            'id', 'user_email', 'action', 'document_name',
            'ip_address', 'details', 'timestamp'
        ]