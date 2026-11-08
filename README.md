# Research Methods - Assignment 3: REST versus gRPC pilot testbed

This is the executable code and recorded output supporting the **initial practical implementation** (not a conclusive benchmark). The companion report describes the method, objectives and limitations.

## Testbed

One deterministic Catalog business operation (`data.py`) serves the same 100 synthetic records through REST and gRPC. A fixed FastAPI gateway offers the same external `GET /item/{id}` request for both conditions and switches only the downstream communication protocol: REST (JSON over HTTP/1.1) or gRPC (Protocol Buffers over HTTP/2). One benchmark driver loads the gateway. Clients and downstream channels are reused.

The Protobuf schema is in `catalog.proto`. `catalog_schema.py` constructs the same schema programmatically at runtime, so installing `protoc` is not necessary. This is true `grpcio` transport with binary Protocol Buffers.

## Reproduction

On Python 3.11+ (tested on Python 3.13.5):

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python run_benchmark.py --seconds 3 --repeats 2
```

The script starts and stops the services automatically, on localhost ports 18100 (gateway), 18101 (REST service), and 18151 (gRPC). Run `--seconds 10 --repeats 5` for a stronger follow-up on dedicated hardware. No external network, private data, API keys, or human subjects are used.

## Outputs

- `evidence/functional_test.txt` - observed cross-protocol parity for three valid IDs and one missing ID.
- `evidence/pilot_raw.csv` - per observed workload/protocol/trial: counts, mean/p50/p95/p99 latency (ms), successful responses per second, combined gateway + active-server CPU (% of one logical core), and absolute peak combined RAM (MiB).
- `evidence/pilot_summary.csv` - arithmetic means of repeated exploratory runs, not population estimates.
- `evidence/environment.json` - timestamp, versions, machine data, known limits, parameters, code SHA-256 hashes.
- `evidence/failures.txt` - observed failures or an explicit none statement.

## Interpretation and limitations

Runs are short and performed on a shared host against an in-memory catalog. This is an exploratory proof of concept, NOT a universal proof that a protocol is faster. The constant gateway removes external transport differences, while adding the same overhead to both. REST and gRPC server framework internals still differ. Concurrency is simultaneous virtual workers, not requests per second. Throughput counts correct **successful responses** per measured time. CPU uses the process CPU seconds for gateway + active service; 100% means one core fully busy. Peak RSS includes runtime allocations and is not the RAM cost of one request. Do not select only flattering results or overlook failures.
