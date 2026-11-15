"""
`authorized_by` records who created a record (or, where a serializer lists
it explicitly, who performed the action, e.g. a guard booking a visitor in).
It always comes from the login, never from the request body.
"""

from estates.context import current_user


class StampAuthorizedBy:
    def get_extra_kwargs(self):
        extra = super().get_extra_kwargs()
        if self._has_audit_field():
            extra.setdefault("authorized_by", {})["read_only"] = True
        return extra

    def _has_audit_field(self):
        return any(f.name == "authorized_by" for f in self.Meta.model._meta.fields)

    def save(self, **kwargs):
        user = current_user()
        if user is not None and self._has_audit_field():
            listed = self.Meta.fields if isinstance(self.Meta.fields, (list, tuple)) else ()
            if self.instance is None or "authorized_by" in listed:
                kwargs.setdefault("authorized_by", user)
        return super().save(**kwargs)
