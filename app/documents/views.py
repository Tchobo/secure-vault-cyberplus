from django.shortcuts import render

# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema

from apps.documents.models import Document
from apps.documents.serializers import DocumentSerializer, DocumentListSerializer
from apps.documents.permissions import IsOwnerOrShared


class DocumentListView(APIView):
    """Liste et création de documents"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    @extend_schema(
        responses={200: DocumentListSerializer(many=True)}
    )
    def get(self, request):
        """Lister les documents de l'utilisateur"""
        documents = Document.objects.filter(owner=request.user)
        serializer = DocumentListSerializer(documents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    @extend_schema(
        request=DocumentSerializer,
        responses={201: DocumentSerializer}
    )
    def post(self, request):
        """Upload un nouveau document"""
        serializer = DocumentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(owner=request.user)
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
    
    def get_object(self, pk):
        obj = get_object_or_404(Document, pk=pk)
        self.check_object_permissions(self.request, obj)
        return obj
    
    @extend_schema(
        responses={200: {'description': 'Fichier téléchargé'}}
    )
    def get(self, request, pk):
        """Télécharger le fichier"""
        document = self.get_object(pk)
        
        response = FileResponse(
            document.file.open('rb'),
            content_type='application/octet-stream'
        )
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
        responses={200: DocumentSerializer}
    )
    def post(self, request, pk):
        """Désactiver le document"""
        document = self.get_object(pk)
        document.is_active = False
        document.save()
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
        responses={200: DocumentSerializer}
    )
    def post(self, request, pk):
        """Activer le document"""
        document = self.get_object(pk)
        document.is_active = True
        document.save()
        serializer = DocumentSerializer(document)
        return Response(serializer.data, status=status.HTTP_200_OK)