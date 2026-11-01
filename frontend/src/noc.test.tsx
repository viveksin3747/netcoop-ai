import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {NocShell,NocHome,NocIncidentDetails,NocReports,InputLauncher} from './NocPages';
import {NocSettings,NocRecommendations} from './NocOperations';
import {RecommendationStatus} from './workflows';
import {navigation,incidentTabs,configurationSections} from './navigation';
import type {Incident,Recommendation} from './types';

const recommendation:Recommendation={id:'REC-test',incident_id:'INC-012345678901',priority:'P1',status:'Pending',action:'Inspect router load',rationale:'Router overload',expected_impact:'Reduce load',verification:'Repeat measurements',evidence_ids:['EV-test']};
const incident:Incident={id:recommendation.incident_id,status:'completed',created_at:'2026-11-01T01:00:00Z',telemetry:{timestamp:'2026-11-01T01:00:00Z',network_id:'NETWORK',source_type:'live',data_mode:'observed',source_reference:'test fixture',devices:[{device_id:'R1',device_type:'router',status:'online',latency_ms:6,packet_loss_percent:0}],connections:[]},quality:{core_completeness:.4,stale:false,missing_fields:{},notes:[]},correlation:{status:'completed',root_cause:'Router overload',severity:'high',confidence:.8,confidence_category:'high',confidence_method:'Test method',affected_devices:['R1'],supporting_evidence_ids:['EV-test'],limitations:[],hypotheses:[]},agents:['performance_agent','infrastructure_agent','connectivity_agent','correlation_agent','recommendation_agent','reporting_agent'].map(agent_id=>({agent_id,status:'completed',findings:[],limitations:[],started_at:'2026-11-01T01:00:00Z',ended_at:'2026-11-01T01:00:01Z'})),evidence:[{evidence_id:'EV-test',source_agent:'infrastructure_agent',device_id:'R1',metric:'cpu_usage_percent',observed_value:96,unit:'%',threshold:85,timestamp:'2026-11-01T01:00:00Z',source_reference:'fixture',abnormal:true,explanation:'High CPU'}],recommendations:[recommendation],report_id:'RPT-012345678901',error:null,timeline:[{timestamp:'2026-11-01T01:00:00Z',event:'performance_agent completed'}],speed_test:{download_mbps:120,upload_mbps:80,status:'completed',errors:[]}};
let host:HTMLDivElement;let root:Root;let writes:{url:string;body:Record<string,unknown>}[];
beforeEach(()=>{
 (globalThis as typeof globalThis&{IS_REACT_ACT_ENVIRONMENT:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
 host=document.createElement('div');document.body.append(host);root=createRoot(host);writes=[];localStorage.clear();
 incident.telemetry.timestamp=new Date().toISOString();
 vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
 vi.stubGlobal('ResizeObserver',class {constructor(private callback:ResizeObserverCallback){}observe(target:Element){this.callback([{target,contentRect:{width:600,height:260}} as ResizeObserverEntry],this as unknown as ResizeObserver);}unobserve(){}disconnect(){}});
 vi.stubGlobal('fetch',vi.fn(async(url:string,options?:RequestInit)=>{
  if(options?.method==='PUT'){writes.push({url,body:JSON.parse(String(options.body))});return new Response(JSON.stringify({status:'Completed'}),{status:200});}
  const path=String(url).replace('/api','');
  const data=path==='/health'?{status:'online'}:path==='/incidents'?[incident]:path.startsWith('/incidents/')?incident:path==='/recommendations'?[recommendation]:path==='/reports'?[{report_id:'RPT-012345678901',incident_id:incident.id,generated_at:incident.created_at,status:'completed',severity:'high',source_type:'live',data_mode:'observed',conclusion:'Actual fixture'},{report_id:'RPT-111111111111',incident_id:'period-summary',report_type:'weekly',generated_at:incident.created_at,status:'completed',severity:'info',data_mode:'observed',conclusion:'Weekly fixture'}]:path==='/monitoring'?{enabled:true,next_check_at:'2026-11-01T01:15:00Z',last_check_at:'2026-11-01T01:00:00Z',last_incident_id:incident.id,last_error:null}:path==='/settings'?{cpu_threshold:85,memory_threshold:90,latency_threshold:100,packet_loss_threshold:2,bandwidth_threshold:85,timeout_seconds:10,retry_limit:1,stale_after_minutes:60,enabled_agents:incident.agents.map(a=>a.agent_id)}:[];
  return new Response(JSON.stringify(data),{status:200});
 }));
});
afterEach(async()=>{await act(async()=>root.unmount());host.remove();vi.unstubAllGlobals();});
async function render(component:React.ReactNode,path='/'){await act(async()=>{root.render(<MemoryRouter initialEntries={[path]}>{component}</MemoryRouter>);});}
async function click(el:Element|null){expect(el).not.toBeNull();await act(async()=>{el!.dispatchEvent(new MouseEvent('click',{bubbles:true}));});}
function button(text:string){return [...host.querySelectorAll('button')].find(b=>b.textContent===text)||null;}
async function change(el:HTMLInputElement|HTMLSelectElement|HTMLTextAreaElement,value:string){await act(async()=>{Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el),'value')!.set!.call(el,value);el.dispatchEvent(new Event('change',{bubbles:true}));el.dispatchEvent(new Event('input',{bubbles:true}));});}

