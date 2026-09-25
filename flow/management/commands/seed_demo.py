import secrets
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from flow.models import Activity, Membership, Project, Task, Workspace

class Command(BaseCommand):
    help = 'Create explicitly labelled local sample records, without touching existing accounts.'
    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG: raise CommandError('Sample seeding is for local development only.')
        User = get_user_model()
        if Workspace.objects.filter(name='Demo team · sample data').exists():
            self.stdout.write('Sample team already exists. Existing data and passwords were not changed.')
            return
        names = ['giri.demo', 'anu.demo', 'ravi.demo']
        if User.objects.filter(username__in=names).exists(): raise CommandError('A demo username is already in use; no accounts modified.')
        password = secrets.token_urlsafe(12)
        users = [User.objects.create_user(name, password=password, first_name=first) for name, first in zip(names, ['Giri', 'Anu', 'Ravi'])]
        team = Workspace.objects.create(name='Demo team · sample data')
        for index, user in enumerate(users): Membership.objects.create(workspace=team, user=user, role='leader' if index == 0 else 'member')
        project = Project.objects.create(workspace=team, name='Shopping Website · demo')
        examples = [('Build the login page', 'Design the sign-in form and handle incorrect passwords.', users[1], users[2], 'todo'),
            ('Create the shopping cart', 'Keep selected items together and calculate their total.', users[2], users[1], 'progress'),
            ('Review the product page', 'Sample review state for exploring the board. No GitHub event has been received.', users[1], users[2], 'review'),
            ('Build the home page', 'Sample completed record for exploring the board. Not evidence of a real merge.', users[0], users[1], 'done')]
        now = timezone.now()
        for title, desc, assignee, reviewer, status in examples:
            task = Task.objects.create(project=project, title=title, description=desc, assignee=assignee, reviewer=reviewer,
                creator=users[0], status=status, due_date=timezone.localdate() + timedelta(days=3),
                review_started_at=now if status == 'review' else None, review_cycle=1 if status == 'review' else 0,
                completed_at=now if status == 'done' else None)
            Activity.objects.create(project=project, task=task, text='Sample task created for the local demonstration.')
        (settings.LOCAL_DIR / 'demo-login.txt').write_text('Local sample accounts only\nUsernames: ' + ', '.join(names) + '\nPassword: ' + password + '\n')
        self.stdout.write('Created four labelled sample tasks. Local credentials are in .local/demo-login.txt.')
