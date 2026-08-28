# Secure Vault CyberPlus — Roadmap de renforcement portfolio

**Goal** : transformer ce squelette Django en un vrai *"secure vault"* qui honore son nom, à destination des candidatures backend Python / Platform Engineer / Security.

**Timeline cible** : ~1 semaine (5-7 soirées de 1h-2h), intermittent.

**Ready to showcase** : quand les 4 phases sont ✅ complètes.

---

## 📊 État actuel du repo (audit du 2026-08-24)

> ⚠️ Snapshot du 2026-08-24, avant la Phase 0. Voir la section **Phase 0** et le **Session log** (2026-08-25) pour l'état réel actuel — la plupart des ❌ ci-dessous sont maintenant ✅.

### ✅ Ce qui est déjà en place
- **User model** — Custom user email + is_verified + is_active
- **Document model** — UUID PK, ownership, sharing via `DocumentShare` (audit-ready), lifecycle timestamps
- **DocumentShare model** — table pivot avec `shared_at`, `revoked_at`, `is_active` (GDPR-friendly)
- **AuditLog model** — journal complet (action, user, document, IP, user_agent, JSON details) — Article 30 GDPR ready
- **Validators** — file extension, size, content (52 lignes)
- **Permissions** — `IsOwnerOrShared` (15 lignes)
- **Views** — CRUD Document + download + activate/deactivate (~127 lignes)
- **Auth flow** — users/views.py (116 lignes, à explorer)
- **Tests users** — 81 lignes
- **Docker + docker-compose** — présents
- **.env / .env.example** — split OK, .env gitignored

