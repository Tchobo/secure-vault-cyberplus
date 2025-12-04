from rest_framework import permissions


class IsOwnerOrShared(permissions.BasePermission):
    """Permission: Seul le propriétaire ou les users avec qui c'est partagé peuvent accéder"""
    
    def has_object_permission(self, request, view, obj):
        # Le propriétaire a tous les droits
        if obj.owner == request.user:
            return True
        
        # Les users avec qui c'est partagé peuvent lire
        if request.method in permissions.SAFE_METHODS:
            return obj.shared_with.filter(id=request.user.id).exists()
        
        return False