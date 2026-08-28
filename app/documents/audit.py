from documents.models import AuditLog


def _get_client_ip(request):
    forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(user, action, document, request, details=None):
    AuditLog.objects.create(
        user=user,
        user_email=user.email,
        action=action,
        document=document,
        document_name=document.name,
        ip_address=_get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', ''),
        details=details or {},
    )
