# Secure Vault CyberPlus

![CI](https://github.com/Tchobo/secure-vault-cyberplus/actions/workflows/ci.yml/badge.svg)

Stockage et partage de documents chiffrés, avec piste d'audit — API Django/DRF pensée pour la conformité RGPD.

## Threat model

Ce que le vault protège, et contre qui :

- **Compromission du stockage / disque / backup** : les fichiers sont chiffrés at-rest (Fernet/AES). Un accès brut au volume `media/` ou à un backup ne révèle pas le contenu des documents.
- **Falsification du contenu stocké** (tampering) : chaque fichier est associé à un hash SHA-256 de son contenu original, revérifié à chaque téléchargement. Un fichier altéré sur disque est détecté et rejeté (`500`) plutôt que servi silencieusement.
- **Upload de fichier malveillant** : chaque upload est scanné par ClamAV **avant** chiffrement (sinon on ne scannerait qu'un blob Fernet opaque). Détection = rejet `400 MALWARE_DETECTED`. Fail-closed : si le daemon est activé mais injoignable, l'upload est rejeté aussi — on ne prend jamais le fichier à l'aveugle.
- **Accès non autorisé entre utilisateurs** : chaque document appartient à un `owner`, et n'est lisible que par lui ou les utilisateurs avec qui il a été explicitement partagé (`DocumentShare`).
- **Abus / brute-force sur l'API** : rate limiting DRF par utilisateur sur l'upload et le download.
- **Absence de traçabilité** : chaque action sensible (upload, download, activation, désactivation) est journalisée dans `AuditLog` (utilisateur, action, document, IP, user-agent, horodatage) — Article 30 RGPD.

Ce que le vault **ne** protège **pas** (hors scope v1) :
- Compromission de la clé de chiffrement elle-même (`VAULT_ENCRYPTION_KEY`) — pas de rotation de clé ni de KMS/Vault externe en v1.
- Accès direct à la base de données par un attaquant disposant déjà des credentials DB.
- Partage de lien public (non implémenté).

## Décision : Fernet applicatif, pas d'URLs présignées S3 (S3 accepté comme backend de stockage)

Le chiffrement reste géré par l'application (Fernet), quel que soit l'endroit où atterrit le blob chiffré — délibérément, pas par manque de temps. Une URL présignée S3 sert le blob **directement depuis S3 au client**, en court-circuitant l'application ; le client recevrait alors le contenu chiffré sans jamais posséder la clé pour le déchiffrer. Chiffrement applicatif et URLs présignées sont incompatibles tels quels :

- **Fernet applicatif (choix retenu)** : le serveur reste seul à détenir la clé, chaque download passe par la vue Django qui déchiffre et vérifie l'intégrité SHA-256 avant de servir le fichier. C'est ce qui est implémenté et testé (Phase 1 + Phase 2), et qui reste vrai quel que soit le backend de stockage physique.
- **S3 SSE-KMS + presigned URLs** : aurait du sens comme alternative — pas en complément — si on retirait le chiffrement applicatif et qu'on laissait S3 gérer le chiffrement at-rest nativement. Non retenu.

**Backend de stockage physique — S3 en option** (`USE_S3=True` + credentials, voir `.env.example`) : pour un déploiement PaaS (Render, Fly.io...) au filesystem éphémère, les fichiers uploadés doivent survivre aux redéploiements/redémarrages — le disque local du conteneur ne convient pas. `django-storages`/`boto3` permettent de faire écrire Django sur un bucket S3 (privé, `AWS_QUERYSTRING_AUTH=False`, pas d'URL présignée) au lieu du disque local, **sans changer le modèle de sécurité ci-dessus** : c'est toujours Django qui chiffre avant écriture et déchiffre après lecture, le client ne parle jamais directement à S3. Par défaut (`USE_S3=False`), tout reste sur disque local. Les tests d'intégrité manipulent le blob stocké via l'API `Storage` de Django (helper `overwrite_stored_file()`), donc la suite pytest tourne à l'identique en local et sur S3.

## Architecture

```
Upload:
  Client → API (JWT auth) → validation (extension/taille/magic bytes)
         → scan ClamAV (fail-closed) → SHA-256(original)
         → chiffrement Fernet → stockage (FileField)
         → AuditLog("upload")

Download:
  Client → API (JWT auth) → permission (owner/shared)
         → lecture du blob chiffré → déchiffrement Fernet
         → SHA-256(déchiffré) == hash stocké ? → 200 + fichier : 500
         → AuditLog("download")
```

## Features implémentées

- ✅ Authentification par email + JWT (register, email verification, login)
- ✅ Upload/download de documents avec ownership et partage (`DocumentShare`)
- ✅ Validation des fichiers : extension, taille, contenu réel (magic bytes)
- ✅ **Scan anti-malware** (ClamAV, opt-in via `CLAMAV_ENABLED=True`) — fail-closed avant chiffrement
- ✅ **Chiffrement at-rest** (Fernet/AES) — les fichiers ne sont jamais stockés en clair
- ✅ **Intégrité SHA-256** — vérifiée à chaque téléchargement, détecte le tampering
- ✅ **Rate limiting** DRF (upload/download/global)
- ✅ **Audit trail** RGPD (Article 30) sur upload/download/activate/deactivate
- ✅ Documentation API OpenAPI/Swagger (`drf-spectacular`)

## Stack technique

Django 3.2 · Django REST Framework · PostgreSQL · `cryptography` (Fernet) · SimpleJWT · drf-spectacular · Docker / docker-compose

## Setup local

```bash
cp .env.example .env
# Générer une clé de chiffrement et la coller dans .env (VAULT_ENCRYPTION_KEY) :
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser
```

L'API est servie sur `http://localhost:8000`.

## Qualité du code

CI (GitHub Actions, `.github/workflows/ci.yml`) : lint (`ruff`), type check (`mypy`), tests (`pytest` + PostgreSQL) à chaque push/PR sur `main`.

En local, les mêmes vérifications tournent avant chaque commit via [pre-commit](https://pre-commit.com/) (`ruff`, `mypy`, `bandit`, `detect-secrets`) :

```bash
pip install -r requirements-dev.txt
pre-commit install          # active le hook git une fois pour toutes
pre-commit run --all-files  # exécute manuellement sur tout le repo
```

`detect-secrets` compare contre `.secrets.baseline` (secrets déjà connus/acceptés — ex. mots de passe factices dans les tests) ; un vrai secret nouvellement introduit bloque le commit.

## Variables d'environnement

| Variable | Rôle |
|---|---|
| `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT` | Connexion PostgreSQL |
| `DEBUG` | Mode debug Django (désactiver en prod) |
| `SECRET_KEY` | Clé secrète Django (sessions, signing) |
| `ALLOWED_HOSTS` | Hosts autorisés, liste séparée par des virgules |
| `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` | Envoi des emails de vérification de compte |
| `FRONTEND_URL` | Base URL utilisée dans les liens de vérification d'email |
| `MAX_UPLOAD_SIZE` | Taille max d'un fichier uploadé (bytes) |
| `ALLOWED_FILE_EXTENSIONS` | Extensions autorisées à l'upload |
| `VAULT_ENCRYPTION_KEY` | Clé maître Fernet pour le chiffrement at-rest (32 bytes base64 url-safe) |
| `CLAMAV_ENABLED` | `False` (défaut) = pas de scan (dev/CI sans daemon). `True` = scan chaque upload avec ClamAV avant chiffrement, rejet fail-closed si le daemon est injoignable |
| `CLAMAV_HOST`, `CLAMAV_PORT`, `CLAMAV_TIMEOUT` | Cible du daemon clamd (`clamav:3310` par défaut, service `clamav` dans `docker-compose.yml`) |
| `USE_S3` | `False` (défaut) = stockage disque local. `True` = stockage S3 (voir décision ci-dessus), nécessite les variables `AWS_*` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` | Credentials et bucket S3, requis seulement si `USE_S3=True` |

## Endpoints API

| Méthode | Endpoint | Description | Auth |
|---|---|---|---|
| POST | `/api/auth/register/` | Créer un compte | Non |
| POST | `/api/auth/verify-email/` | Vérifier l'email via token | Non |
| POST | `/api/auth/login/` | Login, obtenir les tokens JWT | Non |
| GET | `/api/documents/` | Lister mes documents | Oui |
| POST | `/api/documents/` | Uploader un document (chiffré) | Oui |
| GET | `/api/documents/{id}/` | Détails d'un document | Oui (owner/shared) |
| GET | `/api/documents/{id}/download/` | Télécharger (déchiffré + vérifié) | Oui (owner/shared) |
| POST | `/api/documents/{id}/activate/` | Réactiver un document | Oui (owner) |
| POST | `/api/documents/{id}/deactivate/` | Désactiver un document | Oui (owner) |
| GET | `/api/documents/{id}/audit/` | Historique d'audit du document | Oui (owner) |
| GET | `/api/audit/` | Mon historique d'audit (tous documents) | Oui |
| GET | `/api/documents/{id}/share/` | Lister les partages actifs | Oui (owner) |
| POST | `/api/documents/{id}/share/` | Partager avec un ou plusieurs emails (`user_emails`) | Oui (owner) |
| POST | `/api/documents/{id}/unshare/` | Révoquer un ou plusieurs partages (`user_emails`) | Oui (owner) |
| GET | `/api/docs/` | Documentation Swagger UI | Non |

## Scan anti-malware (ClamAV)

Le service `clamav` de `docker-compose.yml` fait tourner un daemon `clamd` (image officielle `clamav/clamav`). Chaque upload est scanné **avant chiffrement** — sinon on ne scannerait qu'un blob Fernet opaque et illisible par n'importe quel moteur AV. Le scan est **synchrone** (pas de Celery) : le portfolio privilégie la simplicité, et un scan `clamd instream` sur un fichier de 10 MB se compte en dizaines de ms.

**Fail-closed** : si `CLAMAV_ENABLED=True` et que le daemon est injoignable, l'upload est rejeté (`400 MALWARE_DETECTED`) plutôt que passé en clair. Un scanner absent est traité comme un fichier infecté — jamais l'inverse.

**Désactivé par défaut** (`CLAMAV_ENABLED=False`). Le service `clamav` est aussi derrière un **profil Docker Compose** (`profiles: ["scan"]`) — un `docker compose up` classique ne tire pas l'image (~200 MB) et n'attend pas les ~5 min de `freshclam` au premier boot. Pour activer le scan en local :

```bash
# .env : CLAMAV_ENABLED=True
docker compose --profile scan up
```

La CI GitHub Actions n'a pas besoin d'un vrai clamd — les tests mockent le socket (voir plus bas).

**Tests** : la suite pytest utilise le [signature EICAR](https://www.eicar.org/download-anti-malware-testfile/) (chaîne standard reconnue par tous les moteurs AV, sans code malveillant réel). `TestMalwareScanning` couvre les 4 branches de `scan_bytes()` (short-circuit désactivé, OK, FOUND, ConnectionError fail-closed) + le comportement de la vue (rejet 400 sur infecté/scanner down, upload OK sur clean). Pas besoin d'un clamd tournant en CI, `ClamdNetworkSocket` est mocké.

## Rate limits

| Scope | Limite |
|---|---|
| Upload | 10 / minute / utilisateur |
| Download | 30 / minute / utilisateur |
| Global (autres endpoints authentifiés) | 100 / heure / utilisateur |

## License

MIT