### ⚠️ Ce qui manque (ce qu'on va combler)
- ❌ **Encryption at rest** — les fichiers sont stockés en clair via `FileField`. Le nom "secure vault" perd sa promesse
- ❌ **SHA-256 integrity hash** — pas de verification anti-tampering
- ❌ **Rate limiting** — pas de DRF throttling
- ❌ **Audit hooks** — les modèles AuditLog existent mais les views ne loggent PAS
- ❌ **Tests documents/** — 3 lignes = 0 tests → coverage crashera
- ❌ **README** — 1 ligne, aucun contenu utile
- ❌ **API docs polie** — drf-spectacular installé mais pas de tags/descriptions
- ❌ **CI/CD** — pas de `.github/workflows/`
- ❌ **Presigned URLs S3** — download direct `FileField.open()` = anti-pattern cloud

---

## 🧱 Phase 0 — Fondations (hors roadmap initial, bloquant)

Pas planifiée dans l'audit du 2026-08-24, mais découverte le 2026-08-25 en essayant de faire tourner le squelette : **le projet ne démarrait pas du tout**. Corrigé avant de pouvoir attaquer la Phase 1 :

- [x] Imports cassés `apps.users.*` / `apps.documents.*` / `backend.users.*` → `users.*` / `documents.*` (le package `apps` n'existe pas)
- [x] `SharedUserSerializer.Meta.model = serializers.ModelSerializer.Meta.model` → `AttributeError` à l'import (`ModelSerializer` n'a pas de `Meta`). Remplacé par `model = User`.
- [x] `Document.shared_with` (M2M avec `through=DocumentShare`) ambigu : `DocumentShare` a 2 FK vers `User` (`shared_with`, `shared_by`) → ajout de `through_fields=('document', 'shared_with')`
- [x] Migrations initiales absentes (`users`, `documents`) → générées et appliquées
- [x] `pytest.init` : `DJANGO_SETTINGS_MODULE = config.settings` (inexistant) → `app.settings`
- [x] `docker-compose.yml` : commande `python manage.py wait_for_db` référencée mais absente du repo → créée (`users/management/commands/wait_for_db.py`)
- [x] `settings.py` : `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` lus depuis `.env` via `config()` puis **réécrits en dur juste en dessous**, annulant le split env/secrets fait au commit précédent. `SPECTACULAR_SETTINGS`/`STATIC_URL` dupliqués. Nettoyé.
- [x] `settings.py` : `FRONTEND_URL`, `EMAIL_BACKEND`, `DEFAULT_FROM_EMAIL` présents dans `.env`/`.env.example` mais jamais lus dans `settings.py` → `AttributeError` au register. Ajoutés.
- [x] `Dockerfile` : `COPY requirements.txt /requirements.txt` puis `pip install -r requirements.txt` (chemin relatif, sans le `/`) exécuté depuis `WORKDIR /app` → fichier introuvable. Corrigé en `pip install -r /requirements.txt`.
- [x] `requirements.txt` : `psycopg2>=2.8.6,<2.9` incompatible avec Python 3.11 (`SystemError: initialization of _psycopg raised unreported exception`) → bump `psycopg2>=2.9.9`. `python-magic` (utilisé par `validators.py`, `import magic`) manquant → ajouté.
- [x] `docker-compose.yml` : `ports: "8000:8000"` mais `runserver 0.0.0.0:8080` à l'intérieur du conteneur → port inaccessible. Aligné sur `8000`.
- [x] `documents/serializers.py` : `is_active` accepté en écriture sur `DocumentSerializer`. Or un `BooleanField` DRF absent d'un `multipart/form-data` (upload) est traité comme **`False`** (sémantique "checkbox HTML non cochée"), pas comme "utiliser le `default=True}` du modèle" → **tout document uploadé naissait désactivé**. Passé en `read_only` (le toggle se fait via `activate`/`deactivate`).
- [x] `DocumentDownloadView` : `cryptography.fernet.InvalidToken` (échec HMAC sur un blob chiffré altéré) non catché → 500 Django brut au lieu d'une réponse JSON propre. Ajout d'un `try/except` dédié.

**Status Phase 0** : ✅ Complète (2026-08-25)

---

## 🎯 Phase 1 — Le must (features "secure vault" attendues)

**Durée** : 2-3 soirées.
**Impact portfolio** : maximal — le repo devient enfin ce que son nom promet.

### 1.1 — Setup branche + dépendance `cryptography` (15 min)
- [x] `git checkout -b feat/security-hardening` (rester en local, push à la fin de la phase)
- [x] Ajouter `cryptography>=42.0` dans `requirements.txt`
- [x] `pip install -r requirements.txt` dans le venv Docker

### 1.2 — Utilitaire d'encryption (~1h)
- [x] Créer `app/documents/encryption.py`
- [x] Implémenter `encrypt_bytes(data: bytes) -> bytes` via `cryptography.Fernet`
- [x] Implémenter `decrypt_bytes(data: bytes) -> bytes`
- [x] Clé maître en env var `VAULT_ENCRYPTION_KEY` (base64 32 bytes)
- [x] Ajouter la variable dans `.env.example` avec commentaire "generate with `Fernet.generate_key()`"

**Implémentation type** :
```python
# app/documents/encryption.py
from cryptography.fernet import Fernet
from django.conf import settings

_fernet = Fernet(settings.VAULT_ENCRYPTION_KEY.encode())

def encrypt_bytes(data: bytes) -> bytes:
    return _fernet.encrypt(data)

def decrypt_bytes(token: bytes) -> bytes:
    return _fernet.decrypt(token)
```

### 1.3 — Document model : ajouter hash + encrypted flag (~30 min)
- [x] Ajouter champ `sha256 = models.CharField(max_length=64, blank=True)` — stocker le hash du contenu ORIGINAL (avant chiffrement)
- [x] Ajouter champ `is_encrypted = models.BooleanField(default=True)` — flag pour rétro-compat éventuelle
- [x] Ajouter champ `original_size = models.PositiveBigIntegerField(default=0)` — pour analytics + validation
- [x] `python manage.py makemigrations documents` → générer migration
- [x] Revoir la migration pour ajouter un `default` cohérent aux champs sur rows existantes

### 1.4 — Modifier upload : chiffrer + hasher avant save (~1h)
- [x] Dans `DocumentListView.post()`, avant `serializer.save()` :
  - Lire les bytes du fichier
  - Calculer `sha256 = hashlib.sha256(bytes).hexdigest()`
  - Chiffrer les bytes via `encrypt_bytes()`
  - Remplacer le contenu du `InMemoryUploadedFile` par les bytes chiffrés
  - Passer `sha256`, `original_size`, `is_encrypted=True` à `serializer.save()`
- [x] Adapter le serializer pour marquer ces champs `read_only` (computed backend, pas fournis par le client) — `is_active` a dû être ajouté ici aussi : un `BooleanField` DRF absent d'un formulaire multipart est traité comme `False` (sémantique "checkbox HTML"), pas comme "utiliser le default du modèle" → tout upload créait un document désactivé.

### 1.5 — Modifier download : déchiffrer + verify hash (~1h)
- [x] Dans `DocumentDownloadView.get()` :
  - Lire les bytes chiffrés depuis `document.file`
  - Déchiffrer via `decrypt_bytes()` (avec catch de `cryptography.fernet.InvalidToken` → 500 propre si le blob chiffré est corrompu, avant même la comparaison de hash)
  - Recalculer sha256 des bytes déchiffrés
  - Comparer avec `document.sha256` → si mismatch, `HTTP 500` (fichier corrompu ou tampered)
  - Return `HttpResponse` avec les bytes déchiffrés + `Content-Disposition: attachment`

### 1.6 — Rate limiting DRF (~30 min)
- [x] Dans `settings.py`, ajouter :
```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'upload': '10/min',
        'download': '30/min',
        'user': '100/hour',
    },
}
```
- [x] Créer 2 classes custom `UploadRateThrottle(UserRateThrottle)` avec `scope='upload'` et `DownloadRateThrottle` avec `scope='download'`
- [x] Attacher aux views : `throttle_classes = [UploadRateThrottle]` sur `DocumentListView.post` (via `get_throttles()` pour ne pas throttler le `GET` de la même view), `DownloadRateThrottle` sur `DocumentDownloadView`

### 1.7 — Audit hooks dans les views (~1h)
Les modèles `AuditLog` existent mais aucune view ne loggue. À corriger :
- [x] Créer helper `app/documents/audit.py` avec `log_action(user, action, document, request, details=None)`
- [x] Appeler le helper dans :
  - `DocumentListView.post` → action `upload`
  - `DocumentDownloadView.get` → action `download`
  - `DocumentDeactivateView` → action `deactivate`
  - `DocumentActivateView` → action `activate`
- [x] Capturer `ip_address` via `request.META.get("REMOTE_ADDR")` (attention derrière proxy → `X-Forwarded-For`)
- [x] Capturer `user_agent` via `request.META.get("HTTP_USER_AGENT", "")`

### 1.8 — README complet (~1h)
- [x] Remplacer le README d'1 ligne par un fichier structuré avec :
  - Header + tagline
  - Threat model court (qui protège-t-on contre quoi)
  - Architecture (diagram texte : Client → API → Encrypt → Storage → Audit)
  - Features implémentées (avec ✅)
  - Tech stack (Django, DRF, PostgreSQL, cryptography, boto3...)
  - Setup local (docker-compose up, migrate, createsuperuser)
  - Variables d'env expliquées
  - API endpoints (table : POST /docs/, GET /docs/, GET /docs/{id}/download, etc.)
  - Rate limits documentés
  - License

**Status Phase 1** : ✅ Complète (2026-08-25) — testée de bout en bout via l'API réelle (register → verify → login → upload chiffré → download déchiffré+vérifié → tampering détecté → rate limiting → audit log), voir Session log ci-dessous.

---

## 🧪 Phase 2 — Tests solides (~1 soirée)

**Durée** : 1 soirée (2-3h).
**Impact portfolio** : recruteur voit "80% coverage" badge = crédibilité immédiate.

### 2.1 — Setup pytest + coverage (~15 min)
- [x] Créer `pytest.ini` — **déplacé dans `app/pytest.ini`** (le fichier `pytest.init` original était à la racine du repo, hors du dossier `app/` monté dans le conteneur Docker (`volumes: ./app:/app`) : il n'était jamais visible par pytest, donc jamais lu, et 0 test n'était collecté malgré des tests déjà écrits dans `users/tests.py`) :
```
[pytest]
DJANGO_SETTINGS_MODULE = app.settings
python_files = test_*.py tests.py
addopts = --cov=users --cov=documents --cov-report=term-missing --cov-fail-under=80
```
  (`--cov=app` du roadmap original ne couvrirait que `app/settings.py`/`urls.py` — la logique métier est dans `users`/`documents`)
- [x] Vérifier que `pytest`, `pytest-django`, `factory-boy`, `Faker` sont bien dans requirements.txt — `pytest-cov` manquait, ajouté
- [x] `app/.coveragerc` pour exclure les migrations du calcul de couverture

### 2.2 — Factories (~30 min)
- [x] Créer `app/tests/factories.py`
- [x] `UserFactory` (email + firstname + lastname + is_verified=True, mot de passe hashé via `create_user`)
- [x] `DocumentFactory` (owner via SubFactory + fichier mock via `factory.django.FileField`)

### 2.3 — Tests upload/download avec encryption (~1h)
- [x] `test_upload_encrypts_file` — vérifier que le fichier stocké n'est PAS égal au fichier envoyé (bytes chiffrés)
- [x] `test_download_returns_original_bytes` — round-trip encrypt → decrypt = original
- [x] `test_sha256_is_computed_on_upload` — hash présent en DB après upload
- [x] `test_download_detects_corrupted_ciphertext` + `test_download_detects_content_substitution` — les deux chemins d'intégrité testés séparément (échec HMAC Fernet vs. mismatch SHA-256 sur un contenu substitué mais validement re-chiffré)
- [x] `test_upload_rejects_bad_extension` — fichier `.exe` refusé par validators
- [x] `test_upload_rejects_too_large` — fichier > MAX_UPLOAD_SIZE refusé
- [x] `test_uploaded_document_is_active_by_default` — régression pour le bug `is_active` (Phase 0/1) trouvé pendant l'implémentation

### 2.4 — Tests permissions (~30 min)
- [x] `test_user_a_cannot_download_user_b_document` (403 Forbidden)
- [x] `test_shared_user_can_download` (200 OK)
- [x] `test_owner_can_deactivate` (200 OK)
- [x] `test_non_owner_cannot_deactivate` (403)

### 2.5 — Tests rate limiting (~30 min)
- [x] `test_upload_throttle` — 11e upload dans la minute → 429 Too Many Requests
- [x] `test_download_throttle` — 31e download → 429
- [x] `app/conftest.py` : fixture `autouse` qui vide le cache Django (LocMemCache, partagé tout le process pytest) avant/après chaque test — sans ça, les compteurs de throttle fuient entre tests et cassent des tests non liés

### 2.6 — Tests audit hooks (~30 min)
- [x] `test_upload_creates_audit_log` — après upload, 1 AuditLog avec action=upload
- [x] `test_download_creates_audit_log` — idem
- [x] `test_audit_log_captures_ip_and_user_agent`

### 2.7 — Run + fix (~30 min)
- [x] `pytest` — **84.02% coverage**, seuil 80% atteint
- [x] 20/20 tests passent, suite stable sur plusieurs runs consécutifs

**Status Phase 2** : ✅ Complète (2026-08-26)

---

## ☁️ Phase 3 — Cloud & polish (~1 soirée)

**Durée** : 1 soirée (2-3h).
**Impact portfolio** : signal maturité cloud + Swagger UI belle = points recruteur.

### 3.1 — S3 presigned URLs pour download (~1h)
- [x] **Décision (validée avec l'utilisateur)** : Fernet app-level conservé, **pas de S3**. Une URL présignée sert le blob directement depuis S3 au client, en court-circuitant la vue Django qui déchiffre — incompatible tel quel avec le chiffrement applicatif déjà en place et testé (Phase 1+2). Décision documentée dans le README (`## Décision : stockage local + Fernet, pas d'URLs présignées S3`).
- [x] `django-storages`/`boto3` retirés de `requirements.txt` (jamais importés dans le code, morts depuis le début du repo) — `drf-yasg` retiré aussi, même raison (jamais utilisé, `drf-spectacular` est le seul générateur OpenAPI du projet)
- [x] Helper `s3.py` — non créé, cohérent avec la décision ci-dessus

### 3.2 — Enrichir OpenAPI/Swagger (~1h)
- [x] `SPECTACULAR_SETTINGS` complété : DESCRIPTION détaillée, CONTACT, LICENSE, TAGS (`auth`, `documents`)
- [x] Chaque vue décorée avec `@extend_schema(tags=[...], summary=..., description=...)` (users + documents)
- [x] `help_text` ajouté sur les champs modèles (propagé automatiquement aux `ModelSerializer`) et sur les champs de serializers explicites (password, token, file, user_email...) — migrations générées (`documents/migrations/0003_*`, `users/migrations/0002_*`, aucun impact SQL réel, juste l'état Django)
- [x] `request=None` ajouté sur activate/deactivate (aucun corps de requête) — supprime les warnings `unable to guess serializer` qui apparaissaient dans les logs
- [x] `/api/docs/` vérifié : tags `auth`/`documents` bien séparés, tous les endpoints ont summary + description. Pas de tag "audit" : il n'existe pas d'endpoint audit exposé (AuditLog n'a pas de vue), donc pas de tag fabriqué pour un endpoint qui n'existe pas.
- Corrections trouvées en marge (remontées par l'usage réel de Swagger UI, cf. Session log) : `COMPONENT_SPLIT_REQUEST` (bouton d'upload absent) et retrait de `FormParser` (upload vide si le mauvais content-type était sélectionné)

### 3.3 — Polish Docker Compose (~30 min)
- [x] `docker compose down` (complet, réseau+conteneurs supprimés) puis `docker compose up -d` depuis zéro : boot propre, migrations appliquées automatiquement, aucune intervention manuelle
- [x] `docker-compose.override.yml` — **non créé**, délibérément : le `docker-compose.yml` actuel n'a qu'une seule variante (pas de fichier prod séparé), et monte déjà `./app:/app` en volume — le hot-reload (`StatReloader`) fonctionne déjà nativement, observé tout au long de cette session à chaque edit de code. Un override dupliquerait le même mount sans rien y gagner ; le split base/override aura du sens quand un compose prod distinct apparaîtra (Phase 4)

### 3.4 — Petits diagrams pour README (~30 min)
- [x] Déjà fait pendant la Phase 1 (`## Architecture` du README) : flows ASCII Upload et Download

**Status Phase 3** : ✅ Complète (2026-08-26)

---

## 🚀 Phase 4 — CI/CD + deploy demo (~1-2 soirées)

**Durée** : 1-2 soirées.
**Impact portfolio** : badge vert dans le README = "ce dev est pro". Deploy demo = "et il sait mettre en prod".

### 4.1 — GitHub Actions CI (~1h)
- [x] Créé `.github/workflows/ci.yml` — 3 jobs séparés (`lint`, `typecheck`, `test`) plutôt qu'un seul, pour un statut plus lisible par échec
- [x] Jobs : lint (`ruff==0.6.9`), type (`mypy==1.11.2`), test (`pytest` + service Postgres 14)
- [x] Trigger : `push`/`pull_request` sur `main`
- [x] Badge ajouté dans le README
- **Validé empiriquement avant de committer** (pas juste écrit et espéré) :
  - `ruff check .` : 98 erreurs avec la dernière version de ruff (dont beaucoup de `RUF012` sur des patterns DRF idiomatiques comme `permission_classes = [...]`, non pertinentes ici) → pinné `ruff==0.6.9` dont le rule-set par défaut est plus proche de Pyflakes/pycodestyle classique. Ramené à 7 erreurs réelles (imports inutilisés + 1 import mal placé + 1 redéfinition), toutes pré-existantes dans le squelette original (pas introduites pendant cette session) → corrigées (`documents/admin.py`, `users/admin.py`, `users/models.py` avait `from django.db import models` importé deux fois, `users/utils.py`, `users/views.py`, `app/settings.py`)
  - `mypy --ignore-missing-imports --exclude 'migrations/'` : 1 seule erreur, dans une migration auto-générée (`dependencies: list[...]` non annotable utilement) → migrations exclues du check
  - **Bug de CI trouvé avant qu'il ne casse la CI** : `pip install -r requirements.txt` sur un environnement `python:3.11-slim` vierge (simulant un runner GitHub) échoue — `psycopg2` et `Pillow` compilent depuis les sources (pas de wheel précompilé pour cette combo) et ont besoin de `libpq-dev`/`libjpeg-dev`/`zlib1g-dev`, absents par défaut. Reproduit le même besoin que le `Dockerfile` (`build-essential libpq-dev libjpeg-dev zlib1g-dev libmagic1`) et ajouté à l'étape `Install system dependencies` des jobs `typecheck`/`test`. Re-vérifié : `pip install` réussit proprement avec la liste complète.
- Créé `requirements-dev.txt` (ruff/mypy/bandit/detect-secrets/pre-commit, séparé de `requirements.txt` pour ne pas alourdir l'image de prod)

### 4.2 — Pre-commit config (~30 min)
- [x] Créé `.pre-commit-config.yaml` avec ruff, mypy, bandit, detect-secrets (mêmes versions pinnées que la CI)
- [x] `bandit -r users documents app` (hors migrations/tests) : **aucun problème** — codebase clean
- [x] `.secrets.baseline` généré via `detect-secrets scan` : 1 secret détecté (`users/tests.py:17`, mot de passe factice `'SecurePass123!'` dans un fixture de test) — faux positif attendu, absorbé dans la baseline
- [x] **`pre-commit run --all-files` exécuté réellement** (pas juste écrit) sur les 4 hooks → les 4 passent au premier run
- [x] Setup documenté dans le README (nouvelle section "Qualité du code")

### 4.3 — Deploy demo (~1h, OPTIONNEL)
Choix : **Render** (le plus simple, free tier) ou **Fly.io** (plus pro, free tier). Pas démarré — nécessite un compte Render/Fly.io côté utilisateur, que je ne peux pas créer moi-même. Le stockage S3 (déjà branché et vérifié en amont, cf. session précédente) lève le principal obstacle technique (filesystem éphémère de Render) ; reste à décider Render vs Fly.io, connecter le repo, configurer les variables d'env en prod, et déployer.
- [ ] Créer compte + connecter le repo
- [ ] Configurer variables d'env (DATABASE_URL, VAULT_ENCRYPTION_KEY, SECRET_KEY, USE_S3 + AWS_*, etc.)
- [ ] Deploy
- [ ] Ajouter bouton "Try demo" dans README avec URL
- [ ] Ajouter compte de démo (readonly ou reset quotidien) pour recruteurs

**Status Phase 4** : 🟡 4.1 + 4.2 complètes (2026-08-27), 4.3 en attente (nécessite une action utilisateur)

---

## 📓 Session log (mise à jour à chaque session)

- **2026-08-24** : ROADMAP créé. Audit du code existant terminé. Phase 1 démarre bientôt.
- **2026-08-25** : Branche `feat/security-hardening` créée en local (pas encore pushée). Phase 0 (fondations, hors roadmap) + Phase 1 complètes — voir détail des bugs corrigés dans la section Phase 0 ci-dessus. Tout testé de bout en bout via `docker compose up` + `curl` sur l'API réelle (pas de tests automatisés — c'est l'objet de la Phase 2). Le repo boot maintenant proprement (`docker compose up`), les fichiers sont chiffrés at-rest, l'intégrité SHA-256 est vérifiée au download, le rate limiting et l'audit trail fonctionnent.
  - Reste des données de test dans la DB locale (uploads `rate1.txt`…`rate10.txt`, un fichier volontairement altéré) — à nettoyer si besoin (`docker compose down -v` puis `migrate` relance une DB propre).
  - **Prochaine étape** : Phase 2 (tests pytest — factories, upload/download/encryption, permissions, throttling, audit ; viser ≥80% coverage). Le ROADMAP recommande de faire les tests avant la Phase 3 (S3/Swagger) car ils protègent les refactors.
  - Pas encore pushé sur le remote — à faire quand la Phase 2 (au moins) sera là, ou plus tôt si voulu.
- **2026-08-26** : Deux bugs post-Phase 1 remontés par l'usage réel de Swagger UI, corrigés :
  - `file` documenté en `format: uri` (sortie) au lieu de `format: binary` (entrée) car `DocumentSerializer` était partagé entre `request=` et `responses=` dans `@extend_schema` → pas de bouton d'upload dans Swagger. Fixé via `SPECTACULAR_SETTINGS['COMPONENT_SPLIT_REQUEST'] = True`.
  - `DocumentListView` acceptait aussi `FormParser` (url-encoded) en plus de `MultiPartParser`, donc Swagger proposait un content-type qui ne peut pas transporter de fichier binaire → upload vide. `FormParser` retiré (aucune valeur pour un endpoint qui n'accepte que des fichiers).
  - Phase 2 complète dans la foulée : tests pytest (factories, encryption, intégrité, permissions, throttling, audit), 20/20 passent, 84% coverage. Bug de fond trouvé en cours de route : `pytest.init` était à la racine du repo, jamais monté dans le conteneur Docker → jamais lu par pytest, 0 test collecté même si `users/tests.py` en contenait déjà. Déplacé/renommé en `app/pytest.ini`.
  - **Prochaine étape** : Phase 3 (S3 presigned URLs ou décision Fernet-only, polish Swagger/OpenAPI, docker-compose.override.yml, diagrams README) — à démarrer sur demande.
  - Phase 3 complète dans la foulée (même session) : décision Fernet/pas de S3 validée avec l'utilisateur et documentée dans le README ; `django-storages`/`boto3`/`drf-yasg` retirés (dépendances mortes) ; OpenAPI enrichi (tags `auth`/`documents`, summary/description sur chaque endpoint, `help_text` sur les champs modèles + serializers, migrations générées pour l'état Django) ; `docker compose down && up` vérifié propre depuis zéro ; diagrams déjà présents dans le README depuis la Phase 1. Pas d'override docker-compose créé (justifié dans la section Phase 3 — pas de variante prod distincte pour l'instant, le hot-reload marche déjà nativement).
  - Suite des 20 tests toujours verte après ces changements (84% coverage, inchangé).
  - **Prochaine étape** : Phase 4 (CI/CD GitHub Actions, pre-commit, deploy demo optionnel) — nécessitera des décisions/comptes externes (Render/Fly.io) que l'utilisateur devra fournir. À démarrer sur demande.
  - **Gap hors-roadmap comblé** : `AuditLog`/`AuditLogSerializer` existaient depuis le début mais n'étaient exposés nulle part (pas d'endpoint, pas enregistré dans le Django admin) — le journal RGPD Article 30 se remplissait sans que personne (utilisateur ou admin) puisse le consulter. Ajouté :
    - `GET /api/documents/{id}/audit/` — historique d'un document, **propriétaire uniquement** (nouvelle permission `IsDocumentOwner` dans `documents/permissions.py` : un utilisateur partagé peut lire le document mais pas son audit trail, qui révélerait IP/user-agent d'autres personnes, dont le propriétaire)
    - `GET /api/audit/` — historique de l'utilisateur connecté, tous documents confondus
    - 4 tests ajoutés (owner OK, non-owner 403, shared-user 403, historique filtré par utilisateur) → 24/24 passent, 85% coverage
    - Vérifié manuellement via curl : remonte bien tout l'historique réel accumulé pendant les tests manuels des phases précédentes
  - **Gap hors-roadmap comblé** : même constat pour le partage — `DocumentShare`/`DocumentShareSerializer`/`SharedUserSerializer`/`DocumentShareDetailSerializer` existaient depuis le début (et `IsOwnerOrShared` savait déjà lire `shared_with`), mais aucun endpoint ne permettait de créer un partage via l'API. Ajouté :
    - `POST /api/documents/{id}/share/` (créer/réactiver un partage) et `GET .../share/` (lister les partages actifs) — propriétaire uniquement (`IsDocumentOwner`)
    - `POST /api/documents/{id}/unshare/` (révoquer) — propriétaire uniquement
    - Actions `share`/`revoke` journalisées dans `AuditLog` (choices déjà prévues dans le modèle, jamais utilisées jusqu'ici)
    - **Bug de sécurité réel trouvé par les tests** : `IsOwnerOrShared.has_object_permission` interrogeait `obj.shared_with.filter(id=request.user.id)` — le manager M2M via `through=DocumentShare` ne fait qu'un JOIN sur la table pivot et ignore complètement la colonne `is_active`. Résultat : révoquer un partage (`unshare/`) ne coupait PAS l'accès réel, une ligne `DocumentShare` révoquée continuait à autoriser le download. Corrigé en interrogeant directement `DocumentShare.objects.filter(document=obj, shared_with=request.user, is_active=True)`. Confirmé par un test qui échouait avant le fix (`test_owner_can_unshare`) et par un test manuel curl complet (partage → accès 200 → révocation → accès 403).
    - 9 tests ajoutés → 33/33 passent, 88% coverage
  - **Suite à la question utilisateur** "partage avec plusieurs users à la fois ?" : `DocumentShareSerializer.user_email` (singulier) remplacé par `user_emails` (liste). Sémantique **best-effort** choisie avec l'utilisateur : chaque email est traité indépendamment, un email invalide n'empêche pas le partage/révocation avec les autres — la réponse liste un statut par email (`created`/`reactivated`/`revoked`/`error`+`detail`), plutôt qu'un tout-ou-rien en 400. S'applique symétriquement à `share/` et `unshare/`. 3 tests ajoutés (partage multiple, best-effort avec un email invalide, révocation d'un email inconnu) → 36/36 passent, 89% coverage. `README.md` : table des endpoints mise à jour (elle n'avait jamais été complétée avec audit/share/unshare, et la colonne auth d'activate/deactivate était imprécise — "owner/shared" alors que `IsOwnerOrShared` n'autorise en écriture que le propriétaire).
  - **Gap signalé par l'utilisateur** : "je ne vois pas le document partagé avec moi dans `/api/documents/`" — confirmé, `DocumentListView.get()` ne filtrait que par `owner=request.user`, jamais les documents partagés (alors que `IsOwnerOrShared` y donne bien accès en direct via `/api/documents/{id}/`). Corrigé : la liste inclut maintenant `owner=request.user` OU (`shares__shared_with=request.user` ET `shares__is_active=True`), via `Q()` + `.distinct()`. 3 tests ajoutés (le document partagé apparaît chez le destinataire, un utilisateur non lié ne le voit pas, un partage révoqué disparaît de la liste) → 39/39 passent, 89.6% coverage. Vérifié manuellement via curl.
  - **Demande utilisateur** : "configure l'upload S3 avec boto" — motivée par un déploiement Render prévu (filesystem éphémère, besoin d'un stockage externe persistant pour les fichiers uploadés). Clarifié avant d'implémenter (deux lectures possibles, une seule compatible avec le chiffrement applicatif déjà en place — cf. décision Phase 3.1) : **S3 comme backend de stockage physique uniquement**, pas d'upload direct client→S3 (qui court-circuiterait le chiffrement Fernet, puisque Django ne verrait jamais les bytes en clair). Implémenté :
    - `USE_S3` (défaut `False`) dans `app/app/settings.py` : bascule `DEFAULT_FILE_STORAGE` vers `storages.backends.s3boto3.S3Boto3Storage` si activé (+ `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_STORAGE_BUCKET_NAME`/`AWS_S3_REGION_NAME`, requis seulement dans ce cas — échoue vite et clairement au boot si `USE_S3=True` sans credentials, testé). `AWS_QUERYSTRING_AUTH=False` : toujours pas d'URL présignée, cohérent avec la décision Phase 3.1.
    - `django-storages`/`boto3` remis dans `requirements.txt` (retirés en Phase 3 comme code mort — plus mort maintenant qu'ils sont réellement utilisés)
    - Aucun changement à la logique métier (`documents/encryption.py`, `views.py`) : l'abstraction `Storage`/`FieldFile` de Django absorbe le changement de backend, le code applicatif ne sait pas où atterrit le blob
    - Vérifié : `manage.py check` passe avec des credentials factices (le backend s'importe et se configure sans erreur, boto3 ne se connecte qu'au premier accès réel) ; suite de tests (39/39) inchangée avec `USE_S3=False` (défaut)
    - **Non vérifiable de bout en bout sans bucket réel** — nécessite les credentials AWS de l'utilisateur. `.env.example` documenté, README mis à jour (section décision + tableau des variables d'env)
    - **Limite connue documentée** : les tests d'intégrité qui tamperent le fichier stocké (`test_download_detects_corrupted_ciphertext`, `test_download_detects_content_substitution`) utilisent `document.file.path`, une API propre à `FileSystemStorage` — absente sur `S3Boto3Storage`. Sans impact tant que les tests tournent avec `USE_S3=False` (cas actuel), mais à adapter si un environnement de test S3 est mis en place un jour.
  - **Credentials AWS ajoutées par l'utilisateur** (édition manuelle de `.env`/`settings.py`) — vérifiées à sa demande. Deux bugs trouvés et corrigés dans son édition de `settings.py` :
    - `AWS_S3_CUSTOM_DOMAIN`/`STATIC_URL`/`MEDIA_URL` (pointant vers S3) étaient placés **hors** du bloc `if USE_S3:`, alors que `AWS_STORAGE_BUCKET_NAME` n'est défini que dedans → `NameError` au boot dès que `USE_S3=False` (le défaut). Confirmé par `manage.py check` avant fix.
    - `STATIC_ROOT`/`MEDIA_ROOT` avaient disparu du fichier, et `STATIC_URL` était systématiquement basculé vers S3 alors que seul `DEFAULT_FILE_STORAGE` (médias) était configuré, pas de storage S3 pour les statiques — aurait cassé les assets Django admin/Swagger. Corrigé : `STATIC_URL` reste local (servi par `whitenoise`, déjà en dépendance), seul `MEDIA_URL` bascule vers S3 quand `USE_S3=True`.
    - `import os` (ajouté, jamais utilisé) retiré.
    - **Connectivité S3 réelle vérifiée** : écriture + lecture + suppression d'un fichier de test sur le bucket via `default_storage`, contenu confirmé identique. Suite de tests (39/39) toujours verte avec `USE_S3=False` (défaut, .env non modifié pour l'activer).
    - **Signalé à l'utilisateur, pas corrigé unilatéralement** : le nom du bucket (`awscsirtmedia`) laisse penser à une réutilisation d'un bucket d'un autre projet (`csirts-app-api`) — à confirmer/isoler avant un vrai déploiement, pour éviter de mélanger les données de deux applications non liées.
  - **S3 activé pour de vrai** — l'utilisateur a créé un bucket dédié (`aws-vault-media`, séparé du bucket CSIRT, dans la console AWS avec guidage pas-à-pas) et demandé de finaliser la connexion + activer `USE_S3=True`. Un 3ᵉ bug trouvé au passage : `AWS_DEFAULT_ACL = 'private'` aurait fait échouer tout upload (`AccessControlListNotSupported`) sur un bucket créé avec les réglages par défaut actuels d'AWS ("ACLs disabled" / Bucket owner enforced, recommandé depuis 2023) — corrigé en `AWS_DEFAULT_ACL = None` (la confidentialité vient du Block Public Access du bucket + de l'absence d'URL présignée, pas d'une ACL par objet).
    - **Dette de test payée** : la limitation documentée plus haut (`document.file.path` indisponible sur S3) a été corrigée pour de bon — les deux tests de tampering utilisent maintenant un helper `overwrite_stored_file()` basé sur l'API `Storage` générique de Django (`storage.delete()` + `storage.save()`) au lieu du filesystem direct. Fonctionne identiquement en local et sur S3 ; plus de dépendance au backend.
    - Vérifié à plusieurs niveaux : connectivité brute (écriture/lecture/suppression) sur le bucket final ; les 3 tests `TestDownloadIntegrity` (dont les 2 anciennement dépendants de `.path`) exécutés **contre le vrai bucket S3** (`USE_S3=True`) → passent ; flux complet via l'API réelle (upload chiffré → stocké sur S3 sous forme de token Fernet illisible, vérifié directement → download → contenu déchiffré correct).
    - **Gotcha découvert et documenté** : les tests pytest tournent dans une transaction DB annulée à la fin (rollback), mais les écritures S3 ne font PAS partie de cette transaction — des fichiers de test orphelins restent sur le bucket après un run avec `USE_S3=True`. Nettoyé manuellement après vérification. À garder en tête si des tests tournent un jour contre S3 en routine (CI) : soit les exclure de ce mode, soit ajouter un nettoyage explicite.
    - `.env` local : `USE_S3=True` + bucket `aws-vault-media` actifs. `docker compose up` relancé, vérifié propre.
- **2026-08-27** : Phase 4.1 (CI GitHub Actions) + 4.2 (pre-commit) complètes, voir détail dans la section Phase 4 ci-dessus. Tout validé empiriquement avant d'être committé (pas juste écrit) : `ruff`/`mypy`/`bandit`/`detect-secrets` exécutés en local avec les mêmes versions que la CI, `pip install -r requirements.txt` simulé sur un environnement `python:3.11-slim` vierge pour attraper un problème de dépendances système qui aurait fait échouer la CI dès le premier run (`psycopg2`/`Pillow` compilent depuis les sources, besoin de `libpq-dev`/`libjpeg-dev`/`zlib1g-dev`). Suite de tests toujours verte (39/39, 89.6% coverage) après tous les nettoyages ruff.
  - **Prochaine étape** : Phase 4.3 (déploiement, optionnel) — bloquée sur une décision + un compte externe (Render ou Fly.io) côté utilisateur. Rien d'autre à faire de mon côté avant ça.
- **2026-08-28** : Ajout d'un **scan anti-malware (ClamAV)** — extension hors-roadmap demandée par l'utilisateur, motivée par le portfolio (les uploads sans scan sont une lacune évidente pour un "secure vault"). Choix de design :
  - **Scan synchrone dans la vue**, pas de Celery — cohérent avec la simplicité du reste du projet (`clamd instream` sur ≤ 10 MB se compte en dizaines de ms, pas de bénéfice réel à faire de l'async pour ce volume). Isolé dans `app/documents/malware.py` : `scan_bytes(data: bytes) -> None`, lève `MalwareError` si infecté OU si le daemon est activé mais injoignable.
  - **Scan AVANT chiffrement** : sinon on ne scannerait qu'un blob Fernet opaque, illisible par n'importe quel moteur AV. Placé entre `uploaded_file.read()` et le calcul SHA-256 dans `DocumentListView.post()`.
  - **Fail-closed** : si `CLAMAV_ENABLED=True` et daemon down → 400 `MALWARE_DETECTED`. On ne stocke jamais un fichier non-vérifié.
  - **Désactivé par défaut** (`CLAMAV_ENABLED=False`) : dev/CI restent verts sans daemon (`scan_bytes` court-circuite immédiatement). Activation opt-in en prod via env var.
  - **Docker** : service `clamav` ajouté à `docker-compose.yml` (image officielle `clamav/clamav:1.3`, port 3310, volume persistant pour la signature DB, healthcheck). `docker-compose.yml` inchangé côté app à part `depends_on: - clamav`.
  - **Tests** : `TestMalwareScanning` (4 tests) dans `app/documents/tests.py` — utilise le signature EICAR standard, mocke `documents.views.scan_bytes` pour ne pas dépendre d'un vrai clamd en CI. Couvre : infecté rejeté, scanner down rejeté (fail-closed), fichier clean accepté, scan désactivé court-circuite. La 4ᵉ appelle `scan_bytes` réellement pour vérifier le no-op quand `CLAMAV_ENABLED=False` — c'est le seul chemin non-mocké.
  - README mis à jour (threat model + diagramme upload + tableau features + nouvelle section "Scan anti-malware (ClamAV)" + variables d'env). `.env.example` + `requirements.txt` (`clamd==1.0.2`) alignés.
  - **Validation empirique effectuée** :
    - Suite pytest complète verte : **46 passed, 90.39% coverage** (au-dessus du gate 80%), `malware.py` à **100%**.
    - Bug de contamination inter-classes attrapé au passage : `TestMalwareScanning` (avec `@override_settings(CLAMAV_ENABLED=True)`) laissait fuiter l'état vers `TestUploadEncryption` → 5 tests en ERROR dans le run complet, tous passants en isolé. Résolu par une fixture autouse `_disable_clamav_by_default` dans `conftest.py` qui force `settings.CLAMAV_ENABLED = False` avant chaque test (via la fixture `settings` de pytest-django). Ce pattern immunise aussi les futures features flag-driven contre le même piège.
    - **Test end-to-end réel** : `docker compose --profile scan up clamav` → freshclam ~5 min → upload d'un fichier EICAR (généré dans le container via `printf` pour contourner Windows Defender qui supprime le fichier au repos, puis `docker compose cp` vers le host après exclusion Defender du dossier projet) via Swagger UI → réponse `400 MALWARE_DETECTED` avec `detail: "Malware detected: Win.Test.EICAR_HDB-1"`. Confirmé côté user.
    - **Découverte accessoire** : le pipeline de validation est bien **ordonné en profondeur** (extension → magic bytes → taille → scan → hash → chiffrement). Un `.com` (extension refusée) se fait rejeter avant même de consommer le scan CPU — architecture propre observée à l'occasion du test EICAR.

_(à chaque session, ajouter : date, ce qui a été fait, où on s'est arrêté, prochaine étape)_

---

## 🧭 Notes de conversation

### Décisions design
- **Encryption at rest** : Fernet (AES-128 CBC + HMAC SHA-256) via `cryptography` library. Une clé maître par instance (stockée en env var), pas de key rotation dans v1. Envisager KMS/Vault en v2.
- **Hash** : SHA-256 du contenu ORIGINAL (avant chiffrement) — permet de detecter tampering post-decrypt.
- **Rate limits** : `10/min upload`, `30/min download`, `100/h user`. Ajustable.
- **Audit** : GDPR Article 30 — action + user + resource + ip + user_agent + timestamp + details JSON.
- **Multi-tenant** : PAS pour v1 (portfolio piece single-tenant). À envisager v2 si le projet grossit.

### Points à ne PAS faire
- Pas de key rotation manuelle dans le code (complexité pour peu de valeur portfolio)
- Pas de chiffrement per-file avec dérivation KDF (overkill pour v1)
- Pas de sharing "public link" (hors scope initial)

### Pour reprendre plus tard sans moi
1. Ouvre ce fichier
2. Regarde le "Session log" pour voir où on s'est arrêté
3. Regarde la phase active + prochaine tâche non cochée
4. Chaque tâche a assez de détail pour être faite en autonomie
5. Si tu bloque, notes dans le "Session log" avec la question

---

## 🚦 Ordre d'attaque conseillé

1. **Phase 1.1 → 1.8** dans l'ordre — chacune dépend de la précédente (sauf 1.6 rate limit qui peut être fait en parallèle de 1.7)
2. **Phase 2** après Phase 1 finie
3. **Phase 3** après Phase 2 (les tests protègent les refactors S3)
4. **Phase 4** en dernier — nécessite tout ce qui précède pour être utile
