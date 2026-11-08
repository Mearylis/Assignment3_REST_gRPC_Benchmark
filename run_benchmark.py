"""Launch the testbed, smoke-test, and run a reproducible pilot.
Run: python run_benchmark.py --seconds 3 --repeats 2
"""
import argparse
import asyncio
import csv
import datetime as dt
import hashlib
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
import httpx
import psutil
import grpc
import google.protobuf
import fastapi
import uvicorn
ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence'
URL = 'http://127.0.0.1:18100'

def csv_write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

def percentile(xs, q):
    data = sorted(xs)
    if not data: return None
    p = (len(data)-1)*q/100; left = int(p); fraction = p-left
    return data[left]*(1-fraction) + data[min(left+1,len(data)-1)]*fraction

def cpu_seconds(proc):
    x = proc.cpu_times(); return x.user + x.system

def memory_bytes(proc):
    return proc.memory_info().rss

async def wait_healthy(url):
    async with httpx.AsyncClient() as c:
        for _ in range(80):
            try:
                resp = await c.get(url, timeout=.5)
                if resp.status_code == 200: return
            except (httpx.HTTPError, OSError): pass
            await asyncio.sleep(.1)
        raise RuntimeError(f'Server did not become healthy: {url}')

async def smoke_test():
    async with httpx.AsyncClient(timeout=3) as c:
        for item_id in [1, 45, 100, 101]:
            a = (await c.get(f'{URL}/item/{item_id}?backend=rest')).json()
            b = (await c.get(f'{URL}/item/{item_id}?backend=grpc')).json()
            assert a == b, (item_id, a, b)
            assert a['id'] == item_id
            assert a['ok'] == (1 <= item_id <= 100)
    return 'PASS: identical responses for valid IDs 1, 45, 100 and missing ID 101'

async def bench_trial(protocol, concurrency, seconds, processes):
    attempts = []; failures = []
    start_at = time.perf_counter(); end_at = start_at + seconds
    start_cpu = sum(cpu_seconds(p) for p in processes)
    peak_rss = sum(memory_bytes(p) for p in processes)
    async def sample_memory():
        nonlocal peak_rss
        while time.perf_counter() < end_at:
            rss = sum(memory_bytes(p) for p in processes)
            peak_rss = max(peak_rss, rss)
            await asyncio.sleep(.15)
    async with httpx.AsyncClient(timeout=3, limits=httpx.Limits(max_connections=60, max_keepalive_connections=60)) as client:
        async def worker(index):
            iteration = 0
            while time.perf_counter() < end_at:
                item_id = 1 + ((index*13 + iteration) % 100)
                a = time.perf_counter_ns()
                try:
                    r = await client.get(f'{URL}/item/{item_id}', params={'backend': protocol})
                    data = r.json()
                    success = r.status_code == 200 and data == {
                        'id': item_id,
                        'name': f'Campus item {item_id:03d}',
                        'category': ('hardware', 'stationery', 'books')[item_id % 3],
                        'stock': (item_id*7) % 101,
                        'ok': True,
                    }
                    if not success: failures.append(f'invalid response: {protocol}, id={item_id}, status={r.status_code}')
                except (httpx.HTTPError, ValueError) as err:
                    success = False; failures.append(f'{type(err).__name__}: {str(err)[:80]}')
                latency_ms = (time.perf_counter_ns() - a) / 1e6
                attempts.append((latency_ms, success)); iteration += 1
        await asyncio.gather(sample_memory(), *(worker(i) for i in range(concurrency)))
    elapsed = time.perf_counter() - start_at
    cpu_end = sum(cpu_seconds(p) for p in processes)
    peak_rss = max(peak_rss, sum(memory_bytes(p) for p in processes))
    valid = [t for t, ok in attempts if ok]; successes = len(valid)
    row = dict(
        protocol=protocol, concurrency=concurrency, duration_target_s=seconds,
        wall_s=round(elapsed, 3), attempts=len(attempts), successes=successes,
        failures=len(attempts)-successes,
        success_pct=round(100 * successes / len(attempts), 3) if attempts else 0,
        mean_latency_ms=round(statistics.mean(valid), 3) if valid else None,
        p50_ms=round(percentile(valid, 50), 3) if valid else None,
        p95_ms=round(percentile(valid, 95), 3) if valid else None,
        p99_ms=round(percentile(valid, 99), 3) if valid else None,
        rps=round(successes/elapsed, 2),
        avg_cpu_pct_one_core=round((cpu_end-start_cpu)/elapsed*100, 2),
        peak_rss_mib=round(peak_rss/1024**2, 2),
    )
    return row, failures

