"""Bounded HTTP transfer-rate estimate; not an ISP line-capacity measurement."""
import asyncio
import os
from time import perf_counter
import httpx
from .schemas import now

lock=asyncio.Lock()
DOWNLOAD_BYTES=10_000_000
UPLOAD_BYTES=5_000_000

def measure():
    result=dict(provider='Cloudflare',host='speed.cloudflare.com',started_at=now(),
        method='Single HTTPS transfer per direction. Mbps = transferred bytes × 8 / elapsed seconds / 1,000,000. Includes request and response overhead.',
        limitation='Short transfer estimate from this computer to Cloudflare, not guaranteed ISP speed. Wi-Fi, VPNs and other traffic can affect results.',
        download_mbps=None,upload_mbps=None,measurements=[],errors=[])
    with httpx.Client(timeout=httpx.Timeout(20),follow_redirects=False,trust_env=False) as client:
        for direction,size in [('download',DOWNLOAD_BYTES),('upload',UPLOAD_BYTES)]:
            started=perf_counter();count=0
            try:
                if direction=='download':
                    with client.stream('GET',f'https://speed.cloudflare.com/__down?bytes={size}',headers={'Accept-Encoding':'identity','Cache-Control':'no-cache'}) as response:
                        response.raise_for_status()
                        for chunk in response.iter_bytes():
                            count+=len(chunk)
                            if count>size or perf_counter()-started>25: raise ValueError('Transfer exceeded test limits')
                    if count!=size: raise ValueError('Incomplete download')
                else:
                    payload=os.urandom(size)
                    started=perf_counter()
                    response=client.post('https://speed.cloudflare.com/__up',content=payload,headers={'Content-Type':'application/octet-stream'})
                    response.raise_for_status();count=size
                elapsed=perf_counter()-started
                value=round(count*8/elapsed/1_000_000,2)
                result[direction+'_mbps']=value
                result['measurements'].append(dict(direction=direction,bytes=count,elapsed_seconds=round(elapsed,6),mbps=value))
            except (httpx.HTTPError,ValueError):
                result['errors'].append(f'{direction.title()} measurement failed or timed out; no speed is reported for that direction.')
    result.update(completed_at=now(),status='completed' if not result['errors'] else 'partial' if result['measurements'] else 'failed')
    return result
