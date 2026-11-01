import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Network,ArrowRight,CheckCircle2,Clock,TriangleAlert} from 'lucide-react';
import {api} from './api';
import type {Agent,Incident} from './types';
export const agentNames=['Performance','Infrastructure','Connectivity','Fault Correlation','Recommendation','Reporting'];
export const agentIds=['performance_agent','infrastructure_agent','connectivity_agent','correlation_agent','recommendation_agent','reporting_agent'];
export const pct=(n:number)=>`${Math.round(n*100)}%`;
export const date=(value:string)=>new Date(value).toLocaleString(undefined,{timeZone:readPreferences().timezone==='local'?undefined:readPreferences().timezone});
export type Preferences={workspace:string;density:string;timezone:string;reportFormat:string};
export function readPreferences():Preferences{try{return {workspace:'Network Operations',density:'comfortable',timezone:'local',reportFormat:'preview',...JSON.parse(localStorage.getItem('netcoop.preferences')||'{}')};}catch{return {workspace:'Network Operations',density:'comfortable',timezone:'local',reportFormat:'preview'};}}
export function savePreferences(value:Preferences){localStorage.setItem('netcoop.preferences',JSON.stringify(value));window.dispatchEvent(new Event('netcoop-preferences'));}
export function Loading({label='Loading workspace…'}:{label?:string}){return <div className="loading-state" role="status" aria-busy="true"><span className="loading-dot"/>{label}</div>;}
export function Tabs({items,value,onChange,label='Workspace sections'}:{items:string[];value:string;onChange:(s:string)=>void;label?:string}){return <div className="tabs" role="tablist" aria-label={label}>{items.map(item=><button type="button" role="tab" aria-selected={value===item} className={value===item?'active':''} key={item} onClick={()=>onChange(item)}>{item}</button>)}</div>;}
export function Badge({value}:{value:string}){return <span className={`badge ${value.toLowerCase().replaceAll(' ','-')}`}>{value.replaceAll('_',' ')}</span>;}
export function Empty({text='No records yet. Run your first diagnosis to get started.'}:{text?:string}){return <div className="empty"><Network size={30}/><p>{text}</p><Link to="/start">Start diagnosis <ArrowRight size={14}/></Link></div>;}
export function ErrorBox({error}:{error:string}){return error?<div role="alert" className="error"><TriangleAlert size={18}/>{error}</div>:null;}
export function useData<T>(path:string,refresh=0){const [record,setRecord]=useState<{path:string;data:T|null}>({path,data:null});const [error,setError]=useState('');useEffect(()=>{let alive=true;setError('');api<T>(path).then(d=>{if(alive){setRecord({path,data:d});setError('');}}).catch(e=>{if(alive){setRecord({path,data:null});setError(e.message);}});return()=>{alive=false;};},[path,refresh]);return {data:record.path===path?record.data:null,error};}
export function Title({title,subtitle,action}:{title:string;subtitle:string;action?:React.ReactNode}){return <div className="page-title"><div><h1>{title}</h1><p>{subtitle}</p></div>{action}</div>;}
export function AgentList({agents}:{agents:Agent[]}){return <div className="agent-list">{agentIds.map((id,k)=>{const a=agents.find(x=>x.agent_id===id);return <div key={id}><span className={`agent-dot ${a?.status||'idle'}`}>{a?.status==='completed'?<CheckCircle2 size={16}/>:<Clock size={16}/>}</span><span>{agentNames[k]} Agent</span><Badge value={a?.status||'idle'}/></div>;})}</div>;}
export function Stat({icon,label,value,note,color}:{icon:React.ReactNode;label:string;value:string;note:string;color:string}){return <section className="stat"><div className={`stat-icon ${color}`}>{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{note}</small></div></section>;}
export function Situation({incident:i}:{incident:Incident}){
 const c=i.correlation;
 const explanations:Record<string,[string,string,string]>={
 'Router overload':['The router is working too hard.','Websites, calls, or connected apps may respond slowly.','Ask your network administrator to check what is using the router’s processing capacity.'],
 'Network congestion':['A network connection is carrying too much traffic.','Downloads or calls may slow down while traffic queues up.','Check for large transfers and ask an administrator to review connection capacity.'],
 'Connectivity failure':['A device or network link is reported disconnected.','Services using that connection may be unreachable.','Check power and cable connections, then ask an administrator to test the affected device.'],
 'Infrastructure resource failure':['A device is under memory or heat pressure.','Apps running on that device may slow down or stop responding.','Ask the device owner to check available memory, cooling, and device health.'],
 'Compute resource pressure':['A device is using too much processing capacity.','Applications using that device may respond slowly.','Ask the device owner to inspect running processes.'],
 'No fault observed in this snapshot':['The supplied readings show no detected network problem.','No disruption is established by this check.','Continue monitoring and repeat the check if symptoms return.']};
 const [happening,impact,next]=explanations[c?.root_cause||'']||['There is not enough clear evidence to explain the problem yet.','The effect on services is not established.','Collect fresh readings and ask an administrator to review the technical evidence.'];
 return <section className="situation"><span className="eyebrow">{i.telemetry.data_mode==='simulated'?'DEMO EXPLANATION':'LATEST CHECK'} · {date(i.telemetry.timestamp)}</span><h2>What is happening?</h2><p>{i.status==='running'?'The network readings are being checked.':happening}</p><h3>What could this mean for you?</h3><p>{impact} This is a possible impact, not a confirmed service outage.</p><h3>What should happen next?</h3><p>{next}</p><Link className="button" to={`/incidents/${i.id}`}>View findings and technical evidence <ArrowRight size={14}/></Link><p className="muted">Based on the supplied readings at the time shown above. No repairs have been performed.</p></section>;
}
