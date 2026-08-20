def unread_count(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    return {
        "unread_notification_count": user.notifications.filter(is_read=False).count(),
    }
