export async function api<T>(path:string, options:RequestInit={}):Promise<T>{
 const response=await fetch('/api'+path,{...options,headers:options.body instanceof FormData?options.headers:{'Content-Type':'application/json',...options.headers}});
 if(!response.ok){let message;try{const body=await response.json();message=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail);}catch{message=`Request failed (${response.status})`;}throw new Error(message);}
 return response.json();
}
export function post<T>(path:string,body:unknown={}){return api<T>(path,{method:'POST',body:JSON.stringify(body)});}
