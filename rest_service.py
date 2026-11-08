"""Independent REST microservice with GET /items/{id} and JSON response."""
import uvicorn
from fastapi import FastAPI
from data import lookup_item
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
@app.get('/items/{item_id}')
async def get_item(item_id: int):
    return lookup_item(item_id)
@app.get('/health')
async def health():
    return {'status': 'ok'}
if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18101, log_level='error', access_log=False)
