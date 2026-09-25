import time
from django.core.management.base import BaseCommand
from flow.services import run_once

class Command(BaseCommand):
    help = 'Process saved GitHub deliveries and create due in-app reminders.'
    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
    def handle(self, *args, **options):
        self.stdout.write('Teamflow automation worker running. Ctrl+C stops it.')
        try:
            while True:
                count = run_once()
                if count: self.stdout.write(f'Created {count} reminder(s).')
                if options['once']: break
                time.sleep(10)
        except KeyboardInterrupt:
            self.stdout.write('Worker stopped.')
