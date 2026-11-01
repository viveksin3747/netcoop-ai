"""Read-only ICMP measurements of this computer's default IPv4 gateway."""
import asyncio
import json
import subprocess
from .schemas import Telemetry, now
from .agents import uid
from . import store

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$candidates = @([System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | Where-Object {
    $_.OperationalStatus -eq 'Up' -and $_.NetworkInterfaceType -ne 'Loopback'
} | ForEach-Object {
    $iface = $_
    $_.GetIPProperties().GatewayAddresses | Where-Object {
        $_.Address.AddressFamily -eq 'InterNetwork' -and $_.Address.ToString() -ne '0.0.0.0'
    } | ForEach-Object { [pscustomobject]@{ address=$_.Address.ToString(); adapter=$iface.Name } }
})
if ($candidates.Count -eq 0) { throw 'No active IPv4 default gateway found. Connect to Wi-Fi or Ethernet first.' }
$gateway = $candidates[0]
$probe = New-Object System.Net.NetworkInformation.Ping
$samples = @()
try {
    for ($n=0; $n -lt 5; $n++) {
        try {
            $reply = $probe.Send($gateway.address, 1500)
            $samples += [pscustomobject]@{status=$reply.Status.ToString(); latency_ms=$(if ($reply.Status -eq 'Success') { $reply.RoundtripTime } else { $null })}
        } catch { $samples += [pscustomobject]@{status='ProbeError';latency_ms=$null} }
        if ($n -lt 4) { Start-Sleep -Milliseconds 400 }
    }
} finally { $probe.Dispose() }
[pscustomobject]@{gateway=$gateway.address;adapter=$gateway.adapter;samples=$samples;gateway_candidates=$candidates.Count} | ConvertTo-Json -Depth 5 -Compress
'''

def collect():
    started=now()
    completed=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',SCRIPT],
        capture_output=True,text=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if completed.returncode:
        raise ValueError('Could not measure the default gateway. Check that Wi-Fi or Ethernet is connected and PowerShell is available.')
    raw=json.loads(completed.stdout)
    values=[s['latency_ms'] for s in raw['samples'] if s['status']=='Success']
    key=uid('LIVE');raw.update(sample_id=key,timestamp=now(),started_at=started)
    store.put('live-sample',key,raw)
    # Failed ICMP responses alone cannot prove that a router is offline.
    t=Telemetry(timestamp=raw['timestamp'],source_type='live',data_mode='observed',network_id='Local gateway connection',
        source_reference=f'{key}: 5 ICMP probes of default gateway; {len(values)} replies; adapter {raw["adapter"]}'[:200],
        devices=[dict(device_id='DEFAULT-GATEWAY',device_type='router',ip_address=raw['gateway'],
            status='online' if values else 'unknown',latency_ms=sum(values)/len(values) if values else None,
            packet_loss_percent=(5-len(values))*20,
            jitter_ms=sum(abs(b-a) for a,b in zip(values,values[1:]))/(len(values)-1) if len(values)>1 else None)])
    return t,raw

lock=asyncio.Lock()
