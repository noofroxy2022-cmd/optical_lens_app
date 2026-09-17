"""Original-Rx input/edit safety; no catalog database writes."""
import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app import crud, models, schemas, product_search
from app.database import Base, get_db
from app.routers.prescriptions import router


def payload():
    return dict(od=dict(sph=-2, cyl=0), os=dict(sph=-2, cyl=0))


@pytest.fixture
def db():
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    # Exercise the ASGI request boundary without an optional HTTP client package.
    class Client:
        def request(self, method, path, **kwargs):
            async def run():
                messages = []
                body = json.dumps(kwargs.get('json', {})).encode()
                async def receive():
                    return {'type': 'http.request', 'body': body, 'more_body': False}
                async def send(message):
                    messages.append(message)
                await app({'type': 'http', 'asgi': {'version': '3.0'},
                           'http_version': '1.1', 'method': method, 'scheme': 'http',
                           'path': path, 'raw_path': path.encode(), 'query_string': b'',
                           'headers': [(b'content-type', b'application/json')],
                           'client': ('test', 1), 'server': ('test', 80)}, receive, send)
                content = b''.join(m.get('body', b'') for m in messages)
                return SimpleNamespace(status_code=messages[0]['status'],
                                       json=lambda: json.loads(content))
            return asyncio.run(run())
        def post(self, path, **kwargs): return self.request('POST', path, **kwargs)
        def put(self, path, **kwargs): return self.request('PUT', path, **kwargs)
        def get(self, path, **kwargs): return self.request('GET', path, **kwargs)
    yield Client()


@pytest.mark.parametrize("eye", ["od", "os"])
@pytest.mark.parametrize("axis", ["omitted", None])
def test_nonzero_cylinder_requires_axis_at_api_boundary(client, db, eye, axis):
    data = payload()
    data[eye]["cyl"] = -1
    if axis != "omitted":
        data[eye]["axis"] = axis
    response = client.post('/prescriptions/', json=data)
    assert response.status_code == 422
    assert eye in response.json()['detail'][0]['loc']
    assert 'AXIS' in response.json()['detail'][0]['msg']
    assert db.query(models.Prescription).count() == 0


def test_zero_cylinder_omitted_axis_accepted(client):
    response = client.post('/prescriptions/', json=payload())
    assert response.status_code == 200
    assert response.json()['od_axis'] == response.json()['os_axis'] == 0


@pytest.mark.parametrize("cyl,axis,normalized", [(-1, 0, 0), (-1, 180, 180),
                                                (-1, 45, 45), (1, 0, 90),
                                                (1, 180, 90), (1, 90, 180)])
def test_explicit_axis_and_existing_transposition(client, cyl, axis, normalized):
    data = payload()
    for eye in ('od', 'os'):
        data[eye].update(cyl=cyl, axis=axis)
    result = client.post('/prescriptions/', json=data).json()
    for eye in ('od', 'os'):
        assert result[eye+'_axis_original'] == axis
        assert result[eye+'_axis'] == normalized
        assert result[eye+'_sph'] == (-1 if cyl > 0 else -2)


def test_edit_original_then_reading_never_mutates_stored_rx(client, db):
    created = client.post('/prescriptions/', json=payload()).json()
    pid = created['id']
    data = payload()
    data['od'].update(sph=-3, cyl=1, axis=180, add=2)
    data['os'].update(sph=-2, cyl=-1, axis=0, add=2.5)
    edited = client.put(f'/prescriptions/{pid}', json=data)
    assert edited.status_code == 200
    before = edited.json()
    assert before['id'] == pid and before['created_at'] == created['created_at']
    assert before['od_sph_original'] == -3 and before['od_sph'] == -2
    assert before['od_axis_original'] == 180 and before['od_axis'] == 90
    response = client.post(f'/prescriptions/{pid}/search', json={
        'use_mode': 'reading', 'customer_need': 'none'}).json()
    assert response['derived_search_rx'] == dict(od_sph=0, od_cyl=-1, od_axis=90,
                                                os_sph=.5, os_cyl=-1, os_axis=0)
    assert client.get(f'/prescriptions/{pid}').json() == before
    bad = payload()
    bad['os']['cyl'] = 1
    assert client.put(f'/prescriptions/{pid}', json=bad).status_code == 422
    assert client.get(f'/prescriptions/{pid}').json() == before
    assert db.query(models.Prescription).count() == 1


def test_edit_missing_prescription_returns_404(client):
    assert client.put('/prescriptions/999', json=payload()).status_code == 404
