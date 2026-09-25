from .models import Membership, Notification

def navigation(request):
    if not request.user.is_authenticated: return {}
    memberships = Membership.objects.filter(user=request.user).select_related('workspace')
    return {'memberships': memberships, 'unread_count': Notification.objects.filter(user=request.user, read=False).count(),
            'nav_page': request.resolver_match.url_name if request.resolver_match else ''}
