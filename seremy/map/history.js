// Private device history. Reports are saved only after the visitor chooses Save.
(()=>{
  const names=['map.html','architecture.md','graph.json','validation.json','manifest.json'];
  let active=null,captured=null,capturing=null,urls=[];
  const history=document.createElement('button');
  history.id='history';history.textContent='Saved on this device';
  get('connect').after(history);
  const save=document.createElement('button');
  save.id='save-device';save.textContent='Save on this device';get('outputs').append(save);
  const dialog=document.createElement('dialog');dialog.id='history-dialog';
  const heading=document.createElement('h2');heading.textContent='Saved on this device';dialog.append(heading);
  const notice=document.createElement('p');
  notice.textContent='Saved reports include source code. They are stored in this browser. Clearing site data or browser storage eviction can remove them. Download files for a separate copy.';
  dialog.append(notice);
  const list=document.createElement('div');dialog.append(list);
  const close=document.createElement('button');close.textContent='Close history';close.onclick=()=>dialog.close();dialog.append(close);
  document.body.append(dialog);
  const database=new Promise((resolve,reject)=>{
    const request=indexedDB.open('seremy-device-history',1);
    request.onupgradeneeded=()=>request.result.createObjectStore('reports',{keyPath:'id'});
    request.onsuccess=()=>resolve(request.result);
    request.onerror=()=>reject(request.error);
  });
  // Attach a rejection handler even before the visitor first opens history.
  database.catch(()=>status('Device history is unavailable in this browser. Downloads are still available.'));
  async function storage(mode,operation){
    const db=await database;
    return new Promise((resolve,reject)=>{
      const transaction=db.transaction('reports',mode);
      const request=operation(transaction.objectStore('reports'));
      transaction.oncomplete=()=>resolve(request.result);
      transaction.onabort=()=>reject(transaction.error||new Error('History could not be saved.'));
      transaction.onerror=()=>reject(transaction.error);
    });
  }
  async function verify(files){
    const manifest=JSON.parse(files['manifest.json']);
    for(const name of names.slice(0,-1)){
      const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(files[name]));
      const hash=Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('');
      if(hash!==manifest.files[name])throw new Error('Saved report verification failed.');
    }
  }
  async function persistReport(report){
    const db=await database;
    return new Promise((resolve,reject)=>{
      const transaction=db.transaction('reports','readwrite'),store=transaction.objectStore('reports');
      let failure;
      store.getAll().onsuccess=event=>{
        const others=event.target.result.filter(item=>item.id!==report.id);
        const size=new TextEncoder().encode(JSON.stringify([...others,report])).length;
        if(others.length>=10||size>50*1024*1024){
          failure=new Error('Device history is full. Delete an older report first.');transaction.abort();return;
        }
        store.put(report);
      };
      transaction.oncomplete=resolve;
      transaction.onabort=()=>reject(failure||transaction.error);
      transaction.onerror=()=>reject(transaction.error);
    });
  }
  function release(){for(const url of urls)URL.revokeObjectURL(url);urls=[];}
  function fileUrl(text,type){const url=URL.createObjectURL(new Blob([text],{type}));urls.push(url);return url;}
  async function openReport(report,saved=true){
    if(job)throw new Error('Wait for the current analysis to finish before opening a saved report.');
    await verify(report.files);
    release();active=report;publication=report.id;repositoryName=report.name;
    const restoreDrafts=()=>{
      if(active!==report)return;
      visibleDrafts=Array.isArray(report.drafts)?report.drafts.filter(draft=>typeof draft.markdown==='string'&&draft.markdown.length<=262144).slice(0,16):[];
      selectedDocument=null;
      if(!get('doc').hidden)showDocumentation(report.files['architecture.md']);
    };
    restoreDrafts();
    get('map').src=fileUrl(report.files['map.html'],'text/html');
    get('map').srcdoc=report.files['map.html'];
    get('map').addEventListener('load',restoreDrafts,{once:true});
    get('download-map').href=get('map').src;get('download-map').hidden=false;
    get('download').href=fileUrl(report.files['graph.json'],'application/json');
    get('download-doc').href=fileUrl(report.files['architecture.md'],'text/markdown');
    get('checks').href=fileUrl(report.files['validation.json'],'application/json');
    get('map').hidden=false;get('doc').hidden=true;get('outputs').hidden=false;get('empty').hidden=true;
    document.body.classList.add('loaded');get('connect').textContent=report.name;
    get('map-tab').setAttribute('aria-pressed','true');get('doc-tab').setAttribute('aria-pressed','false');
    get('summary').textContent=saved?'Saved on this device · '+new Date(report.saved).toLocaleString():'Prepared public example · Save on this device to keep a copy';
    status('Report opened');save.disabled=false;dialog.close();
    window.dispatchEvent(new Event('seremy-restored-report'));
  }
  async function showHistory(){
    list.replaceChildren();
    const reports=await storage('readonly',store=>store.getAll());
    if(!reports.length){const empty=document.createElement('p');empty.textContent='No saved reports yet.';list.append(empty);}
    for(const report of reports.sort((a,b)=>b.saved-a.saved)){
      const row=document.createElement('p');
      const open=document.createElement('button');open.textContent=report.name;open.setAttribute('aria-label','Open saved '+report.name);
      open.onclick=()=>openReport(report).catch(error=>status(error.message));
      const remove=document.createElement('button');remove.textContent='Delete';remove.setAttribute('aria-label','Delete saved '+report.name);
      remove.onclick=async()=>{
        try{await storage('readwrite',store=>store.delete(report.id));await showHistory();}
        catch(error){status(error.message);}
      };
      row.append(open,' · '+new Date(report.saved).toLocaleString()+' ',remove);list.append(row);
    }
  }
  history.onclick=async()=>{
    try{await showHistory();dialog.showModal();}catch(error){status('Device history could not be opened.');}
  };
  save.onclick=async()=>{
    if(!publication||job)return;
    const id=publication,name=repositoryName;
    save.disabled=true;
    try{
      const report=active?{...active,saved:Date.now(),drafts:visibleDrafts}:await capture(id,name);
      if(publication!==id)throw new Error('The active report changed. Save the current report again.');
      report.saved=Date.now();report.drafts=visibleDrafts;
      await persistReport(report);
      status('Saved on this device');get('summary').textContent='Saved on this device · '+new Date(report.saved).toLocaleString();
    }catch(error){status(error.message||'Device history could not be saved. Download the files instead.');}
    finally{save.disabled=false;}
  };
  const liveDocumentation=get('doc-tab').onclick;
  get('doc-tab').onclick=()=>{
    const report=active||(captured?.id===publication?captured:null);
    if(!report)return liveDocumentation();
    showDocumentation(report.files['architecture.md']);get('doc').hidden=false;get('map').hidden=true;
    get('doc-tab').setAttribute('aria-pressed','true');get('map-tab').setAttribute('aria-pressed','false');
  };
  async function capture(id,name){
    if(captured?.id===id)return captured;
    if(capturing?.id===id)return capturing.promise;
    const promise=(async()=>{
      const files={};
      for(const filename of names){
        const response=await fetch('/reports/'+id+'/'+filename);
        if(!response.ok)throw new Error('Report files are unavailable. Keep this tab open and download available documentation.');
        files[filename]=await response.text();
      }
      await verify(files);
      const report={id,name,saved:Date.now(),files};
      if(publication===id)captured=report;
      return report;
    })();
    capturing={id,promise};
    try{return await promise;}finally{if(capturing?.id===id)capturing=null;}
  }
  window.addEventListener('seremy-publication',()=>{
    active=null;captured=null;save.disabled=false;release();
    capture(publication,repositoryName).catch(error=>status(error.message));
  });
  window.addEventListener('seremy-open-example',async()=>{
    try{
      const response=await fetch('/example-report');
      if(!response.ok)throw new Error('The example is unavailable. Try analyzing your repository.');
      await openReport(await response.json(),false);
      window.dispatchEvent(new Event('seremy-example-opened'));
    }catch(error){status(error.message);}
  });
})();
