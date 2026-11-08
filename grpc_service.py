"""Independent gRPC microservice with unary Protobuf RPC."""
import asyncio
import grpc
from catalog_schema import LookupRequest, LookupReply
from data import lookup_item
async def lookup_rpc(request: LookupRequest, context) -> LookupReply:
    return LookupReply(**lookup_item(request.id))
async def main():
    server = grpc.aio.server(options=[('grpc.max_concurrent_streams', 100)])
    handler = grpc.method_handlers_generic_handler('bench.Catalog', {
        'LookupItem': grpc.unary_unary_rpc_method_handler(
            lookup_rpc,
            request_deserializer=LookupRequest.FromString,
            response_serializer=LookupReply.SerializeToString,
        ),
    })
    server.add_generic_rpc_handlers((handler,))
    server.add_insecure_port('127.0.0.1:18151')
    await server.start(); await server.wait_for_termination()
if __name__ == '__main__':
    asyncio.run(main())
