from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from leadzen.accounts.service import create_account


class Command(BaseCommand):
    help = "Create the first LeadZen company administrator using a private password prompt."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", default="Zyene administrator")

    def handle(self, *args, **options):
        from leadzen.accounts.models import AccountProfile
        if AccountProfile.objects.filter(user__is_staff=True, user__is_active=True, deleted_at__isnull=True).exists():
            raise CommandError("An administrator already exists. Create additional accounts from /admin.")
        password = getpass("New administrator password (12+ characters): ")
        if password != getpass("Confirm password: "):
            raise CommandError("Passwords do not match")
        try:
            create_account(email=options["email"], name=options["name"], password=password, is_admin=True, require_change=False)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS("Administrator created. Sign in at https://leadzen.zyene.com/login."))
