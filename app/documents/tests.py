from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from documents.encryption import encrypt_bytes
from documents.malware import MalwareError
from documents.models import AuditLog, Document, DocumentShare
from tests.factories import UserFactory

ORIGINAL_CONTENT = b'Contenu confidentiel du vault, pour les tests.'

# Standard EICAR test string — recognized as "safe test virus" by every
# AV engine. Not actual malware.
EICAR = (
    br'X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-'
    br'STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
)


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def other_user():
    return UserFactory()


@pytest.fixture
def auth_client(owner):
    client = APIClient()
    client.force_authenticate(user=owner)
    return client


def upload_file(client, name='confidentiel.txt', content=ORIGINAL_CONTENT):
    upload = SimpleUploadedFile(name, content, content_type='text/plain')
    return client.post(reverse('document-list'), {'name': name, 'file': upload}, format='multipart')


def overwrite_stored_file(document, data):
    """Remplace le contenu stocké d'un document en passant par l'API Storage
    de Django (pas .file.path, indisponible sur un backend distant type S3) —
    fonctionne aussi bien en stockage local qu'en S3."""
    storage = document.file.storage
    name = document.file.name
    storage.delete(name)
    storage.save(name, ContentFile(data))


@pytest.mark.django_db
class TestUploadEncryption:
    """Upload : hash + chiffrement avant stockage"""

    def test_upload_encrypts_file(self, auth_client):
        response = upload_file(auth_client)
        assert response.status_code == status.HTTP_201_CREATED

        document = Document.objects.get(pk=response.data['id'])
        stored_bytes = document.file.read()

        assert stored_bytes != ORIGINAL_CONTENT

    def test_sha256_is_computed_on_upload(self, auth_client):
        response = upload_file(auth_client)

        document = Document.objects.get(pk=response.data['id'])
        assert document.sha256 != ''
        assert document.is_encrypted is True
        assert document.original_size == len(ORIGINAL_CONTENT)

    def test_uploaded_document_is_active_by_default(self, auth_client):
        """Régression : un BooleanField DRF absent d'un formulaire multipart
        est traité comme False (sémantique 'checkbox HTML'), pas comme
        'utiliser le default du modèle' — is_active doit être read_only."""
        response = upload_file(auth_client)
        assert response.data['is_active'] is True

    def test_upload_rejects_bad_extension(self, auth_client):
        upload = SimpleUploadedFile('malware.exe', b'MZ\x90\x00', content_type='application/octet-stream')
        response = auth_client.post(
            reverse('document-list'), {'name': 'malware.exe', 'file': upload}, format='multipart'
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'file' in response.data

    def test_upload_rejects_too_large(self, auth_client):
        with override_settings(MAX_UPLOAD_SIZE=10):
            response = upload_file(auth_client, content=b'0123456789ABCDEF')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'file' in response.data


@pytest.mark.django_db
class TestDownloadIntegrity:
    """Download : déchiffrement + vérification d'intégrité"""

    def test_download_returns_original_bytes(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        response = auth_client.get(reverse('document-download', args=[document_id]))

        assert response.status_code == status.HTTP_200_OK
        assert response.content == ORIGINAL_CONTENT

    def test_download_detects_corrupted_ciphertext(self, auth_client):
        upload_response = upload_file(auth_client)
        document = Document.objects.get(pk=upload_response.data['id'])

        raw = document.file.read()
        overwrite_stored_file(document, raw[:-4] + b'XXXX')

        response = auth_client.get(reverse('document-download', args=[document.id]))

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_download_detects_content_substitution(self, auth_client):
        """Cas plus subtil : le blob est re-chiffré validement (même clé)
        mais avec un contenu différent — le token Fernet est valide, seul
        le hash SHA-256 révèle la substitution."""
        upload_response = upload_file(auth_client)
        document = Document.objects.get(pk=upload_response.data['id'])

        forged = encrypt_bytes(b'contenu totalement different, faux document')
        overwrite_stored_file(document, forged)

        response = auth_client.get(reverse('document-download', args=[document.id]))

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


@pytest.mark.django_db
class TestPermissions:
    """Ownership et partage"""

    def test_user_a_cannot_download_user_b_document(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-download', args=[document_id]))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_shared_user_can_download(self, auth_client, owner, other_user):
        upload_response = upload_file(auth_client)
        document = Document.objects.get(pk=upload_response.data['id'])
        DocumentShare.objects.create(document=document, shared_with=other_user, shared_by=owner)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-download', args=[document.id]))

        assert response.status_code == status.HTTP_200_OK

    def test_owner_can_deactivate(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        response = auth_client.post(reverse('document-deactivate', args=[document_id]))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_active'] is False

    def test_non_owner_cannot_deactivate(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.post(reverse('document-deactivate', args=[document_id]))

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestThrottling:
    """Rate limiting DRF"""

    def test_upload_throttle(self, auth_client):
        for _ in range(10):
            response = upload_file(auth_client)
            assert response.status_code == status.HTTP_201_CREATED

        response = upload_file(auth_client)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_download_throttle(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        url = reverse('document-download', args=[document_id])

        for _ in range(30):
            response = auth_client.get(url)
            assert response.status_code == status.HTTP_200_OK

        response = auth_client.get(url)
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
class TestAuditLog:
    """Journal d'audit RGPD Article 30"""

    def test_upload_creates_audit_log(self, auth_client, owner):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        log = AuditLog.objects.get(action='upload', document_id=document_id)
        assert log.user == owner
        assert log.user_email == owner.email

    def test_download_creates_audit_log(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        auth_client.get(reverse('document-download', args=[document_id]))

        assert AuditLog.objects.filter(action='download', document_id=document_id).exists()

    def test_audit_log_captures_ip_and_user_agent(self, auth_client):
        upload_response = auth_client.post(
            reverse('document-list'),
            {'name': 'confidentiel.txt', 'file': SimpleUploadedFile(
                'confidentiel.txt', ORIGINAL_CONTENT, content_type='text/plain'
            )},
            format='multipart',
            HTTP_USER_AGENT='pytest-agent/1.0',
            REMOTE_ADDR='203.0.113.5',
        )

        log = AuditLog.objects.get(action='upload', document_id=upload_response.data['id'])
        assert log.ip_address == '203.0.113.5'
        assert log.user_agent == 'pytest-agent/1.0'


@pytest.mark.django_db
class TestAuditEndpoints:
    """Consultation du journal d'audit"""

    def test_owner_can_view_document_audit_log(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        auth_client.get(reverse('document-download', args=[document_id]))

        response = auth_client.get(reverse('document-audit', args=[document_id]))

        assert response.status_code == status.HTTP_200_OK
        actions = {entry['action'] for entry in response.data}
        assert actions == {'upload', 'download'}

    def test_non_owner_cannot_view_document_audit_log(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-audit', args=[document_id]))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_shared_user_cannot_view_document_audit_log(self, auth_client, owner, other_user):
        """Un utilisateur partagé peut lire le document mais pas son audit trail
        (qui révélerait IP/user-agent d'autres personnes, dont le propriétaire)."""
        upload_response = upload_file(auth_client)
        document = Document.objects.get(pk=upload_response.data['id'])
        DocumentShare.objects.create(document=document, shared_with=other_user, shared_by=owner)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-audit', args=[document.id]))

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_my_audit_log_returns_own_actions_only(self, auth_client, owner, other_user):
        upload_file(auth_client)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        upload_file(other_client)

        response = auth_client.get(reverse('my-audit-log'))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['user_email'] == owner.email


def share(client, document_id, *emails):
    return client.post(reverse('document-share', args=[document_id]), {'user_emails': list(emails)}, format='json')


def unshare(client, document_id, *emails):
    return client.post(reverse('document-unshare', args=[document_id]), {'user_emails': list(emails)}, format='json')


@pytest.mark.django_db
class TestSharing:
    """Partage d'un document entre utilisateurs"""

    def test_owner_can_share_document(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        response = share(auth_client, document_id, other_user.email)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == [{'user_email': other_user.email, 'status': 'created'}]
        assert DocumentShare.objects.filter(
            document_id=document_id, shared_with=other_user, is_active=True
        ).exists()

    def test_owner_can_share_with_several_users_at_once(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        third_user = UserFactory()

        response = share(auth_client, document_id, other_user.email, third_user.email)

        assert response.status_code == status.HTTP_200_OK
        assert {r['user_email']: r['status'] for r in response.data} == {
            other_user.email: 'created', third_user.email: 'created'
        }
        assert DocumentShare.objects.filter(document_id=document_id, is_active=True).count() == 2

    def test_share_is_best_effort_per_email(self, auth_client, other_user):
        """Un email invalide dans le lot ne doit pas empêcher le partage avec les autres."""
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        unverified = UserFactory(is_verified=False)

        response = share(auth_client, document_id, other_user.email, unverified.email)

        assert response.status_code == status.HTTP_200_OK
        results = {r['user_email']: r['status'] for r in response.data}
        assert results[other_user.email] == 'created'
        assert results[unverified.email] == 'error'
        assert DocumentShare.objects.filter(
            document_id=document_id, shared_with=other_user, is_active=True
        ).exists()
        assert not DocumentShare.objects.filter(document_id=document_id, shared_with=unverified).exists()

    def test_sharing_grants_download_access(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-download', args=[document_id]))

        assert response.status_code == status.HTTP_200_OK

    def test_shared_document_appears_in_recipient_list(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-list'))

        assert response.status_code == status.HTTP_200_OK
        assert [d['id'] for d in response.data] == [document_id]

    def test_unrelated_user_does_not_see_shared_document(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)

        unrelated_client = APIClient()
        unrelated_client.force_authenticate(user=UserFactory())
        response = unrelated_client.get(reverse('document-list'))

        assert response.data == []

    def test_revoked_share_removed_from_recipient_list(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)
        unshare(auth_client, document_id, other_user.email)

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = other_client.get(reverse('document-list'))

        assert response.data == []

    def test_non_owner_cannot_share_document(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        third_user = UserFactory()
        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        response = share(other_client, document_id, third_user.email)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_cannot_share_with_self(self, auth_client, owner):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        response = share(auth_client, document_id, owner.email)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == [{
            'user_email': owner.email, 'status': 'error',
            'detail': 'Impossible de partager un document avec soi-même.'
        }]

    def test_share_with_unverified_user_rejected(self, auth_client):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        unverified = UserFactory(is_verified=False)

        response = share(auth_client, document_id, unverified.email)

        assert response.data == [{
            'user_email': unverified.email, 'status': 'error',
            'detail': 'Utilisateur non trouvé ou inactif.'
        }]

    def test_owner_can_list_shares(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)

        response = auth_client.get(reverse('document-share', args=[document_id]))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['shared_with']['email'] == other_user.email

    def test_owner_can_unshare(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)

        response = unshare(auth_client, document_id, other_user.email)
        assert response.status_code == status.HTTP_200_OK
        assert response.data == [{'user_email': other_user.email, 'status': 'revoked'}]

        share_row = DocumentShare.objects.get(document_id=document_id, shared_with=other_user)
        assert share_row.is_active is False
        assert share_row.revoked_at is not None

        other_client = APIClient()
        other_client.force_authenticate(user=other_user)
        download_response = other_client.get(reverse('document-download', args=[document_id]))
        assert download_response.status_code == status.HTTP_403_FORBIDDEN

    def test_unshare_unknown_user_reports_error(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        response = unshare(auth_client, document_id, other_user.email)

        assert response.data == [{
            'user_email': other_user.email, 'status': 'error',
            'detail': 'Aucun partage actif avec cet utilisateur.'
        }]

    def test_resharing_reactivates_revoked_share(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']
        share(auth_client, document_id, other_user.email)
        unshare(auth_client, document_id, other_user.email)

        response = share(auth_client, document_id, other_user.email)

        assert response.data == [{'user_email': other_user.email, 'status': 'reactivated'}]
        share_row = DocumentShare.objects.get(document_id=document_id, shared_with=other_user)
        assert share_row.is_active is True
        assert share_row.revoked_at is None

    def test_share_and_unshare_create_audit_logs(self, auth_client, other_user):
        upload_response = upload_file(auth_client)
        document_id = upload_response.data['id']

        share(auth_client, document_id, other_user.email)
        unshare(auth_client, document_id, other_user.email)

        assert AuditLog.objects.filter(action='share', document_id=document_id).exists()
        assert AuditLog.objects.filter(action='revoke', document_id=document_id).exists()


@pytest.mark.django_db
class TestMalwareScanning:
    """Anti-malware guard: uploads infected or scanner-unreachable are rejected.

    Uses the EICAR test string, the industry-standard "not-a-real-virus" file
    that every AV engine detects. The daemon itself is patched — CI doesn't
    need a real clamd running."""

    def test_infected_upload_rejected(self, auth_client):
        with patch('documents.views.scan_bytes', side_effect=MalwareError('Malware detected: Eicar-Test-Signature')):
            response = auth_client.post(
                reverse('document-list'),
                {'name': 'eicar.txt', 'file': SimpleUploadedFile('eicar.txt', EICAR, content_type='text/plain')},
                format='multipart',
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['code'] == 'MALWARE_DETECTED'
        assert Document.objects.count() == 0

    def test_unreachable_scanner_rejects_upload(self, auth_client):
        # Fail-closed: if the daemon can't be reached we don't just wave the file through.
        with patch('documents.views.scan_bytes', side_effect=MalwareError('Malware scanner unreachable')):
            response = upload_file(auth_client)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['code'] == 'MALWARE_DETECTED'
        assert Document.objects.count() == 0

    def test_clean_upload_passes_scan(self, auth_client):
        # scan_bytes returns None on clean bytes — normal upload flow proceeds.
        with patch('documents.views.scan_bytes', return_value=None) as scan:
            response = upload_file(auth_client)

        assert response.status_code == status.HTTP_201_CREATED
        assert scan.called
        assert Document.objects.count() == 1

    @override_settings(CLAMAV_ENABLED=False)
    def test_scan_disabled_short_circuits(self):
        # CLAMAV_ENABLED=False → scan_bytes returns immediately without
        # attempting any socket connection, even on EICAR bytes.
        from documents.malware import scan_bytes
        with patch('documents.malware.ClamdNetworkSocket') as socket_cls:
            scan_bytes(EICAR)  # must not raise
        assert not socket_cls.called

    @override_settings(CLAMAV_ENABLED=True)
    def test_scan_bytes_raises_on_found(self):
        # scan_bytes() itself (not the view mock) — clamd reports FOUND → MalwareError.
        from documents.malware import scan_bytes
        with patch('documents.malware.ClamdNetworkSocket') as socket_cls:
            socket_cls.return_value.instream.return_value = {
                'stream': ('FOUND', 'Eicar-Test-Signature'),
            }
            with pytest.raises(MalwareError, match='Eicar-Test-Signature'):
                scan_bytes(EICAR)

    @override_settings(CLAMAV_ENABLED=True)
    def test_scan_bytes_fails_closed_on_unreachable_daemon(self):
        # scan_bytes() itself — clamd connection error → MalwareError (fail-closed).
        from clamd import ConnectionError as ClamdConnectionError

        from documents.malware import scan_bytes
        with patch('documents.malware.ClamdNetworkSocket') as socket_cls:
            socket_cls.return_value.instream.side_effect = ClamdConnectionError('refused')
            with pytest.raises(MalwareError, match='unreachable'):
                scan_bytes(EICAR)

    @override_settings(CLAMAV_ENABLED=True)
    def test_scan_bytes_passes_on_ok(self):
        # scan_bytes() itself — clamd reports OK → no exception.
        from documents.malware import scan_bytes
        with patch('documents.malware.ClamdNetworkSocket') as socket_cls:
            socket_cls.return_value.instream.return_value = {'stream': ('OK', None)}
            scan_bytes(b'clean bytes')  # must not raise
