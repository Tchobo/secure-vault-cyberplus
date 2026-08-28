import hashlib

from django.core.files.base import ContentFile
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser

from cryptography.fernet import InvalidToken

from documents.audit import log_action
from documents.encryption import encrypt_bytes, decrypt_bytes
from documents.malware import MalwareError, scan_bytes
from documents.models import AuditLog, Document, DocumentShare
from documents.permissions import IsDocumentOwner, IsOwnerOrShared
from documents.serializers import (
    AuditLogSerializer,
    DocumentListSerializer,
    DocumentSerializer,
    DocumentShareDetailSerializer,
    DocumentShareSerializer,
)
from documents.throttling import DownloadRateThrottle, UploadRateThrottle
from users.models import User


class DocumentListView(APIView):
    """Liste et création de documents"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [UploadRateThrottle()]
        return super().get_throttles()

    @extend_schema(
        tags=['documents'],
        summary='Lister mes documents',
        description="Liste les documents dont l'utilisateur connecté est propriétaire, "
                    "ainsi que ceux activement partagés avec lui.",
        responses={200: DocumentListSerializer(many=True)}
    )
    def get(self, request):
        """Lister les documents de l'utilisateur (possédés + partagés avec lui)"""
        documents = Document.objects.filter(
            Q(owner=request.user) | Q(shares__shared_with=request.user, shares__is_active=True)
        ).distinct()
        serializer = DocumentListSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['documents'],
        summary='Uploader un document',
        description='Valide (extension/taille/magic bytes), chiffre (Fernet) et stocke le fichier ; '
                    'calcule son SHA-256 avant chiffrement pour vérification ultérieure. '
                    'Limité à 10 uploads/minute/utilisateur.',
        request=DocumentSerializer,
        responses={201: DocumentSerializer}
    )
    def post(self, request):
        """Upload un nouveau document : hash + chiffrement avant stockage"""
        serializer = DocumentSerializer(data=request.data)
        if serializer.is_valid():
            uploaded_file = serializer.validated_data['file']
            original_bytes = uploaded_file.read()

            # Anti-malware scan BEFORE encryption — otherwise we'd only be able
            # to scan opaque Fernet blobs. No-op when CLAMAV_ENABLED=False.
            try:
                scan_bytes(original_bytes)
            except MalwareError as exc:
                return Response(
                    {'success': False, 'code': 'MALWARE_DETECTED', 'detail': str(exc)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            sha256 = hashlib.sha256(original_bytes).hexdigest()
            encrypted_bytes = encrypt_bytes(original_bytes)
            encrypted_file = ContentFile(encrypted_bytes, name=uploaded_file.name)

            document = serializer.save(
                owner=request.user,
                file=encrypted_file,
                sha256=sha256,
                original_size=len(original_bytes),
                is_encrypted=True,
            )
            log_action(request.user, 'upload', document, request)

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class DocumentDetailView(APIView):
    """Détails d'un document"""
    permission_classes = [IsAuthenticated, IsOwnerOrShared]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary="Détails d'un document",
        description='Accessible au propriétaire ou à un utilisateur avec qui le document est partagé.',
        responses={200: DocumentSerializer}
    )
    def get(self, request, pk):
        """Voir les détails d'un document"""
        document = self.get_object(pk)
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentDownloadView(APIView):
    """Télécharger un document"""
    permission_classes = [IsAuthenticated, IsOwnerOrShared]
    throttle_classes = [DownloadRateThrottle]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary='Télécharger un document',
        description='Déchiffre le fichier stocké et vérifie son SHA-256 avant de le renvoyer ; '
                    'répond 500 si le blob a été altéré (échec du déchiffrement ou hash différent). '
                    'Limité à 30 téléchargements/minute/utilisateur.',
        responses={200: {'description': 'Fichier téléchargé'}}
    )
    def get(self, request, pk):
        """Déchiffrer le fichier et vérifier son intégrité avant de le renvoyer"""
        document = self.get_object(pk)

        stored_bytes = document.file.read()

        if document.is_encrypted:
            try:
                data = decrypt_bytes(stored_bytes)
            except InvalidToken:
                return Response(
                    {'error': 'Intégrité compromise : impossible de déchiffrer le fichier stocké.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            data = stored_bytes

        if document.sha256:
            computed_sha256 = hashlib.sha256(data).hexdigest()
            if computed_sha256 != document.sha256:
                return Response(
                    {'error': 'Intégrité compromise : le contenu du fichier ne correspond pas au hash enregistré.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        log_action(request.user, 'download', document, request)

        response = HttpResponse(data, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.name}"'
        return response


class DocumentDeactivateView(APIView):
    """Désactiver un document"""
    permission_classes = [IsAuthenticated, IsOwnerOrShared]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary='Désactiver un document',
        description='Réservé au propriétaire. Aucun corps de requête attendu.',
        request=None,
        responses={200: DocumentSerializer}
    )
    def post(self, request, pk):
        """Désactiver le document"""
        document = self.get_object(pk)
        document.is_active = False
        document.save()
        log_action(request.user, 'deactivate', document, request)
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentActivateView(APIView):
    """Activer un document"""
    permission_classes = [IsAuthenticated, IsOwnerOrShared]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary='Activer un document',
        description='Réservé au propriétaire. Aucun corps de requête attendu.',
        request=None,
        responses={200: DocumentSerializer}
    )
    def post(self, request, pk):
        """Activer le document"""
        document = self.get_object(pk)
        document.is_active = True
        document.save()
        log_action(request.user, 'activate', document, request)
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentAuditLogView(APIView):
    """Historique d'audit d'un document"""
    permission_classes = [IsAuthenticated, IsDocumentOwner]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary="Historique d'audit d'un document",
        description="Réservé au propriétaire — révèle IP/user-agent de tous les accès, "
                    "y compris ceux des utilisateurs avec qui le document est partagé.",
        responses={200: AuditLogSerializer(many=True)}
    )
    def get(self, request, pk):
        document = self.get_object(pk)
        logs = AuditLog.objects.filter(document=document)
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MyAuditLogView(APIView):
    """Historique d'audit de l'utilisateur connecté"""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['documents'],
        summary="Mon historique d'audit",
        description="Actions de l'utilisateur connecté, tous documents confondus.",
        responses={200: AuditLogSerializer(many=True)}
    )
    def get(self, request):
        logs = AuditLog.objects.filter(user=request.user)
        serializer = AuditLogSerializer(logs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DocumentShareView(APIView):
    """Partager un document / lister ses partages actifs"""
    permission_classes = [IsAuthenticated, IsDocumentOwner]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary='Lister les partages actifs',
        description='Réservé au propriétaire.',
        responses={200: DocumentShareDetailSerializer(many=True)}
    )
    def get(self, request, pk):
        document = self.get_object(pk)
        shares = DocumentShare.objects.filter(document=document, is_active=True)
        serializer = DocumentShareDetailSerializer(shares, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=['documents'],
        summary='Partager un document avec un ou plusieurs utilisateurs',
        description="Réservé au propriétaire. Traite chaque email indépendamment (best-effort) : "
                    "un email invalide n'empêche pas le partage avec les autres. Réactive un partage "
                    "existant s'il avait été révoqué. Réponse : un statut par email fourni.",
        request=DocumentShareSerializer,
        responses={200: {'description': 'Statut du partage pour chaque email fourni'}}
    )
    def post(self, request, pk):
        document = self.get_object(pk)
        serializer = DocumentShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for email in serializer.validated_data['user_emails']:
            if email == request.user.email:
                results.append({
                    'user_email': email, 'status': 'error',
                    'detail': 'Impossible de partager un document avec soi-même.'
                })
                continue

            try:
                target_user = User.objects.get(email=email, is_active=True, is_verified=True)
            except User.DoesNotExist:
                results.append({
                    'user_email': email, 'status': 'error',
                    'detail': 'Utilisateur non trouvé ou inactif.'
                })
                continue

            _, created = DocumentShare.objects.update_or_create(
                document=document,
                shared_with=target_user,
                defaults={'shared_by': request.user, 'is_active': True, 'revoked_at': None},
            )
            log_action(request.user, 'share', document, request, details={'shared_with': target_user.email})
            results.append({'user_email': email, 'status': 'created' if created else 'reactivated'})

        return Response(results, status=status.HTTP_200_OK)


class DocumentUnshareView(APIView):
    """Révoquer le partage d'un document"""
    permission_classes = [IsAuthenticated, IsDocumentOwner]

    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj

    @extend_schema(
        tags=['documents'],
        summary="Révoquer le partage avec un ou plusieurs utilisateurs",
        description="Réservé au propriétaire. Traite chaque email indépendamment (best-effort). "
                    "Réponse : un statut par email fourni.",
        request=DocumentShareSerializer,
        responses={200: {'description': 'Statut de la révocation pour chaque email fourni'}}
    )
    def post(self, request, pk):
        document = self.get_object(pk)
        serializer = DocumentShareSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        for email in serializer.validated_data['user_emails']:
            share = DocumentShare.objects.filter(
                document=document, shared_with__email=email, is_active=True
            ).first()
            if share is None:
                results.append({
                    'user_email': email, 'status': 'error',
                    'detail': "Aucun partage actif avec cet utilisateur."
                })
                continue

            share.is_active = False
            share.revoked_at = timezone.now()
            share.save()
            log_action(request.user, 'revoke', document, request, details={'shared_with': email})
            results.append({'user_email': email, 'status': 'revoked'})

        return Response(results, status=status.HTTP_200_OK)