describe('NOC navigation and workflows',()=>{
 it('renders exactly the six primary navigation sections and functional input links',async()=>{
  await render(<NocShell><InputLauncher/></NocShell>);
  const links=[...host.querySelectorAll('nav[aria-label="Main navigation"] a')];
  expect(links.map(a=>a.textContent)).toEqual(navigation.map(n=>n.label));
  expect(links.map(a=>a.getAttribute('href'))).toEqual(navigation.map(n=>n.path));
  expect([...host.querySelectorAll('.input-launcher a')].map(a=>a.getAttribute('href'))).toEqual(['/incidents/new?mode=upload','/incidents/new?mode=live','/incidents/new?mode=demo']);
 });
 it('shows recorded live speed, health and backend monitoring without mock KPI placeholders',async()=>{
  await render(<NocHome/>);
  expect(host.textContent).toContain('120 Mbps');expect(host.textContent).toContain('80 Mbps');
  expect(host.textContent).toContain('Automatic live checks');expect(host.textContent).toContain('Recent Agent Activity');
  expect(host.textContent).toContain('Attention required');
 });
 it('separates all eight incident tabs and retains evidence and six-agent execution',async()=>{
  const {Routes,Route}=await import('react-router-dom');
  await render(<Routes><Route path="/incidents/:id" element={<NocIncidentDetails/>}/></Routes>,`/incidents/${incident.id}`);
  expect([...host.querySelectorAll('[role="tab"]')].map(b=>b.textContent)).toEqual(incidentTabs);
  expect(host.querySelector('[role="tabpanel"]')?.textContent).toContain('What is happening?');
  await click(button('Agent Execution'));expect(host.querySelectorAll('.agent-cards section')).toHaveLength(6);expect(host.textContent).toContain('1000 ms');
  await click(button('Evidence Register'));expect(host.querySelector('[role="tabpanel"]')?.textContent).toContain('EV-test');expect(host.querySelector('[role="tabpanel"]')?.textContent).not.toContain('What is happening?');
  await click(button('Related Reports'));expect(host.textContent).toContain('RPT-012345678901');
 });
 it('filters the report library by type without removing preview links',async()=>{
  await render(<NocReports/>);
  await change(host.querySelector('[aria-label="Report type filter"]')!,'weekly');
  const table=host.querySelector('tbody')!;expect(table.textContent).toContain('RPT-111111111111');expect(table.textContent).not.toContain('RPT-012345678901');
  expect(table.querySelector('a[href="/reports/RPT-111111111111"]')).not.toBeNull();
 });
 it('requires completion notes and operator confirmation before a status request',async()=>{
  await render(<RecommendationStatus r={recommendation} onChange={()=>{}}/>);
  await click(button('Verify completion'));expect(writes).toHaveLength(0);
  const confirm=button('Confirm completed') as HTMLButtonElement;expect(confirm.disabled).toBe(true);
  await change(host.querySelector('textarea')!,'Verified device recovery and repeated the measurements');
  await click(host.querySelector('.confirmation-check input'));expect(confirm.disabled).toBe(false);
  await click(confirm);expect(writes[0].body).toMatchObject({status:'Completed',operator_confirmed:true,verification_note:'Verified device recovery and repeated the measurements'});
 });
 it('starts an investigation without completing or running a network change',async()=>{
  await render(<RecommendationStatus r={recommendation} onChange={()=>{}}/>);await click(button('Start investigation'));
  expect(writes).toHaveLength(1);expect(writes[0].body.status).toBe('In Progress');expect(writes[0].url).toContain('/status');
 });
 it('organizes all ten settings sections and saves thresholds through the original endpoint',async()=>{
  await render(<NocSettings/>);
  expect([...host.querySelectorAll('nav[aria-label="Settings sections"] button')].map(b=>b.textContent)).toEqual(configurationSections);
  await click(button('Diagnostic thresholds'));expect(host.textContent).toContain('Thresholds are warning limits');
  await act(async()=>{host.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));});
  expect(writes[0].url).toBe('/api/settings');expect(writes[0].body.cpu_threshold).toBe(85);
 });
 it('opens recommendation queues without automatically changing tracking status',async()=>{
  await render(<NocRecommendations/>);expect(host.textContent).toContain('Inspect router load');
  await click(button('Completed'));expect(host.textContent).toContain('No recommendations match this queue');expect(writes).toHaveLength(0);
 });
});
