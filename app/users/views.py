import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from drf_spectacular.utils import extend_schema, inline_serializer

from users.models import User
from users.serializers import (
    UserRegistrationSerializer,
    EmailVerificationSerializer,
    UserLoginSerializer,
    UserSerializer
)
from users.utils import generate_verification_token, verify_token

logger = logging.getLogger(__name__)


class UserRegistrationView(APIView):
    """Créer un nouveau compte utilisateur"""
    permission_classes = [AllowAny]
    
    @extend_schema(
        tags=['auth'],
        summary='Créer un compte',
        description="Crée un compte utilisateur (inactif tant que l'email n'est pas vérifié) "
                    "et envoie un email contenant le lien de vérification.",
        request=UserRegistrationSerializer,
        responses={201: inline_serializer(
            name='UserRegistrationResponse',
            fields={
                'id': serializers.UUIDField(),
                'email': serializers.EmailField(),
                'firstname': serializers.CharField(),
                'lastname': serializers.CharField(),
                'created_at': serializers.DateTimeField(),
                'message': serializers.CharField(),
                'email_sent': serializers.BooleanField(),
            }
        )}
    )
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        # Envoyer email de vérification. On ne veut pas 500 si SMTP down :
        # le compte est créé, on signale juste au client que l'envoi a échoué
        # pour qu'il puisse demander un renvoi (ou que l'admin regarde les logs).
        token = generate_verification_token(user)
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
        email_sent = True
        try:
            send_mail(
                subject='Vérifiez votre email',
                message=f'Cliquez sur ce lien pour vérifier votre email: {verification_url}',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send verification email to %s", user.email)
            email_sent = False

        if email_sent:
            message = (
                "Compte créé. Un email de vérification a été envoyé à votre adresse — "
                "cliquez sur le lien pour activer votre compte. "
                "Pensez à vérifier votre dossier spam si vous ne le voyez pas."
            )
        else:
            message = (
                "Compte créé, mais l'envoi de l'email de vérification a échoué. "
                "Contactez le support ou réessayez plus tard."
            )

        return Response(
            {**serializer.data, "message": message, "email_sent": email_sent},
            status=status.HTTP_201_CREATED,
        )


class EmailVerificationView(APIView):
    """Vérifier l'email avec le token"""
    permission_classes = [AllowAny]
    
    @extend_schema(
        tags=['auth'],
        summary="Vérifier l'email",
        description="Active le compte à partir du token reçu par email (signé, valide 24h).",
        request=EmailVerificationSerializer,
        responses={200: {'description': 'Email vérifié avec succès'}}
    )
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            user_id = verify_token(token)
            
            if not user_id:
                return Response(
                    {'token': 'Token invalide ou expiré'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            try:
                user = User.objects.get(id=user_id)
                user.is_verified = True
                user.is_active = True
                user.save()
                
                return Response(
                    {'message': 'Email vérifié avec succès'},
                    status=status.HTTP_200_OK
                )
            except User.DoesNotExist:
                return Response(
                    {'token': 'Utilisateur non trouvé'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """Login et obtenir les tokens JWT"""
    permission_classes = [AllowAny]
    
    @extend_schema(
        tags=['auth'],
        summary='Se connecter',
        description='Authentifie un compte vérifié et actif, renvoie une paire de tokens JWT (access/refresh).',
        request=UserLoginSerializer,
        responses={200: inline_serializer(
            name='LoginResponse',
            fields={
                'access': serializers.CharField(),
                'refresh': serializers.CharField(),
                'user': UserSerializer(),
            }
        )}
    )
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            
            # Générer les tokens JWT
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)