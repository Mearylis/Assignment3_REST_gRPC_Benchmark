"""Constant HTTP gateway; only downstream transport varies by protocol."""
from contextlib import asynccontextmanager
import grpc
import httpx
import uvicorn
from fastapi import FastAPI, Query
from catalog_schema import GRPC_METHOD, LookupRequest, LookupReply
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rest = httpx.AsyncClient(timeout=2.0, limits=httpx.Limits(max_connections=100, max_keepalive_connections=100))
    app.state.grpc_channel = grpc.aio.insecure_channel('127.0.0.1:18151')
    app.state.grpc_lookup = app.state.grpc_channel.unary_unary(
        GRPC_METHOD,
        request_serializer=LookupRequest.SerializeToString,
        response_deserializer=LookupReply.FromString,
    )
    await app.state.grpc_channel.channel_ready()
    yield
    await app.state.rest.aclose(); await app.state.grpc_channel.close()
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
@app.get('/item/{item_id}')
async def get_item(item_id: int, backend: str = Query(pattern='^(rest|grpc)$')):
    if backend == 'rest':
        r = await app.state.rest.get(f'http://127.0.0.1:18101/items/{item_id}')
        r.raise_for_status(); data = r.json()
    else:
        r = await app.state.grpc_lookup(LookupRequest(id=item_id), timeout=2.0)
        data = {"id": r.id, "name": r.name, "category": r.category, "stock": r.stock, "ok": r.ok}
    return data
@app.get('/health')
async def health():
    return {'status': 'ok'}
if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=18100, log_level='error', access_log=False)
