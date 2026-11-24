"""
"Delete" in the back office archives: the record is hidden from the lists but
kept, with its history (payments, visits, complaints). A record that other live
records still depend on is not archived; the office is told what to do first.

Before this, deleting an owner silently deleted all their homes, and deleting a
resident deleted the home they lived in.
"""

from rest_framework import status
from rest_framework.response import Response

from audit.log import name_of, record


class Refused(Exception):
    pass


def _home_label(home):
    return f"{home.address} (stand {home.stand.stand_number})"


def archive_stand(stand):
    from home.models import Home

    if Home.objects.filter(stand=stand, status=True).exists():
        raise Refused("A home is still on this stand. Remove the home first.")
    stand.status = False
    stand.save(update_fields=["status"])
    return f"Removed stand {stand.stand_number}"


def archive_home(home):
    from rentals.models import Lease

    if Lease.objects.filter(home=home, status=Lease.ACTIVE).exists():
        raise Refused("This home has a tenant on a lease. End the lease first.")
    home.status = False
    home.save(update_fields=["status"])
    return f"Removed home {_home_label(home)}"


def archive_owner(owner):
    from home.models import Home

    homes = list(Home.objects.filter(owner=owner, status=True).select_related("stand")[:3])
    if homes:
        raise Refused("This owner still owns " + ", ".join(h.address for h in homes) + ". Give the homes a new owner first.")
    owner.status = False
    owner.save(update_fields=["status"])
    return f"Removed owner {name_of(owner)}"


def archive_resident(resident):
    """A resident who moved out: no longer linked to any home (the home becomes empty)."""
    from home.models import Home
    from parameters.models.models_home_status import HomeStatus
    from rentals.models import Lease

    if Lease.objects.filter(tenant=resident, status=Lease.ACTIVE).exists():
        raise Refused("This person is a tenant on a lease. End the lease first.")
    vacant = HomeStatus.objects.filter(name__iexact="Vacant", status=True).first() or HomeStatus.objects.filter(name__iexact="Unoccupied").first()
    moved = []
    for home in Home.objects.filter(resident=resident).select_related("stand"):
        home.resident = None
        if vacant:
            home.home_status = vacant
        home.save(update_fields=["resident", "home_status"])
        moved.append(home.address)
    resident.status = False
    resident.save(update_fields=["status"])
    return f"Removed resident {name_of(resident)}" + (f" (moved out of {', '.join(moved)})" if moved else "")


def archive_simple(obj, label):
    obj.status = False
    obj.save(update_fields=["status"])
    return label


def respond(obj, archive, *args):
    """Run an archive function and answer the request; record it in the history."""
    try:
        summary = archive(obj, *args)
    except Refused as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    record(f"{obj._meta.model_name}.removed", summary, obj, area="people")
    return Response(status=status.HTTP_204_NO_CONTENT)