async def run(seconds, repeats, warm_seconds):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    handles = []; processes = {}
    try:
        for name, module in [('rest', 'rest_service.py'), ('grpc', 'grpc_service.py')]:
            log = (EVIDENCE/f'{name}_server.log').open('w', encoding='utf-8'); handles.append(log)
            processes[name] = subprocess.Popen([sys.executable, '-u', str(ROOT/module)], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
        await wait_healthy('http://127.0.0.1:18101/health')
        log = (EVIDENCE/'gateway_server.log').open('w', encoding='utf-8'); handles.append(log)
        processes['gateway'] = subprocess.Popen([sys.executable, '-u', str(ROOT/'gateway.py')], cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
        await wait_healthy(f'{URL}/health')
        verification = await smoke_test()
        print('SMOKE:', verification, flush=True)
        (EVIDENCE/'functional_test.txt').write_text(verification+'\n', encoding='utf-8')
        traces = []; notes = []
        for rep in range(1, repeats+1):
            for level in (1, 8, 24):
                order = ['rest','grpc'] if (rep+level) % 2 else ['grpc','rest']
                for protocol in order:
                    active_procs = [psutil.Process(processes['gateway'].pid), psutil.Process(processes[protocol].pid)]
                    await bench_trial(protocol, level, warm_seconds, active_procs)
                    row, failures = await bench_trial(protocol, level, seconds, active_procs)
                    row['repeat'] = rep; traces.append(row); notes.extend(failures[:5])
                    print(f"RUN repeat={rep} load={level} protocol={protocol} success={row['successes']}/{row['attempts']} mean={row['mean_latency_ms']}ms p95={row['p95_ms']}ms rps={row['rps']} cpu={row['avg_cpu_pct_one_core']}% rss={row['peak_rss_mib']}MiB", flush=True)
        csv_write(EVIDENCE/'pilot_raw.csv', traces)
        summarized = []
        for level in (1,8,24):
            for protocol in ('rest','grpc'):
                group = [r for r in traces if r['concurrency']==level and r['protocol']==protocol]
                summarized.append(dict(
                    concurrency=level, protocol=protocol, repeats=len(group),
                    avg_latency_ms=round(statistics.mean(r['mean_latency_ms'] for r in group),3),
                    mean_p95_ms=round(statistics.mean(r['p95_ms'] for r in group),3),
                    avg_rps=round(statistics.mean(r['rps'] for r in group),2),
                    avg_cpu_pct_one_core=round(statistics.mean(r['avg_cpu_pct_one_core'] for r in group),2),
                    mean_peak_rss_mib=round(statistics.mean(r['peak_rss_mib'] for r in group),2),
                    failed_requests=sum(r['failures'] for r in group),
                    total_requests=sum(r['attempts'] for r in group),
                ))
        csv_write(EVIDENCE/'pilot_summary.csv', summarized)
        versions = {
            'date_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
            'platform':platform.platform(), 'python':sys.version.split()[0],
            'processor':platform.processor(), 'cpu_logical':psutil.cpu_count(),
            'libraries':{'grpcio':grpc.__version__, 'protobuf':google.protobuf.__version__,
                'fastapi':fastapi.__version__, 'httpx':httpx.__version__,
                'uvicorn':uvicorn.__version__, 'psutil':psutil.__version__},
            'design':'HTTP client -> constant FastAPI gateway -> REST(JSON/HTTP1.1) or gRPC(Protobuf/HTTP2) catalog service',
            'test_settings':{'repeats':repeats,'levels_concurrent_workers':[1,8,24], 'measured_duration_each_s':seconds,'warmup_s':warm_seconds,'host':'127.0.0.1','timeouts_s':3},
            'limitations':['Shared sandbox environment, not dedicated hardware', 'Short exploratory runs', 'Non-identical server framework execution paths', 'HTTP gateway and driver overhead included', 'No TLS, no database or cross-host network', 'Peak RSS absolute not memory cost per request', 'Paired repeats may be influenced by background host load'],
        }
        for filename in ['catalog_schema.py','catalog.proto','data.py','rest_service.py','grpc_service.py','gateway.py','run_benchmark.py']:
            versions.setdefault('source_sha256',{})[filename]=hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()
        (EVIDENCE/'environment.json').write_text(json.dumps(versions,ensure_ascii=False,indent=2), encoding='utf-8')
        (EVIDENCE/'failures.txt').write_text('\n'.join(notes) if notes else 'No request failures observed in recorded pilot conditions.\n',encoding='utf-8')
        print('FILES: evidence/pilot_raw.csv evidence/pilot_summary.csv evidence/environment.json evidence/functional_test.txt', flush=True)
        return summarized
    finally:
        for p in processes.values():
            if p.poll() is None: p.terminate()
        for p in processes.values():
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
        for log in handles: log.close()
if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--seconds',type=float,default=3.0)
    parser.add_argument('--repeats',type=int,default=2); parser.add_argument('--warm-seconds',type=float,default=.25)
    a=parser.parse_args(); asyncio.run(run(a.seconds,a.repeats,a.warm_seconds))
