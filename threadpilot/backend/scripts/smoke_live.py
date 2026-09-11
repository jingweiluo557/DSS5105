"""One real, non-streaming request through FastAPI. Never prints credentials."""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    health = client.get('/api/v1/health').json()
    print({'configured': health['configured'], 'model': health['model']})
    result = client.post('/api/v1/chat', json={'message': 'In one short sentence, state the business date of this dataset. Do not list orders.'})
    if result.status_code == 200:
        data = result.json()
        print({'status': 200, 'answer': data['answer'], 'usage': data['usage']})
    else:
        print({'status': result.status_code, 'error': result.json().get('error', {}).get('code')})
        raise SystemExit(1)
