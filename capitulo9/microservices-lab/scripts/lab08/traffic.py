import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, ProxyHandler, build_opener
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['business', 'normal', 'errors', 'slow'])
parser.add_argument('--seconds', type=int, default=90)
args = parser.parse_args()
if not 1 <= args.seconds <= 180:
    raise SystemExit('--seconds debe estar entre 1 y 180')
opener = build_opener(ProxyHandler({}))
issuer = 'http://localhost:8080/realms/microservices-lab'
body = urlencode({
    'grant_type': 'client_credentials', 'client_id': 'lab-admin-client',
    'client_secret': 'lab-admin-secret',
    'scope': 'orders.read orders.write inventory.read inventory.write',
}).encode()
with opener.open(Request(issuer + '/protocol/openid-connect/token', data=body,
                        headers={'Content-Type': 'application/x-www-form-urlencoded'}), timeout=15) as r:
    token = json.load(r)['access_token']

def call(path, data=None):
    req = Request('http://localhost:18080' + path,
                  data=json.dumps(data).encode() if data is not None else None,
                  headers={'Host': 'microservices.local', 'Authorization': 'Bearer ' + token,
                           'Content-Type': 'application/json'})
    try:
        response = opener.open(req, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        raw = response.read().decode()
        try:
            content = json.loads(raw)
        except ValueError:
            content = raw
        return response.status, content, response.headers

def expect(code, expected, content):
    if code != expected:
        raise SystemExit(f'Esperado {expected}, recibido {code}: {content}')

if args.mode == 'business':
    code, product, _ = call('/api/v1/products', {
        'name': 'Lab08', 'sku': 'OBS-' + uuid4().hex[:12].upper(), 'stock_quantity': 20,
    })
    expect(code, 201, product)
    code, order, headers = call('/api/v1/orders', {
        'customer_id': str(uuid4()),
        'items': [{'product_id': product['id'], 'quantity': 2, 'unit_price': '10.00'}],
    })
    expect(code, 201, order)
    if headers.get('X-Stock-Precheck') != 'verified':
        raise SystemExit('Precheck no verificado: revisar Inventory antes de analizar la traza')
    trace_id = headers.get('X-Trace-Id')
    if not trace_id:
        raise SystemExit('Falta X-Trace-Id: comprobar instrumentacion e imagen lab08')
    Path('lab08-trace-id.txt').write_text(trace_id)
    print('TRACE_ID:', trace_id)
    print('ORDER_ID:', order['id'])
    end = time.monotonic() + 60
    stock = None
    while time.monotonic() < end:
        code, current, _ = call('/api/v1/products/' + product['id'])
        expect(code, 200, current)
        stock = current['stock_quantity']
        if stock == 18:
            break
        time.sleep(1)
    if stock != 18:
        raise SystemExit('No se observo la reserva de 2 unidades')
    print('OK: pedido, precheck, traza y reserva de stock')
else:
    suffix = {'normal': '', 'errors': '?fail=true', 'slow': '?slow=true'}[args.mode]
    expected = 500 if args.mode == 'errors' else 200
    end = time.monotonic() + args.seconds
    count = 0
    while time.monotonic() < end:
        for service in ['orders', 'inventory']:
            code, content, _ = call('/api/v1/lab08/' + service + '/probe' + suffix)
            expect(code, expected, content)
            count += 1
        time.sleep(.4)
    print(f'OK: {count} solicitudes en modo {args.mode}')
