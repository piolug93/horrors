import email.utils
import http
import time

from horrors import (
    logging,
    triggers,
)
from horrors.services import SocketService


class HTTPStatic(SocketService):

    address = '0.0.0.0'
    port = 8888
    close_connection = True
    banner = 'HTTPStatic'
    template_404 = '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Page not found</title></head><body><h1>404 Not Found!</h1></body></html>'

    def __init__(self, address=None, port=None):
        super().__init__(address, port)
        self.routes = dict()
        self.buffer = None

    def date_time_string(self, timestamp=None):
        if timestamp is None:
            timestamp = time.time()
        return email.utils.formatdate(timestamp, usegmt=True)

    def timestamp(self, request):
        return str(time.time())

    def send_response(self, status_code=200):
        status_code = http.HTTPStatus(status_code)
        self.buffer = list()
        self.buffer.append(
            f'HTTP/1.1 {status_code.value} {status_code.phrase}\r\n'
        )

    def send_header(self, key, value):
        if self.buffer is None:
            raise RuntimeError('Must be initialized with `send_response` first')
        self.buffer.append(
            f'{key}: {value}\r\n'
        )

    def add_route(self, route, content):
        self.routes[route] = content

    def end_headers(self):
        if self.close_connection:
            self.send_header('Connection', 'close')
        self.buffer.append('\r\n')

    async def send_content(self, writer, content='', status_code=200, content_type='text/html'):
        self.send_response(status_code)
        self.send_header('Server', self.banner)
        self.send_header('Date', self.date_time_string())
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.buffer.append(content)
        full_response = ''.join(self.buffer)
        writer.write(bytes(full_response, 'latin-1'))
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        logging.debug(f'Sent response:\r\n{full_response}')

    async def handler(self, reader, writer):
        request = list()
        while True:
            data = await reader.readline()
            if not data or data == b'\r\n':
                break
            else:
                data = data.decode()
                self.process(triggers.DataMatch, data)
                logging.debug(rf'Received:\r\n{data}')
                request.append(data)
        try:
            path = request[0].split(' ')[1]
        except IndexError:
            await self.send_content(writer, content='Error!', status_code=500)
        else:
            self.process(triggers.PathContains, path)
            try:
                content = self.routes[path]
            except KeyError:
                await self.send_content(writer, content=self.template_404, status_code=404)
            else:
                if callable(content):
                    content = content(self, request)
                await self.send_content(writer, content)
