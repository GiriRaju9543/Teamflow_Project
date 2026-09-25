from unittest import TestCase
from unittest.mock import Mock
from flow.webhook_gateway import restricted_gateway


class GatewayTests(TestCase):
    def test_only_sized_webhook_posts_reach_django(self):
        path = '/hooks/github/12345678-1234-1234-1234-123456789abc/'
        for target, method, size, expected in [
            ('/', 'GET', '0', '404'),
            ('/login/', 'POST', '2', '404'),
            (path, 'GET', '2', '405'),
            (path, 'POST', '9999999', '413'),
            (path, 'POST', 'bad', '400'),
        ]:
            app, response = Mock(), Mock()
            restricted_gateway(app)({'PATH_INFO': target, 'REQUEST_METHOD': method, 'CONTENT_LENGTH': size}, response)
            app.assert_not_called()
            self.assertTrue(response.call_args.args[0].startswith(expected))
        app, response = Mock(return_value=[b'ok']), Mock()
        environ = {'PATH_INFO': path, 'REQUEST_METHOD': 'POST', 'CONTENT_LENGTH': '2', 'HTTP_HOST': 'public.example'}
        self.assertEqual(restricted_gateway(app)(environ, response), [b'ok'])
        self.assertEqual(environ['HTTP_HOST'], '127.0.0.1')
        app.assert_called_once()
