// Shared snapshot geometry and UTF-8 coordinate helpers, inlined into each controller scope.
const folders=Object.create(null),files=Object.create(null);
const root={name:'',children:[]};
const closedFolders=new Set();
const expandedFiles=new Set();
const hiddenFiles=new Set();
let layoutMode='packed',placements={packed:{},columns:{}},viewGroups=[],nodeSelection=new Set(),selectedGroup=null,arranging=false;
const nodeId=node=>(node.path?'file:':'folder:')+(node.path||node.name);
function sceneNode(id){return id.startsWith('file:')?files[id.slice(5)]:id.startsWith('folder:')?folders[id.slice(7)]:null;}
let maxY=500,maxX=800;
let overviewRelationships=null;
let projectedEdges=null;
function folderFor(name){
  if(!name)return root;
  if(folders[name])return folders[name];
  const parent=name.includes('/')?name.slice(0,name.lastIndexOf('/')):'';
  const folder={name,parent,children:[],count:0};
  folders[name]=folder;folderFor(parent).children.push(folder);
  return folder;
}
for(const path of Object.keys(data.files).sort()){
  const dir=path.includes('/')?path.slice(0,path.lastIndexOf('/')):'';
  const folder=folderFor(dir),lines=data.files[path].split(/\r\n|\n/);
  let width=650,contentWidth=0;
  for(const line of lines)contentWidth=Math.max(contentWidth,line.replace(/\t/g,'    ').length*charWidth);
  width=Math.max(width,contentWidth+70);
  const raw=new TextEncoder().encode(data.files[path]),lineOffsets=[0];
  for(let offset=0;offset<raw.length;offset++)if(raw[offset]===10)lineOffsets.push(offset+1);
  files[path]={path,text:data.files[path],lines,raw,lineOffsets,positions:new Map(),contentWidth,width:Math.min(760,width),sourceX:0,clipId:'source-window-'+Object.keys(files).length,dir};
  folder.children.push(files[path]);
  for(let ancestor=folder;ancestor!==root;ancestor=folderFor(ancestor.parent))ancestor.count++;
}
function layout(){
  overviewRelationships=null;
  projectedEdges=null;
  root.visibleCount=0;
  for(const folder of Object.values(folders))folder.visibleCount=0;
  for(const file of Object.values(files)){
    file.displayLines=file.lines.length>foldThreshold&&!expandedFiles.has(file.path)?previewLines:file.lines.length;
    file.height=file.displayLines*lineHeight+100;
    if(!hiddenFiles.has(file.path)){
      root.visibleCount++;
      for(let folder=folderFor(file.dir);folder!==root;folder=folderFor(folder.parent))folder.visibleCount++;
    }
  }
  const included=node=>node.children?node.visibleCount>0:!hiddenFiles.has(node.path);
  for(const node of [...Object.values(folders),...Object.values(files)])node.hidden=true;
  function measure(folder){
    if(closedFolders.has(folder.name)){folder.width=320;folder.height=90;return;}
    let area=0,widest=320;
    for(const child of folder.children.filter(included)){
      if(child.children)measure(child);
      area+=(child.width+40)*(child.height+40);widest=Math.max(widest,child.width);
    }
    const rowWidth=layoutMode==='columns'?Number.MAX_SAFE_INTEGER:Math.max(widest,Math.sqrt(area*1.4));
    let x=24,y=52,rowHeight=0,right=320,bottom=52;
    for(const child of folder.children.filter(included)){
      if(x>24&&x+child.width>rowWidth+24){x=24;y+=rowHeight+40;rowHeight=0;}
      const placed=placements[layoutMode][nodeId(child)];
      child.offsetX=placed?.x??x;child.offsetY=placed?.y??y;
      right=Math.max(right,child.offsetX+child.width);rowHeight=Math.max(rowHeight,child.offsetY-y+child.height);x+=child.width+40;
      bottom=Math.max(bottom,child.offsetY+child.height);
    }
    folder.width=right+24;folder.height=bottom+24;
  }
  function place(folder,x,y){
    folder.x=x;folder.y=y;folder.hidden=false;
    if(closedFolders.has(folder.name))return;
    for(const child of folder.children.filter(included)){
      if(child.children)place(child,x+child.offsetX,y+child.offsetY);
      else{child.x=x+child.offsetX;child.y=y+child.offsetY;child.hidden=false;}
    }
  }
  measure(root);place(root,60,40);
  maxX=root.width+120;maxY=root.height+80;
}
function position(span){
  const f=files[span.file],key=span.start+':'+span.end;
  if(f.positions.has(key))return f.positions.get(key);
  let low=0,high=f.lineOffsets.length;
  while(low+1<high){const middle=Math.floor((low+high)/2);if(f.lineOffsets[middle]<=span.start)low=middle;else high=middle;}
  const prefix=new TextDecoder().decode(f.raw.subarray(f.lineOffsets[low],span.start));
  const result={line:low+1,col:prefix.replace(/\t/g,'    ').length,x:textWidth(prefix),
    token:new TextDecoder().decode(f.raw.subarray(span.start,span.end))};
  result.width=textWidth(result.token.split(/\r\n|\n/)[0]);
  f.positions.set(key,result);return result;
}
function anchor(span){
  const f=files[span.file],p=position(span);
  for(let folder=folderFor(f.dir);folder!==root;folder=folderFor(folder.parent))
    if(closedFolders.has(folder.name)&&!folder.hidden)return {x:folder.x+folder.width/2,y:folder.y+folder.height/2};
  if(p.line>f.displayLines)return {x:f.x+f.width/2,y:f.y+f.height-15};
  const point=sourcePoint(span),clip=sourceWindow(f);
  return {x:Math.max(clip.x,Math.min(clip.x+clip.width,point.x)),y:point.y};
}
function sourceWindow(file){return {x:file.x+50,y:file.y+codeTop-16,width:file.width-66,height:file.height-codeTop-12};}
function sourcePoint(span){const f=files[span.file],p=position(span);return {x:f.x+52+p.x-f.sourceX,y:f.y+codeTop+(p.line-1)*lineHeight};}
function sourceLimit(file){
  if(!file.extentMeasured){
    for(const line of file.lines)if(/[^\x00-\x7f]/.test(line))file.contentWidth=Math.max(file.contentWidth,textWidth(line));
    file.extentMeasured=true;
  }
  return Math.max(0,file.contentWidth-(file.width-70));
}
function revealSource(span){
  const f=files[span.file],p=position(span),width=f.width-70;
  f.contentWidth=Math.max(f.contentWidth,p.x+p.width);
  if(p.x<f.sourceX+12)f.sourceX=Math.max(0,p.x-24);
  else if(p.x+Math.min(p.width,width-48)>f.sourceX+width-12)f.sourceX=Math.min(sourceLimit(f),Math.max(0,p.x+Math.min(p.width,width-48)-width+24));
}
function sourceOffsets(){return Object.fromEntries(Object.values(files).filter(f=>f.sourceX).map(f=>[f.path,f.sourceX]));}
function restoreSourceOffsets(offsets={}){for(const file of Object.values(files))file.sourceX=offsets[file.path]||0;}
function overviewContainer(path){
  const file=files[path];
  for(let folder=folderFor(file.dir);folder!==root;folder=folderFor(folder.parent))
    if(closedFolders.has(folder.name)&&!folder.hidden)return folder;
  return file;
}
function overviewEdges(){
  if(overviewRelationships)return overviewRelationships;
  const groups=new Map();
  for(const edge of visibleEdges()){
    const from=overviewContainer(edge.from.file),to=overviewContainer(edge.to.file);
    const key=JSON.stringify([from.path||from.name,to.path||to.name,edge.kind]);
    if(groups.has(key)){groups.get(key).count++;continue;}
    const same=from===to;
    groups.set(key,{edge,count:1,
      a:{x:from.x+from.width*(same ? 0.3 : 0.5),y:from.y+from.height*(same ? 0.4 : 0.5)},
      b:{x:to.x+to.width*(same ? 0.7 : 0.5),y:to.y+to.height*(same ? 0.6 : 0.5)}});
  }
  overviewRelationships=[...groups.values()];
  return overviewRelationships;
}
layout();
