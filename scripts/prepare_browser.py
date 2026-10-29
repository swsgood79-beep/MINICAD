"""Prepare self-hosted browser Python assets; verify every downloaded wheel."""
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT/'frontend/node_modules/pyodide'
PUBLIC = ROOT/'frontend/public'
TARGET = PUBLIC/'pyodide'
VERSION = '0.29.3'
BASE = f'https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/'

def download(url, target, expected):
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
        return
    with urllib.request.urlopen(url, timeout=120) as response:
        data=response.read()
    if hashlib.sha256(data).hexdigest()!=expected:
        raise RuntimeError('Checksum mismatch: '+target.name)
    target.write_bytes(data)
    print('Verified',target.name)

def main():
    assert json.loads((RUNTIME/'package.json').read_text())['version']==VERSION
    TARGET.mkdir(parents=True,exist_ok=True)
    for name in ('pyodide.js','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json'):
        shutil.copy2(RUNTIME/name,TARGET/name)
    packages=json.loads((RUNTIME/'pyodide-lock.json').read_text())['packages']
    visited=set()
    def package(name):
        if name in visited:return
        visited.add(name)
        spec=packages[name]
        for dependency in spec['depends']:package(dependency)
        download(BASE+spec['file_name'],TARGET/spec['file_name'],spec['sha256'])
    for name in ('numpy','fonttools','pyparsing','typing-extensions'):package(name)
    download('https://files.pythonhosted.org/packages/a0/09/5ecb6f82d35a2f4a4334d0a608fcf764827fa69dccdf5987ce309c16b6c1/ezdxf-1.4.4-py3-none-any.whl',TARGET/'ezdxf-1.4.4-py3-none-any.whl','666edda631ba717270293b734f5d58dd97a1d1aba4787187f09d0cc584645865')
    for name in ('cad_core.py','browser_runtime.py'):shutil.copy2(ROOT/name,PUBLIC/name)
    print('Browser runtime assets prepared (all served by the same website).')

if __name__=='__main__':main()
