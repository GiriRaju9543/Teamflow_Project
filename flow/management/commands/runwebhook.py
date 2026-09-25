from wsgiref.simple_server import make_server, WSGIRequestHandler
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.wsgi import get_wsgi_application
from flow.webhook_gateway import restricted_gateway


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


class Command(BaseCommand):
    help = 'Run the webhook-only development receiver on 127.0.0.1:8001.'

    def handle(self, *args, **options):
        settings.DEBUG = False
        application = restricted_gateway(get_wsgi_application())
        with make_server('127.0.0.1', 8001, application, handler_class=QuietHandler) as server:
            server.socket.settimeout(15)
            self.stdout.write('Webhook receiver ready at http://127.0.0.1:8001. Keep this terminal open.')
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                self.stdout.write('Webhook receiver stopped.')
