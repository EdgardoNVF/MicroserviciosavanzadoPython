import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
K = ['kubectl', '--context', 'msvc-gateway', '-n', 'microservices']
SERVICES = ['order-service', 'inventory-service']

def read(*args):
    return subprocess.check_output(K + list(args), text=True)

def main():
    os.umask(0o077)
    for name in SERVICES:
        if not (ROOT / name / 'app/main.py').is_file():
            raise SystemExit(f'Falta {name}/app/main.py; revisa la ubicacion del script')
    for folder in ['backup-lab08', 'charts/lab09/files']:
        (ROOT / folder).mkdir(parents=True, exist_ok=True)

    targets = [ROOT / 'charts/lab09/values.yaml']
    for name in SERVICES:
        targets.extend([ROOT / 'backup-lab08' / f'{name}.json',
                        ROOT / 'charts/lab09/files' / f'{name}.json',
                        ROOT / name / 'requirements.lab09.lock'])
    existing = [str(p.relative_to(ROOT)) for p in targets if p.exists()]
    if existing:
        raise SystemExit('Captura detenida; no se sobrescribe:\n' + '\n'.join(existing)
                         + '\nSi ya completaste la captura, continua con el paso 7.')

    # Primero consultar y validar AMBOS servicios. No escribir salidas aun.
    pending = {}
    values = {'hardening': False, 'services': {}}
    package_code = r'''
import importlib.metadata as metadata
import json
print(json.dumps(sorted({d.metadata['Name'] + '==' + d.version
    for d in metadata.distributions() if d.metadata['Name']
    and d.metadata['Name'].lower() not in {'pip', 'setuptools', 'wheel'}})))
'''
    for name in SERVICES:
        obj = json.loads(read('get', 'deployment', name, '-o', 'json'))
        owner = obj['metadata'].get('annotations', {}).get('meta.helm.sh/release-name')
        if owner:
            raise SystemExit(f'{name} pertenece a Helm ({owner}); no recaptures la base')
        spec = obj['spec']
        containers = spec['template']['spec']['containers']
        if len(containers) != 1 or containers[0]['name'] != name:
            raise SystemExit(f'{name}: se espera un contenedor con el mismo nombre')
        if spec.get('replicas', 1) != 1:
            raise SystemExit(f'{name}: esta practica parte de una replica')
        if spec['selector'].get('matchExpressions'):
            raise SystemExit(f'{name}: selector no compatible con esta captura')
        read('rollout', 'status', f'deployment/{name}', '--timeout=180s')
        selector = ','.join(f'{key}={value}' for key, value in
                            spec['selector']['matchLabels'].items())
        pods = json.loads(read('get', 'pods', '-l', selector, '-o', 'json'))['items']
        ready = [p for p in pods if not p['metadata'].get('deletionTimestamp')
                 and any(c['type'] == 'Ready' and c['status'] == 'True'
                         for c in p.get('status', {}).get('conditions', []))]
        if len(ready) != 1:
            raise SystemExit(f'{name}: se necesita un unico pod Ready')
        packages = json.loads(read('exec', ready[0]['metadata']['name'], '-c', name,
                                   '--', 'python', '-c', package_code))
        if not packages or not all(isinstance(p, str) and
            re.fullmatch(r'[A-Za-z0-9_.-]+==[^\s]+', p) for p in packages):
            raise SystemExit(f'{name}: lista de dependencias invalida')
        pending[ROOT / name / 'requirements.lab09.lock'] = '\n'.join(packages) + '\n'
        pending[ROOT / 'backup-lab08' / f'{name}.json'] = json.dumps(obj, indent=2)
        clean = {'apiVersion': 'apps/v1', 'kind': 'Deployment',
                 'metadata': {'name': name, 'namespace': 'microservices',
                              'labels': obj['metadata'].get('labels', {})},
                 'spec': spec}
        annotations = {k: v for k, v in obj['metadata'].get('annotations', {}).items()
                       if k not in {'kubectl.kubernetes.io/last-applied-configuration',
                                    'deployment.kubernetes.io/revision'}}
        if annotations:
            clean['metadata']['annotations'] = annotations
        pending[ROOT / 'charts/lab09/files' / f'{name}.json'] = json.dumps(clean, indent=2)
        c = containers[0]
        values['services'][name] = {'image': c['image'],
                                    'pullPolicy': c.get('imagePullPolicy', 'IfNotPresent')}
    pending[ROOT / 'charts/lab09/values.yaml'] = json.dumps(values, indent=2)

    # Exclusivo: no sobrescribir archivos creados por otra ejecucion.
    # Si hay un error capturable de escritura, retirar solo nuestras salidas.
    created = []
    try:
        for path, content in pending.items():
            with path.open('x', encoding='utf-8') as output:
                created.append(path)
                output.write(content)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    print('Captura completa: 7 archivos. Puedes continuar con el paso 7.')

if __name__ == '__main__':
    main()
