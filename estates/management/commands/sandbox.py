"""
Sandbox estates for testers.

  python manage.py sandbox create "Sandbox Estate"     new estate + sample data + admin and guard logins
  python manage.py sandbox create "Demo Rentals" --kind rental    a rental portfolio with tenants, leases and rent
  python manage.py sandbox agent "Demo Agents"         a managing agent with one of each and a login across both
  python manage.py sandbox tester <slug> --role Guard   another login
  python manage.py sandbox reset <slug>                 sample data back as new
"""

from django.core.management.base import BaseCommand, CommandError

from estates import sandbox_seed
from estates.models import Estate


class Command(BaseCommand):
    help = "Create and manage sandbox (demo) estates"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["create", "agent", "tester", "reset"])
        parser.add_argument("name", help="Estate name (create) or slug (tester, reset)")
        parser.add_argument("--role", default="Admin", choices=["Admin", "Guard"])
        parser.add_argument("--label", default="", help="e.g. a tester's first name")
        parser.add_argument("--kind", default="estate", choices=["estate", "rental"])

    def handle(self, action, name, role, label, kind, **options):
        if action == "agent":
            organisation, estates, logins = sandbox_seed.create_demo_agent(name)
            self.stdout.write(self.style.SUCCESS(f"Agent '{organisation.name}' created with: " + ", ".join(e.name for e in estates)))
            for r, username, password in logins:
                self.stdout.write(f"  {r:6} {username}  /  {password}")
            return
        if action == "create":
            estate, logins = sandbox_seed.create_sandbox(name, kind=kind)
            self.stdout.write(self.style.SUCCESS(f"Sandbox '{estate.name}' created. Portal: ?estate={estate.slug}"))
            for r, username, password in logins:
                self.stdout.write(f"  {r:6} {username}  /  {password}")
            return
        estate = Estate.objects.filter(slug=name, sandbox=True).first()
        if estate is None:
            raise CommandError(f"No sandbox estate with slug '{name}'.")
        if action == "tester":
            username, password = sandbox_seed.create_tester(estate, role, label)
            self.stdout.write(self.style.SUCCESS(f"{role} {username}  /  {password}"))
        else:
            sandbox_seed.reset(estate)
            self.stdout.write(self.style.SUCCESS(f"Sample data in '{estate.name}' reset."))
