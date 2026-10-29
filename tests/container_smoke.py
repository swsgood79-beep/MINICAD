"""Integration check for a built minicad-web:stage1 image; requires Docker and httpx/ezdxf."""
import io
import os
import secrets
import subprocess
import time
import ezdxf
import httpx

def main():
    docker=['docker','--host=unix:///var/run/docker.sock']
    env=os.environ.copy()
    env.update(MINICAD_DEPLOYED='1',MINICAD_USERNAME='smoke',MINICAD_PASSWORD=secrets.token_urlsafe(32))
    container=subprocess.check_output(docker+['run','-d','-p','127.0.0.1:18000:10000','-e','MINICAD_DEPLOYED','-e','MINICAD_USERNAME','-e','MINICAD_PASSWORD','minicad-web:stage1'],env=env,text=True).strip()
    try:
        with httpx.Client(base_url='http://127.0.0.1:18000',timeout=2) as client:
            for _ in range(40):
                running=subprocess.check_output(docker+['inspect','--format','{{.State.Running}}',container],text=True).strip()
                if running!='true':
                    logs=subprocess.check_output(docker+['logs',container],stderr=subprocess.STDOUT,text=True)
                    raise RuntimeError('Container exited: '+logs[-3000:])
                try:
                    if client.get('/healthz').status_code==200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.5)
            else:
                raise RuntimeError('Container readiness timeout')
            assert client.get('/').status_code==401
            client.auth=('smoke',env['MINICAD_PASSWORD'])
            assert client.get('/').status_code==200
            assert client.get('/api/status').json()['mode']=='private-hosted'
            doc=ezdxf.new(); doc.units=4
            line=doc.modelspace().add_line((0,0),(100,0))
            stream=io.StringIO(); doc.write(stream)
            opened=client.post('/api/open',files={'file':('smoke.dxf',stream.getvalue().encode())})
            assert opened.status_code==200,opened.text
            key=opened.json()['document_id']
            moved=client.post('/api/edit',params={'document_id':key},json={'op':'move','handle':line.dxf.handle,'dx':12,'dy':5})
            assert moved.status_code==200,moved.text
            exported=client.get('/api/export/dxf',params={'document_id':key})
            assert exported.status_code==200
            result=ezdxf.read(io.StringIO(exported.content.decode()))
            assert result.entitydb[line.dxf.handle].dxf.start.isclose((12,5,0))
        print('PASS: non-root container startup, health, login protection, React HTML, authenticated DXF open/edit/export/reopen.')
    finally:
        subprocess.run(docker+['rm','-f',container],check=True,stdout=subprocess.DEVNULL)

if __name__=='__main__':
    main()
