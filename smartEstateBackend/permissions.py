"""
Role-based access for Smart Estate.

Roles live on ``User.role``:
  * Admin - estate administrator, full access
  * Guard - gate security, works with visitors and the whitelist

Residents do not log in yet; the public resident portal may only book a
visitor, log a complaint and read reference lists.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

ROLE_ADMIN = "Admin"
ROLE_GUARD = "Guard"
ROLES = (ROLE_ADMIN, ROLE_GUARD)


def is_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.role == ROLE_ADMIN))


def is_staff_member(user):
    """Admin or Guard."""
    return bool(user and user.is_authenticated and (user.is_superuser or user.role in ROLES))


class IsAdminRole(BasePermission):
    message = "Only estate administrators can do this."

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsAdminOrGuard(BasePermission):
    message = "Only estate administrators and guards can do this."

    def has_permission(self, request, view):
        return is_staff_member(request.user)


class StaffReadAdminWrite(BasePermission):
    """Admins and guards can read; only admins can change."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return is_staff_member(request.user)
        return is_admin(request.user)


class PublicReadAdminWrite(BasePermission):
    """Anyone can read (reference lists for the resident portal); only admins can change."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return is_admin(request.user)


class PublicCreateStaffRead(BasePermission):
    """Anyone can create (resident portal bookings); only admins and guards can list."""

    def has_permission(self, request, view):
        if request.method == "POST":
            return True
        return is_staff_member(request.user)
