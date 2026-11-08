"""Protocol Buffers 3 message classes for the benchmark.
Equivalent to catalog.proto. Descriptors at runtime avoid a compiler step;
the wire format is genuine Protocol Buffers, not JSON-over-gRPC.
"""
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
fd = descriptor_pb2.FileDescriptorProto()
fd.name = 'catalog.proto'
fd.package = 'bench'
fd.syntax = 'proto3'
for name, fields in (
    ('LookupRequest', [('id', 1, 5)]),
    ('LookupReply', [('id', 1, 5), ('name', 2, 9), ('category', 3, 9), ('stock', 4, 5), ('ok', 5, 8)]),
):
    msg = fd.message_type.add(); msg.name = name
    for field_name, number, type_code in fields:
        f = msg.field.add()
        f.name = field_name; f.number = number
        f.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL
        f.type = type_code
service = fd.service.add(); service.name = 'Catalog'
method = service.method.add(); method.name = 'LookupItem'
method.input_type = '.bench.LookupRequest'; method.output_type = '.bench.LookupReply'
pool = descriptor_pool.DescriptorPool(); pool.Add(fd)
LookupRequest = message_factory.GetMessageClass(pool.FindMessageTypeByName('bench.LookupRequest'))
LookupReply = message_factory.GetMessageClass(pool.FindMessageTypeByName('bench.LookupReply'))
GRPC_METHOD = '/bench.Catalog/LookupItem'
