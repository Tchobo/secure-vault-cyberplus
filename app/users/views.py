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
from users.utils import (
    OTP_MAX_ATTEMPTS,
    OTP_TTL_MINUTES,
    clear_user_otp,
    generate_and_set_user_otp,
    verify_user_otp,
)

logger = logging.getLogger(__name__)


class UserRegistrationView(APIView):
    """Créer un nouveau compte utilisateur"""
    permission_classes = [AllowAny]
    
    @extend_schema(
        tags=['auth'],
        summary='Créer un compte',
        description=(
            "Crée un compte utilisateur (inactif tant que l'email n'est pas vérifié) "
            f"et envoie un code OTP à 6 chiffres par email (valide {OTP_TTL_MINUTES} min, "
            f"max {OTP_MAX_ATTEMPTS} tentatives). Appelez ensuite "
            "`POST /api/auth/verify-email/` avec email + code pour activer le compte."
        ),
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

        # OTP à 6 chiffres hashé en DB + envoyé en clair dans le mail.
        # On ne veut pas 500 si SMTP down : le compte est créé, on signale
        # juste au client que l'envoi a échoué.
        code = generate_and_set_user_otp(user)
        email_sent = True
        try:
            send_mail(
                subject='Votre code de vérification Secure Vault',
                message=(
                    f'Bonjour {user.firstname},\n\n'
                    f'Votre code de vérification est : {code}\n\n'
                    f'Ce code est valide pendant {OTP_TTL_MINUTES} minutes.\n'
                    f'Si vous n\'êtes pas à l\'origine de cette inscription, ignorez ce message.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Failed to send verification email to %s", user.email)
            email_sent = False

        if email_sent:
            message = (
                f"Compte créé. Un code de vérification à 6 chiffres a été envoyé à votre adresse "
                f"(valide {OTP_TTL_MINUTES} min). Pensez à vérifier votre dossier spam si vous ne le voyez pas."
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
    """Vérifier l'email avec le code OTP reçu par mail."""
    permission_classes = [AllowAny]

    # Erreurs standardisées exposées au client. On NE révèle pas si l'email
    # existe en base : réponse générique "code invalide ou expiré" pour éviter
    # l'énumération d'utilisateurs via cet endpoint.
    _GENERIC_ERROR = "Code invalide ou expiré."
    _REASON_TO_PUBLIC = {
        'no_otp': _GENERIC_ERROR,
        'expired': _GENERIC_ERROR,
        'invalid': _GENERIC_ERROR,
        'too_many_attempts': "Trop de tentatives. Demandez un nouveau code.",
    }

    @extend_schema(
        tags=['auth'],
        summary="Vérifier l'email avec le code OTP",
        description=(
            f"Active le compte à partir du code OTP à 6 chiffres reçu par email "
            f"(valide {OTP_TTL_MINUTES} min, max {OTP_MAX_ATTEMPTS} tentatives). "
            "Les réponses sont volontairement génériques pour éviter l'énumération "
            "d'utilisateurs — un email inexistant renvoie la même erreur qu'un code faux."
        ),
        request=EmailVerificationSerializer,
        responses={
            200: inline_serializer(
                name='EmailVerificationResponse',
                fields={'message': serializers.CharField()},
            ),
            400: inline_serializer(
                name='EmailVerificationError',
                fields={'detail': serializers.CharField()},
            ),
        },
    )
    def post(self, request):
        serializer = EmailVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data['email']
        code = serializer.validated_data['code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Réponse volontairement générique : pas de disclosure d'email.
            return Response(
                {'detail': self._GENERIC_ERROR},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.is_verified:
            return Response(
                {'message': 'Email déjà vérifié.'},
                status=status.HTTP_200_OK,
            )

        ok, reason = verify_user_otp(user, code)
        if not ok:
            return Response(
                {'detail': self._REASON_TO_PUBLIC.get(reason, self._GENERIC_ERROR)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_verified = True
        user.is_active = True
        user.save(update_fields=['is_verified', 'is_active', 'updated_at'])
        clear_user_otp(user)

        return Response(
            {'message': 'Email vérifié avec succès. Vous pouvez maintenant vous connecter.'},
            status=status.HTTP_200_OK,
        )


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