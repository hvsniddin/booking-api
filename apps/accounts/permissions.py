from rest_framework import permissions


class IsAdminUserOrReadOnly(permissions.BasePermission):
    """
    Allow read-only requests for anyone, but only business admins / staff can modify.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_business_admin)


class IsBusinessAdmin(permissions.BasePermission):
    """
    Allows access only to admin / business owner users.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_business_admin)


class IsProviderUser(permissions.BasePermission):
    """
    Allows access to provider users or admins.
    """
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and (
                request.user.is_provider or request.user.is_business_admin
            )
        )


class IsBookingParticipantOrAdmin(permissions.BasePermission):
    """
    Customer who booked, provider assigned to booking, or business admin can view/modify booking.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_business_admin:
            return True
        if obj.customer_id == request.user.id:
            return True
        if obj.provider.user_id and obj.provider.user_id == request.user.id:
            return True
        return False
