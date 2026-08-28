from rest_framework import permissions

from documents.models import DocumentShare


class IsOwnerOrShared(permissions.BasePermission):
    """Permission: Seul le propriétaire ou les users avec qui c'est partagé peuvent accéder"""

    def has_object_permission(self, request, view, obj):
        # Le propriétaire a tous les droits
        if obj.owner == request.user:
            return True

        # Les users avec qui c'est partagé peuvent lire — on interroge directement
        # DocumentShare.is_active (obj.shared_with.filter(...) ne fait qu'un JOIN sur
        # la table pivot et ignore is_active : une ligne révoquée continuerait sinon
        # à accorder l'accès).
        if request.method in permissions.SAFE_METHODS:
            return DocumentShare.objects.filter(
                document=obj, shared_with=request.user, is_active=True
            ).exists()

        return False


class IsDocumentOwner(permissions.BasePermission):
    """Le propriétaire uniquement — utilisé pour l'audit trail, qui expose
    IP/user-agent de tous les accès (y compris ceux des utilisateurs avec
    qui le document est partagé) et ne doit donc pas leur être visible."""

    def has_object_permission(self, request, view, obj):
        return obj.owner == request.user