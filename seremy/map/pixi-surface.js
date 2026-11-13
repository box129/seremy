// Pixi consumes neutral scene records. SVG remains the semantic/input adapter.
window.createSeremyPixiSurface=async function(map,world,recordFor){
  const app=new PIXI.Application();
  await app.init({width:map.clientWidth,height:map.clientHeight,preference:'webgl',autoStart:false,
    resolution:devicePixelRatio,autoDensity:true,antialias:true,backgroundAlpha:0});
  const canvas=app.canvas;
  canvas.hidden=true;
  canvas.id='pixi-surface';canvas.setAttribute('aria-hidden','true');
  map.parentElement.insertBefore(canvas,map);
  const scene=new PIXI.Container(),highlight=new PIXI.Graphics();app.stage.addChild(scene);scene.addChild(highlight);
  const cache=new Map(),widths=new Map(),ascents=new Map(),styles=new Map();
  const counters={created:0,destroyed:0,text_updates:0,graphics_updates:0};
  let used=new Set(),usedStyles=new Set(),orders=new Map(),parent=scene,scale=1,hover=null,focused=null;
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
    if(!record){record={node:create(),signature:null};counters.created++;cache.set(key,record);parent.addChild(record.node);}
    if(record.node.parent!==parent)parent.addChild(record.node);
    const order=orders.get(parent)||0;if(parent.children[order]!==record.node)parent.setChildIndex(record.node,order);orders.set(parent,order+1);
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
  const has=(element,name)=>(element.attrs.class||'').split(' ').includes(name);
  function shape(element){
    if(has(element,'hit')||has(element,'token'))return;
    const base=Object.entries(palette).find(([name])=>has(element,name))?.[1]||{};
    const fill=color(base.fill||element.attrs['fill']);
    const stroke=color(has(element,'selected')?'#d3ad65':base.stroke||element.attrs['stroke']);
    const width=(has(element,'selected')?4:base.width||1)/(element.attrs['vector-effect']==='non-scaling-stroke'?scale:1);
    const signature=JSON.stringify([element.attrs['x'],element.attrs['y'],element.attrs['width'],element.attrs['height'],element.attrs['rx'],element.attrs['d'],fill,stroke,width,base.dash,has(element,'faded'),!!element.attrs['marker-end']]);
    const record=object(element.id,()=>new PIXI.Graphics());
    if(record.signature===signature)return;
    record.signature=signature;counters.graphics_updates++;const graphics=record.node;graphics.clear();
    let end=null;
    if(element.tag==='rect'){
      const [x,y,w,h]=['x','y','width','height'].map(key=>Number(element.attrs[key]));
      graphics.roundRect(x,y,w,h,Number(element.attrs['rx']||0));
      if(fill)graphics.fill(fill);
      if(base.dash){if(!fill)graphics.clear();else graphics.beginPath();dashedRect(graphics,x,y,w,h,8/scale);}
    }else end=path(graphics,element.attrs['d']||'');
    if(element.tag!=='rect'&&fill)graphics.fill(fill);
    if(stroke)graphics.stroke({...stroke,width});
    graphics.alpha=has(element,'faded')?0.2:1;
    if(end&&!!element.attrs['marker-end']){
      const angle=Math.atan2(end.tangent.y,end.tangent.x),length=width*7,side=width*3.5;
      const bx=end.x-Math.cos(angle)*length,by=end.y-Math.sin(angle)*length;
      graphics.moveTo(end.x,end.y).lineTo(bx-Math.sin(angle)*side,by+Math.cos(angle)*side)
        .lineTo(bx+Math.sin(angle)*side,by-Math.cos(angle)*side).closePath().fill(0x91a0b5);
    }
  }
  function sourceText(element){
    const named=has(element,'name'),baseSize=named?17:14;
    const size=Number.parseFloat(element.style.fontSize)||baseSize,factor=size/baseSize;
    const family=named?['Segoe UI','system-ui']:['Consolas','monospace'],weight=named?'600':'400';
    const resolution=Math.max(2,2**Math.ceil(Math.log2(Math.max(1,scale*devicePixelRatio))));
    let x=Number(element.attrs.x),y=Number(element.attrs.y),top=y,bottom=y;
    const left=x;
    function visit(node,currentColor){
      if(node.text){
        const value=node.text,stroke=element.style.stroke;
        // Quantize inverse-camera stroke arithmetic so unchanged screen styles reuse textures.
        const strokeWidth=stroke?Number(((Number.parseFloat(element.style.strokeWidth)||0)/factor).toFixed(3)):0;
        const styleKey=JSON.stringify([named,currentColor,stroke,strokeWidth]);
        if(!styles.has(styleKey))styles.set(styleKey,new PIXI.TextStyle({fontFamily:family,fontSize:baseSize,fontWeight:weight,fill:currentColor,...stroke?{stroke:{color:stroke,width:strokeWidth}}:{}}));
        usedStyles.add(styleKey);
        const style=styles.get(styleKey),signature=JSON.stringify([value,styleKey,resolution]);
        const record=object(node.id+':text',()=>new PIXI.Text({text:value,style,resolution}));
        if(record.signature!==signature){record.signature=signature;record.node.text=value;record.node.style=style;record.node.resolution=resolution;counters.text_updates++;}
        const fontKey=named?'name':'code';
        if(!ascents.has(fontKey))ascents.set(fontKey,PIXI.CanvasTextMetrics.measureText('M',style).fontProperties);
        const metrics=ascents.get(fontKey),ascent=metrics.ascent*factor;
        record.node.anchor.set((node===element&&element.attrs['text-anchor']==='middle')?0.5:0,0);
        record.node.scale.set(factor);record.node.position.set(x,y-ascent);
        const widthKey=fontKey+'|'+value;
        if(!widths.has(widthKey)){
          if(widths.size>=8192)widths.delete(widths.keys().next().value);
          widths.set(widthKey,PIXI.CanvasTextMetrics.measureText(value,style).width);
        }
        x+=widths.get(widthKey)*factor;top=Math.min(top,y-ascent);bottom=Math.max(bottom,y+metrics.descent*factor);
      }
      for(const child of node.children){
        if(child.tag==='title')continue;
        if(child.attrs.x!==undefined)x=Number(child.attrs.x);if(child.attrs.y!==undefined)y=Number(child.attrs.y);
        const next=Object.keys(colors).find(name=>has(child,name));visit(child,next?colors[next]:currentColor);
      }
    }
    visit(element,named?colors.name:colors.code);
    element.bounds={x:left-(element.attrs['text-anchor']==='middle'?(x-left)/2:0),y:top,width:x-left,height:bottom-top};
  }
  function outline(){
    highlight.clear();const element=focused||hover;
    if(!element?.isConnected||!world.contains(element))return;
    const record=recordFor(element);let box=record.tag==='rect'?record.attrs:record.bounds;
    if(!box)return;
    if(record.clip){const c=record.clip,x=Math.max(box.x,c.x),y=Math.max(box.y,c.y);box={x,y,width:Math.max(0,Math.min(box.x+box.width,c.x+c.width)-x),height:Math.max(0,Math.min(box.y+box.height,c.y+c.height)-y)};}
    highlight.rect(box.x-1,box.y-1,box.width+2,box.height+2).stroke({color:0x9cb9e5,width:1.5/scale});
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
  function dispose(record){if(record.node instanceof PIXI.Container)record.node.mask=null;record.node.destroy();counters.destroyed++;}
  function release(){
    for(const record of cache.values())dispose(record);
    cache.clear();for(const style of styles.values())style.destroy();styles.clear();widths.clear();
    PIXI.TexturePool.clear();
  }
  return {
    canvas,
    release,
    destroy(){for(const [name,handler] of Object.entries(events))map.removeEventListener(name,handler);release();app.destroy(true,{children:true});},
    paint(camera,model){
      if(!map.clientWidth||!map.clientHeight)return;
      if(gl.isContextLost())throw new Error('WebGL context lost');
      if(app.screen.width!==map.clientWidth||app.screen.height!==map.clientHeight)app.renderer.resize(map.clientWidth,map.clientHeight);
      scale=camera.k;scene.position.set(camera.x,camera.y);scene.scale.set(scale);used=new Set();usedStyles=new Set();orders=new Map();parent=scene;
      function visit(element,clip=null){
        element.clip=clip;
        if(element.tag==='text')sourceText(element);
        else if(element.tag==='rect'||element.tag==='path'){
          if(clip&&has(element,'source-focus')){
            const a=element.attrs,x=Math.max(a.x,clip.x),y=Math.max(a.y,clip.y),right=Math.min(a.x+a.width,clip.x+clip.width),bottom=Math.min(a.y+a.height,clip.y+clip.height);
            if(right>x&&bottom>y)shape({...element,attrs:{...a,x,y,width:right-x,height:bottom-y}});
          }else shape(element);
        }else if(element.tag==='g'){
          const a=element.attrs,nextClip=a['data-clip-x']===undefined?clip:{x:a['data-clip-x'],y:a['data-clip-y'],width:a['data-clip-width'],height:a['data-clip-height']};
          if(nextClip&&a['data-layer']==='source'&&a['data-clip-enabled']){
            const group=object(element.id+':group',()=>new PIXI.Container()),previous=parent;parent=group.node;
            const mask=object(element.id+':mask',()=>new PIXI.Graphics()),signature=JSON.stringify(nextClip);
            if(mask.signature!==signature){mask.signature=signature;mask.node.clear().rect(nextClip.x,nextClip.y,nextClip.width,nextClip.height).fill(0xffffff);}
            if(group.node.mask!==mask.node)group.node.mask=mask.node;
            for(const child of element.children)visit(child,nextClip);parent=previous;
          }else for(const child of element.children)visit(child,nextClip);
        }
      }
      for(const child of model.children)visit(child);
      let evicted=0;
      for(const [key,record] of cache)if(!used.has(key)){dispose(record);cache.delete(key);evicted++;}
      for(const [key,style] of styles)if(!usedStyles.has(key)){style.destroy();styles.delete(key);}
      render();
      // Only idle pooled textures are cleared; live/shared text textures retain their references.
      if(evicted||!cache.size)PIXI.TexturePool.clear();
    },
    info(){return {engine:'pixi',version:PIXI.VERSION,renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),
      ...counters,style_objects:styles.size,width_cache:widths.size,objects:cache.size,text_objects:[...cache.values()].filter(record=>record.node instanceof PIXI.Text).length,gl_error:gl.getError()};}
  };
};
