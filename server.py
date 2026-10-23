"""Board-local display panel. Real UART acknowledgement is required for success."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import select
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPLY = re.compile(r'^P1 ([0-9]{8}) ([0-9A-F]{1}) ([0-9A-F]{4}) ([0-9A-F]{8})$')
TOKEN = secrets.token_hex(24)


class Device:
    def __init__(self, port):
        self.port = port
        self.lock = threading.RLock()
        self.state = dict(connected=False, confirmed=None, requested=None,
                          buttons=None, switches=None, event_count=None,
                          last_seen=None, error='等待 FPGA 协议握手')
        self.fd = None

    def snapshot(self):
        with self.lock:
            result = dict(self.state)
            result['connected'] = bool(result['last_seen'] and time.time() - result['last_seen'] < 3)
            return result

    def send(self, data):
        if self.fd is None:
            raise OSError('串口尚未就绪')
        if os.write(self.fd, data) != len(data):
            raise OSError('串口写入不完整')

    def set_display(self, digits):
        with self.lock:
            if not self.snapshot()['connected']:
                raise OSError('FPGA 尚未握手，未发送显示命令')
            self.send(('D' + digits + '\n').encode('ascii'))
            self.state['requested'] = digits

    def run(self):
        import termios
        while True:
            try:
                fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                with self.lock:
                    self.fd = fd
                attrs = termios.tcgetattr(fd)
                attrs[0] = attrs[1] = attrs[3] = 0
                attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
                attrs[4] = attrs[5] = termios.B115200
                attrs[6][termios.VMIN] = 0
                attrs[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, attrs)
                buffer = b''
                next_query = 0
                while True:
                    if time.monotonic() >= next_query:
                        with self.lock:
                            self.send(b'Q\n')
                        next_query = time.monotonic() + .5
                    ready, _, _ = select.select([fd], [], [], .1)
                    if ready:
                        data = os.read(fd, 1024)
                        if not data:
                            raise OSError('串口已断开')
                        buffer += data
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            match = REPLY.fullmatch(line.decode('ascii', errors='replace').rstrip('\r'))
                            if match:
                                digits, buttons, switches, count = match.groups()
                                with self.lock:
                                    self.state.update(connected=True, confirmed=digits,
                                                      buttons=int(buttons, 16), switches=int(switches, 16),
                                                      event_count=int(count, 16), last_seen=time.time(), error=None)
                        if len(buffer) > 4096:
                            buffer = b''
                    with self.lock:
                        if not self.snapshot()['connected']:
                            self.state['error'] = '未收到 FPGA P1 协议应答'
            except OSError as exc:
                with self.lock:
                    self.state.update(connected=False, last_seen=None, error=str(exc))
            finally:
                with self.lock:
                    if self.fd is not None:
                        os.close(self.fd)
                        self.fd = None
            time.sleep(1)


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload, kind='application/json; charset=utf-8'):
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            self.reply(200, Path(__file__).with_name('index.html').read_text(encoding='utf-8').replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')
        elif self.path == '/api/state':
            self.reply(200, self.server.device.snapshot())
        else:
            self.reply(404, {'error': '未找到'})

    def do_POST(self):
        if self.path != '/api/display':
            return self.reply(404, {'error': '未找到'})
        if not secrets.compare_digest(self.headers.get('X-Panel-Token', ''), TOKEN):
            return self.reply(403, {'error': '请刷新页面后重试'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 128:
                raise ValueError('请求长度无效')
            value = json.loads(self.rfile.read(length)).get('digits')
            if not isinstance(value, str) or not re.fullmatch('[0-9]{8}', value):
                raise ValueError('请输入恰好 8 位数字')
            self.server.device.set_display(value)
        except (ValueError, AttributeError) as exc:
            return self.reply(400, {'error': str(exc)})
        except OSError as exc:
            return self.reply(503, {'error': str(exc)})
        self.reply(202, {'requested': value, 'message': '已发送，等待 FPGA 回读确认'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default='/dev/serial/by-id/usb-FTDI_Dual_RS232-HS-if01-port0')
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--http-port', type=int, default=8088)
    parser.add_argument('--offline', action='store_true', help='Preview page without opening hardware UART')
    args = parser.parse_args()
    device = Device(args.port)
    if args.offline:
        device.state['error'] = '等待 FPGA 引脚资料及编译许可，硬件控制尚未启用'
    else:
        threading.Thread(target=device.run, daemon=True).start()
    http = ThreadingHTTPServer((args.bind, args.http_port), Handler)
    http.device = device
    http.serve_forever()


if __name__ == '__main__':
    main()
