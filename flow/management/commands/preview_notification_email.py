"""Generate a local email preview without contacting an email provider."""
from pathlib import Path
from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.core.management.base import BaseCommand, CommandError
from flow.models import Notification

class Command(BaseCommand):
    help = 'Save a notification email preview locally; never sends external email.'

    def add_arguments(self, parser):
        parser.add_argument('--notification', type=int)

    def handle(self, *args, **options):
        items = Notification.objects.select_related('user', 'task', 'task__project')
        item = items.filter(pk=options['notification']).first() if options['notification'] else items.order_by('-created_at', '-pk').first()
        if not item:
            raise CommandError('No matching notification exists. Create a review notification first.')
        destination = Path(settings.LOCAL_DIR) / 'email-previews'
        connection = get_connection('django.core.mail.backends.filebased.EmailBackend', file_path=str(destination))
        name = item.user.first_name or item.user.username
        body = (f'Hello {name},\n\n{item.text}\n\n'
                f'Project: {item.task.project.name}\nTask: {item.task.key} - {item.task.title}\n'
                f'Open task: http://127.0.0.1:8000/tasks/{item.task_id}/\n\n'
                'This is a local email preview. No email was sent.\nTeamflow\n')
        EmailMessage(subject=f'Teamflow: {item.task.key} notification', body=body,
                     from_email='Teamflow <preview@example.invalid>',
                     to=['recipient@example.invalid'], connection=connection).send()
        self.stdout.write(self.style.SUCCESS(f'Local preview saved in {destination}. No email sent; no task data changed.'))
