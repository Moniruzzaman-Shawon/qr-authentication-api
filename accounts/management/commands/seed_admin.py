from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from accounts.roles import ADMIN


class Command(BaseCommand):
    help = 'Create or update the initial Admin user from environment settings.'

    def handle(self, *args, **options):
        username = settings.INITIAL_ADMIN_USERNAME
        email = settings.INITIAL_ADMIN_EMAIL
        password = settings.INITIAL_ADMIN_PASSWORD

        if not password:
            self.stderr.write(
                self.style.ERROR(
                    'INITIAL_ADMIN_PASSWORD is not set. Refusing to create an admin '
                    'with a blank password.'
                )
            )
            return

        group, _ = Group.objects.get_or_create(name=ADMIN)
        user, created = User.objects.get_or_create(
            username=username, defaults={'email': email}
        )
        user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()
        user.groups.add(group)

        verb = 'Created' if created else 'Updated'
        self.stdout.write(self.style.SUCCESS(f'{verb} admin user "{username}".'))
