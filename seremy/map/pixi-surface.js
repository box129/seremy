// Pixi paints the controller's retained scene. SVG provides source semantics and hit testing.
window.createSeremyPixiSurface=async function(map,world){
  const app=new PIXI.Application();
  await app.init({width:map.clientWidth,height:map.clientHeight,preference:'webgl',autoStart:false,
    resolution:devicePixelRatio,autoDensity:true,antialias:true,backgroundAlpha:0});
  const canvas=app.canvas;
  canvas.hidden=true;
  canvas.id='pixi-surface';canvas.setAttribute('aria-hidden','true');
  map.parentElement.insertBefore(canvas,map);
  const scene=new PIXI.Container(),highlight=new PIXI.Graphics();app.stage.addChild(scene);scene.addChild(highlight);
  const cache=new Map(),widths=new Map(),ascents=new Map();
  let used=new Set(),order=0,scale=1,hover=null,focused=null;
  const palette={file:{fill:'#1e1e1e',stroke:'#606773'},folder:{fill:'#33333333',stroke:'#555555'},
    'source-focus':{fill:'#d7ac452b',stroke:'#edc96c',width:1.5},
    'view-group':{fill:'#8198be0c',stroke:'#8198be',dash:true},
    'arranged-selection':{stroke:'#a6bbde',width:2},wire:{stroke:'#708198',width:2}};
  const colors={code:'#cccccc',name:'#dddddd',number:'#777777',keyword:'#bb97cf',comment:'#819574',string:'#c4b28c',literal:'#91b8be'};
  function color(value){
    if(!value||value==='none'||value==='transparent')return null;
    let hex=value.replace('#','');if(hex.length===3)hex=hex.split('').map(value=>value+value).join('');
    return {color:parseInt(hex.slice(0,6),16),alpha:hex.length===8?parseInt(hex.slice(6),16)/255:1};
  }
  function object(key,create){
    used.add(key);let record=cache.get(key);
    if(!record){record={node:create(),signature:null};cache.set(key,record);scene.addChild(record.node);}
    if(scene.getChildIndex(record.node)!==order)scene.setChildIndex(record.node,order);order++;
    return record;
  }
  function path(graphics,value){
    const parts=value.match(/[a-zA-Z]|[-+]?(?:\d*\.)?\d+(?:e[-+]?\d+)?/gi)||[];
    let index=0,x=0,y=0,startX=0,startY=0,command=null,tangent={x:1,y:0};
    while(index<parts.length){
      if(/[a-z]/i.test(parts[index])&&!/^[-+\d.]/.test(parts[index]))command=parts[index++];
      const relative=command===command?.toLowerCase(),kind=command?.toUpperCase();
      const number=()=>Number(parts[index++]);
      if(kind==='M'||kind==='L'){
        const nextX=number()+(relative?x:0),nextY=number()+(relative?y:0);
        if(kind==='M'){graphics.moveTo(nextX,nextY);startX=nextX;startY=nextY;command=relative?'l':'L';}
        else graphics.lineTo(nextX,nextY);
        tangent={x:nextX-x,y:nextY-y};x=nextX;y=nextY;
      }else if(kind==='H'){const next=number()+(relative?x:0);graphics.lineTo(next,y);tangent={x:next-x,y:0};x=next;}
      else if(kind==='V'){const next=number()+(relative?y:0);graphics.lineTo(x,next);tangent={x:0,y:next-y};y=next;}
      else if(kind==='C'){
        const offsetX=relative?x:0,offsetY=relative?y:0;
        const ax=number()+offsetX,ay=number()+offsetY,bx=number()+offsetX,by=number()+offsetY;
        const nextX=number()+offsetX,nextY=number()+offsetY;
        graphics.bezierCurveTo(ax,ay,bx,by,nextX,nextY);tangent={x:nextX-bx,y:nextY-by};x=nextX;y=nextY;
      }else if(kind==='Z'){graphics.closePath();x=startX;y=startY;command=null;}
      else throw new Error('Unsupported scene path command');
    }
    return {x,y,tangent};
  }
  function dashedRect(graphics,x,y,width,height,dash){
    for(const [ax,ay,bx,by] of [[x,y,x+width,y],[x+width,y,x+width,y+height],[x+width,y+height,x,y+height],[x,y+height,x,y]]){
      const length=Math.hypot(bx-ax,by-ay);
      for(let offset=0;offset<length;offset+=dash*1.625){const end=Math.min(length,offset+dash);
        graphics.moveTo(ax+(bx-ax)*offset/length,ay+(by-ay)*offset/length).lineTo(ax+(bx-ax)*end/length,ay+(by-ay)*end/length);}
    }
  }
  function shape(element){
    if(element.classList.contains('hit')||element.classList.contains('token'))return;
    const base=Object.entries(palette).find(([name])=>element.classList.contains(name))?.[1]||{};
    const fill=color(base.fill||element.getAttribute('fill'));
    const stroke=color(element.classList.contains('selected')?'#d3ad65':base.stroke||element.getAttribute('stroke'));
    const width=(element.classList.contains('selected')?4:base.width||1)/(element.getAttribute('vector-effect')==='non-scaling-stroke'?scale:1);
    const signature=JSON.stringify([element.getAttribute('x'),element.getAttribute('y'),element.getAttribute('width'),element.getAttribute('height'),element.getAttribute('rx'),element.getAttribute('d'),fill,stroke,width,base.dash,element.classList.contains('faded'),element.hasAttribute('marker-end')]);
    const record=object(element,()=>new PIXI.Graphics());
    if(record.signature===signature)return;
    record.signature=signature;const graphics=record.node;graphics.clear();
    let end=null;
    if(element.tagName==='rect'){
      const [x,y,w,h]=['x','y','width','height'].map(key=>Number(element.getAttribute(key)));
      graphics.roundRect(x,y,w,h,Number(element.getAttribute('rx')||0));
      if(fill)graphics.fill(fill);
      if(base.dash){if(!fill)graphics.clear();else graphics.beginPath();dashedRect(graphics,x,y,w,h,8/scale);}
    }else end=path(graphics,element.getAttribute('d')||'');
    if(element.tagName!=='rect'&&fill)graphics.fill(fill);
    if(stroke)graphics.stroke({...stroke,width});
    graphics.alpha=element.classList.contains('faded')?0.2:1;
    if(end&&element.hasAttribute('marker-end')){
      const angle=Math.atan2(end.tangent.y,end.tangent.x),length=width*7,side=width*3.5;
      const bx=end.x-Math.cos(angle)*length,by=end.y-Math.sin(angle)*length;
      graphics.moveTo(end.x,end.y).lineTo(bx-Math.sin(angle)*side,by+Math.cos(angle)*side)
        .lineTo(bx+Math.sin(angle)*side,by-Math.cos(angle)*side).closePath().fill(0x91a0b5);
    }
  }
  function sourceText(element){
    const named=element.classList.contains('name'),baseSize=named?17:14;
    const size=Number.parseFloat(element.style.fontSize)||baseSize,factor=size/baseSize;
    const family=named?['Segoe UI','system-ui']:['Consolas','monospace'],weight=named?'600':'400';
    const resolution=Math.max(2,2**Math.ceil(Math.log2(Math.max(1,scale*devicePixelRatio))));
    let x=Number(element.getAttribute('x')),y=Number(element.getAttribute('y'));
    function visit(node,currentColor){
      if(node.nodeType===Node.TEXT_NODE){
        const value=node.textContent;if(!value)return;
        const style={fontFamily:family,fontSize:baseSize,fontWeight:weight,fill:currentColor};
        if(element.style.stroke)style.stroke={color:element.style.stroke,width:(Number.parseFloat(element.style.strokeWidth)||0)/factor};
        const signature=JSON.stringify([value,style,resolution]);
        const record=object(node,()=>new PIXI.Text({text:value,style,resolution}));
        if(record.signature!==signature){record.signature=signature;record.node.text=value;record.node.style=style;record.node.resolution=resolution;}
        const fontKey=JSON.stringify([family,weight,baseSize]);
        if(!ascents.has(fontKey))ascents.set(fontKey,PIXI.CanvasTextMetrics.measureText('M',record.node.style).fontProperties.ascent);
        record.node.scale.set(factor);record.node.position.set(x,y-ascents.get(fontKey)*factor);
        const widthKey=JSON.stringify([fontKey,value]);
        if(!widths.has(widthKey))widths.set(widthKey,PIXI.CanvasTextMetrics.measureText(value,record.node.style).width);
        x+=widths.get(widthKey)*factor;
      }else if(node.nodeType===Node.ELEMENT_NODE&&node.tagName!=='title'){
        if(node.hasAttribute('x'))x=Number(node.getAttribute('x'));if(node.hasAttribute('y'))y=Number(node.getAttribute('y'));
        const next=Object.keys(colors).find(name=>node.classList.contains(name));
        for(const child of node.childNodes)visit(child,next?colors[next]:currentColor);
      }
    }
    for(const child of element.childNodes)visit(child,named?colors.name:colors.code);
  }
  function outline(){
    highlight.clear();const element=focused||hover;
    if(!element?.isConnected||!world.contains(element))return;
    const box=element.getBBox();highlight.rect(box.x-1,box.y-1,box.width+2,box.height+2).stroke({color:0x9cb9e5,width:1.5/scale});
  }
  const gl=app.renderer.gl,debug=gl.getExtension('WEBGL_debug_renderer_info');
  function render(){if(gl.isContextLost())return;outline();scene.setChildIndex(highlight,scene.children.length-1);app.render();}
  const events={
    pointerover(event){hover=event.target.closest('.token,.name');if(!canvas.hidden)render();},
    pointerleave(){hover=null;if(!canvas.hidden)render();},
    focusin(event){focused=event.target;if(!canvas.hidden)render();},
    focusout(){focused=null;if(!canvas.hidden)render();}
  };
  for(const [name,handler] of Object.entries(events))map.addEventListener(name,handler);
  return {
    canvas,
    destroy(){for(const [name,handler] of Object.entries(events))map.removeEventListener(name,handler);cache.clear();app.destroy(true,{children:true});},
    paint(camera){
      if(!map.clientWidth||!map.clientHeight)return;
      if(gl.isContextLost())throw new Error('WebGL context lost');
      if(app.screen.width!==map.clientWidth||app.screen.height!==map.clientHeight)app.renderer.resize(map.clientWidth,map.clientHeight);
      scale=camera.k;scene.position.set(camera.x,camera.y);scene.scale.set(scale);used=new Set();order=0;
      function visit(element){
        if(element.tagName==='text')sourceText(element);
        else if(element.tagName==='rect'||element.tagName==='path')shape(element);
        else if(element.tagName==='g')for(const child of element.children)visit(child);
      }
      for(const child of world.children)visit(child);
      for(const [key,record] of cache)if(!used.has(key)){record.node.destroy();cache.delete(key);}
      render();
    },
    info(){return {engine:'pixi',version:PIXI.VERSION,renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
      objects:cache.size,text_objects:[...cache.values()].filter(record=>record.node instanceof PIXI.Text).length,gl_error:gl.getError()};}
  };
};
