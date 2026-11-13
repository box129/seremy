// Retained renderer-neutral records, with SVG as the semantic/input adapter.
function createSceneAdapter(namespace){
  const retained=new WeakMap(),records=new WeakMap();
  let frame=null,nextId=0,created=0,removed=0;
  function recordFor(node){
    if(!records.has(node))records.set(node,{id:++nextId,tag:node.localName,attrs:{},style:{},text:'',children:[]});
    return records.get(node);
  }
  function state(parent){
    if(!frame.has(parent))frame.set(parent,{counts:new Map(),used:new Set(),index:0,children:[]});
    if(!retained.has(parent))retained.set(parent,new Map());
    return frame.get(parent);
  }
  function identity(tag,attrs){
    const keys=Object.keys(attrs).filter(key=>key.startsWith('data-')&&!key.startsWith('data-clip-')&&!['data-site-count','data-overview','data-render-start'].includes(key));
    return tag+'|'+(attrs.class||'').replace(/\b(selected|faded)\b/g,'').trim()+'|'+JSON.stringify(keys.map(key=>[key,attrs[key]]));
  }
  return {
    recordFor,
    begin(){frame=new Map();},
    add(parent,tag,attrs,text){
      if(!frame){const node=document.createElementNS(namespace,tag);for(const [key,value] of Object.entries(attrs))node.setAttribute(key,value);node.textContent=text;parent.append(node);return node;}
      const current=state(parent),cache=retained.get(parent),signature=identity(tag,attrs),occurrence=current.counts.get(signature)||0;
      current.counts.set(signature,occurrence+1);const key=signature+'@'+occurrence;
      let node=cache.get(key);
      if(!node){node=document.createElementNS(namespace,tag);cache.set(key,node);created++;}
      const record=recordFor(node);
      for(const key of Object.keys(record.attrs))if(!(key in attrs))node.removeAttribute(key);
      for(const [key,value] of Object.entries(attrs))if(record.attrs[key]!==value)node.setAttribute(key,value);
      if(record.text!==text){
        const own=node.firstChild?.nodeType===Node.TEXT_NODE?node.firstChild:null;
        if(text){if(own)own.nodeValue=text;else node.prepend(document.createTextNode(text));}else if(own)own.remove();
      }
      record.attrs=attrs;record.text=text;record.children=[];
      if(retained.has(node))state(node);
      const expected=parent.children[current.index++];if(expected!==node)parent.insertBefore(node,expected||null);
      current.used.add(key);current.children.push(record);return node;
    },
    style(node,values){
      const record=recordFor(node);
      for(const [key,value] of Object.entries(values))if(record.style[key]!==value){node.style[key]=value;record.style[key]=value;}
    },
    raise(parent,node){
      parent.append(node);const children=state(parent).children,record=recordFor(node),index=children.indexOf(record);
      if(index>=0)children.splice(index,1);children.push(record);
    },
    finish(root){
      for(const [parent,current] of frame){
        const cache=retained.get(parent);
        for(const [key,node] of cache)if(!current.used.has(key)){node.remove();cache.delete(key);removed++;}
        recordFor(parent).children=current.children;
      }
      frame=null;return recordFor(root);
    },
    info(){return {created,removed};}
  };
}
