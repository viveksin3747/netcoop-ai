from .schemas import Telemetry, now
from datetime import datetime, timedelta, timezone

SCENARIOS = [
 {'id':'router-overload','name':'Router Overload','description':'Router CPU pressure with latency and packet loss.'},
 {'id':'network-congestion','name':'Network Congestion','description':'Saturated uplink with elevated delay and jitter.'},
 {'id':'connectivity-failure','name':'Connectivity Failure','description':'An unreachable device and a down network link.'},
 {'id':'resource-failure','name':'Infrastructure Resource Failure','description':'Memory and thermal pressure on an edge server.'},
 {'id':'healthy-network','name':'Healthy Network','description':'A normal snapshot with no threshold violations.'},
 {'id':'slow-response','name':'Slow websites and apps','description':'Long response times without enough evidence to identify the cause.'},
 {'id':'unstable-calls','name':'Unstable voice and video calls','description':'Timing variation and packet loss can interrupt calls.'},
 {'id':'wifi-disconnected','name':'Wi-Fi access point disconnected','description':'A wireless access point is offline and its uplink is down.'},
 {'id':'server-cpu','name':'Busy application server','description':'A server is overloaded while the router remains healthy.'},
 {'id':'overheating','name':'Overheating device','description':'High temperature on a switch needs investigation.'},
 {'id':'multiple-causes','name':'Competing causes','description':'Router pressure and heavy traffic produce an uncertain assessment.'},
 {'id':'missing-data','name':'Incomplete monitoring data','description':'Missing readings prevent a reliable conclusion.'},
 {'id':'severe-packet-loss','name':'Severe packet loss','description':'Many test packets fail to arrive. Explore what to check before assuming a cause.'},
 {'id':'branch-outage','name':'Multiple devices disconnected','description':'The server and Wi-Fi access point are offline with down links.'},
 {'id':'router-memory','name':'Router memory exhausted','description':'Very high router memory use accompanies slow responses and lost packets.'},
 {'id':'thermal-emergency','name':'Severe overheating','description':'A server reports extreme heat and delayed responses. Prioritize physical safety and escalation.'},
 {'id':'stale-outage','name':'Old outage readings','description':'Yesterday’s outage data cannot establish what is happening now.'},
 {'id':'campus-outage','name':'Campus segment outage','description':'A campus switch loses connectivity; supplied hostel and department links show potential downstream impact.'},
 {'id':'router-cascade','name':'Router failure dependency chain','description':'A router is offline; switches, department services and hostel Wi-Fi are potentially affected along supplied dependencies.'},
]

def scenario(key):
    if key not in [s['id'] for s in SCENARIOS]:
        raise ValueError('Unknown demo scenario')
    devices = [dict(device_id=name, device_type=kind, status='online',cpu_usage_percent=30,
        memory_usage_percent=45,latency_ms=12,packet_loss_percent=0,jitter_ms=3,
        bandwidth_utilization_percent=35,interface_errors=0,dropped_packets=0,uptime_seconds=86400,temperature_c=42)
        for name,kind in [('RTR-01','router'),('SW-01','switch'),('SRV-01','server'),('AP-01','access point')]]
    links = [dict(source_device='RTR-01',target_device=d['device_id'],status='active') for d in devices[1:]]
    if key in ('campus-outage','router-cascade'):
        devices[0].update(location='Core network',segment_id='Core')
        devices[1].update(location='Campus distribution',segment_id='Distribution',status='offline')
        devices[2].update(department='Computer Science',segment_id='Academic LAN',services=['Learning portal'])
        devices[3].update(hostel='Hostel A',segment_id='Hostel Wi-Fi')
        links=[dict(source_device='RTR-01',target_device='SW-01',status='down'),
            dict(source_device='SW-01',target_device='SRV-01',status='unknown'),
            dict(source_device='SW-01',target_device='AP-01',status='unknown')]
        if key=='router-cascade':
            devices[0].update(status='offline',packet_loss_percent=100,latency_ms=None)
            devices[1].update(status='unknown')
    if key=='router-overload': devices[0].update(cpu_usage_percent=96,latency_ms=180,packet_loss_percent=8,jitter_ms=35)
    if key=='network-congestion': devices[1].update(bandwidth_utilization_percent=98,latency_ms=160,packet_loss_percent=4,jitter_ms=40)
    if key=='connectivity-failure':
        devices[2].update(status='offline',packet_loss_percent=100,latency_ms=None)
        links[1]['status']='down'
    if key=='resource-failure': devices[2].update(memory_usage_percent=97,temperature_c=89,latency_ms=140)
    if key=='slow-response': devices[2].update(latency_ms=450)
    if key=='unstable-calls': devices[3].update(jitter_ms=95,packet_loss_percent=12)
    if key=='wifi-disconnected':
        devices[3].update(status='offline',packet_loss_percent=100,latency_ms=None)
        links[2]['status']='down'
    if key=='server-cpu': devices[2].update(cpu_usage_percent=98,latency_ms=240,packet_loss_percent=5)
    if key=='overheating': devices[1].update(temperature_c=96,latency_ms=150)
    if key=='multiple-causes': devices[0].update(cpu_usage_percent=97,bandwidth_utilization_percent=98,latency_ms=240,packet_loss_percent=9)
    if key=='missing-data':
        devices=[dict(device_id='RTR-01',device_type='router',status='unknown')]
        links=[]
    if key=='severe-packet-loss': devices[0].update(packet_loss_percent=65,latency_ms=600,jitter_ms=120)
    if key=='branch-outage':
        for index in (2,3):
            devices[index].update(status='offline',packet_loss_percent=100,latency_ms=None)
            links[index-1]['status']='down'
    if key=='router-memory': devices[0].update(memory_usage_percent=99,latency_ms=350,packet_loss_percent=15)
    if key=='thermal-emergency': devices[2].update(temperature_c=110,latency_ms=800)
    if key=='stale-outage':
        devices[2].update(status='offline',packet_loss_percent=100,latency_ms=None)
        links[1]['status']='down'
    timestamp=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat() if key=='stale-outage' else now()
    return Telemetry(timestamp=timestamp,network_id='NET-DEMO-01',source_type='demo',data_mode='simulated',
        source_reference=f'synthetic scenario: {key}',devices=devices,connections=links)
