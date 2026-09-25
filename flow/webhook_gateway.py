"""Restricted entry point for a temporary development tunnel."""
import re

PATH = re.compile(r'/hooks/github/[0-9a-fA-F-]{36}/')
MAX_BODY = 2_621_440


def restricted_gateway(application):
    def gateway(environ, start_response):
        def reject(status):
            start_response(status, [('Content-Type', 'text/plain'), ('Cache-Control', 'no-store')])
            return [b'Request rejected.']

        if not PATH.fullmatch(environ.get('PATH_INFO', '')):
            return reject('404 Not Found')
        if environ.get('REQUEST_METHOD') != 'POST':
            return reject('405 Method Not Allowed')
        try:
            size = int(environ.get('CONTENT_LENGTH') or '0')
        except ValueError:
            return reject('400 Bad Request')
        if size <= 0 or size > MAX_BODY:
            return reject('413 Payload Too Large')
        # Only the signed webhook view is reachable; never forward tunnel hosts.
        environ['HTTP_HOST'] = '127.0.0.1'
        return application(environ, start_response)
    return gateway
