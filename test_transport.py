"""Linux PTY integration test; this emulates protocol, not physical hardware."""
import json
import os
import pty
import select
import threading
import time
import urllib.error
import urllib.request
import server

master, slave = pty.openpty()
device = server.Device(os.ttyname(slave))
threading.Thread(target=device.run, daemon=True).start()
digits = '00000000'
stop = threading.Event()

def emulator():
    global digits
    buffer = b''
    while not stop.is_set():
        if not select.select([master], [], [], .1)[0]:
            continue
        buffer += os.read(master, 1024)
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            if line.startswith(b'D'):
                digits = line[1:].decode()
            if line == b'Q' or line.startswith(b'D'):
                os.write(master, ('P1 '+digits+' 5 A55A 00000002\n').encode())

threading.Thread(target=emulator, daemon=True).start()
http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
http.device = device
threading.Thread(target=http.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:'+str(http.server_port)

def wait_for(predicate):
    until = time.monotonic()+4
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('timed out: '+str(device.snapshot()))

def post(value, token=server.TOKEN):
    req = urllib.request.Request(url+'/api/display', data=json.dumps({'digits':value}).encode(), headers={'X-Panel-Token':token, 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code

wait_for(lambda: device.snapshot()['connected'])
assert post('01234567') == 202
wait_for(lambda: device.snapshot()['confirmed'] == '01234567')
s = json.load(urllib.request.urlopen(url+'/api/state'))
assert (s['buttons'], s['switches'], s['event_count']) == (5, 0xA55A, 2)
assert post('1234567') == 400
assert post('１２３４５６７８') == 400
assert post('12345678', 'bad') == 403
stop.set()
wait_for(lambda: not device.snapshot()['connected'])
assert post('12345678') == 503
assert device.snapshot()['requested'] == '01234567'
http.shutdown()
print(json.dumps({'test':'PTY simulation, not FPGA hardware', 'passed':['UART handshake','leading-zero display roundtrip','button/switch decoding','HTTP validation','CSRF token','stale-device rejection']}, indent=2))
