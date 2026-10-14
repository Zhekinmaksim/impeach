/** Impeach — a 60-second, deterministic motion film. No network/API calls. */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { once } from 'node:events';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = process.env.MOTION_NODE_MODULES || '/Users/zmaxx/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const require = createRequire(path.join(modules, 'package.json'));
const { createCanvas, loadImage, GlobalFonts } = require('@napi-rs/canvas');
const OUT = path.join(ROOT, 'output/video');
fs.mkdirSync(OUT, { recursive: true });
const W = 1920, H = 1080, FPS = 30, DURATION = 60;
for (const [file, name] of [
  ['barlow-condensed-latin-600-normal.woff2', 'Head'],
  ['barlow-condensed-latin-400-normal.woff2', 'Book'],
  ['stix-two-text-latin-400-normal.woff2', 'Serif'],
  ['stix-two-text-latin-400-italic.woff2', 'Italic'],
  ['ibm-plex-mono-latin-400-normal.woff2', 'Mono'],
]) {
  if (!GlobalFonts.registerFromPath(path.join(ROOT, 'web/assets/fonts', file), name)) throw new Error('Font missing: ' + file);
}
const logos = await Promise.all(['logo.svg','logo-dark.svg'].map(n => loadImage(path.join(ROOT,'web/assets',n))));
GlobalFonts.registerFromPath('/System/Library/Fonts/Supplemental/Georgia.ttf', 'Symbols');
const C = { paper:'#eef3ec', sheet:'#f9fbf7', green:'#1e6a4b', pale:'#c9dccf', ink:'#26292b', muted:'#5a6061', red:'#b3202e', redlight:'#f3dcdc', white:'#eef3ec', hot:'#ef6370' };
const canvas=createCanvas(W,H), ctx=canvas.getContext('2d');
const cut=[0,6,12,19,27,34,41,48,55,60];
const chapter=['THE QUESTION','IMPEACH','THE CLAIM','THE REWRITE','THE DETECTORS','THE VALIDATORS','THE REGISTRY','THE EVIDENCE','THE INVITATION'];
const clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const lerp=(a,b,p)=>a+(b-a)*p;
const ease=x=>1-Math.pow(1-clamp(x),3);
const io=x=>{x=clamp(x);return x<.5?4*x*x*x:1-Math.pow(-2*x+2,3)/2;};
const enter=(t,delay=0,d=.7)=>ease((t-delay)/d);
const spring=x=>{x=clamp(x);return x===0||x===1?x:1-Math.exp(-7*x)*Math.cos(12*x);};
let audit=[];
function rect(x,y,w,h,fill,stroke=null,r=0,lw=2){ctx.beginPath();ctx.roundRect(x,y,w,h,r);if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=lw;ctx.stroke();}}
function line(x1,y1,x2,y2,color=C.green,lw=2,progress=1){ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(lerp(x1,x2,progress),lerp(y1,y2,progress));ctx.strokeStyle=color;ctx.lineWidth=lw;ctx.lineCap='round';ctx.stroke();}
function text(s,x,y,size=40,color=C.ink,font='Head',align='left',max=null){ctx.font=`${size}px "${font}", "Symbols"`;ctx.textAlign=align;ctx.textBaseline='top';ctx.fillStyle=color;const width=ctx.measureText(s).width;if(max&&width>max+1)audit.push({text:s,width,max});ctx.fillText(s,x,y);}
function reveal(s,x,y,size,color,font,t,delay=0,align='left',max=null){const p=enter(t,delay);ctx.save();ctx.globalAlpha=p;ctx.translate(0,36*(1-p));text(s,x,y,size,color,font,align,max);ctx.restore();}
function group(t,delay,fn,dy=65){const p=enter(t,delay);ctx.save();ctx.globalAlpha=p;ctx.translate(0,dy*(1-p));fn(p);ctx.restore();}
function pill(x,y,w,h,color,p=1){ctx.save();ctx.translate(x+w/2,y+h/2);ctx.scale(clamp(p),clamp(p));rect(-w/2,-h/2,w,h,color,null,h/2);ctx.restore();}
function logo(x,y,w,dark=false){ctx.drawImage(logos[dark?1:0],x,y,w,w*1068/4204);}
function check(x,y,p,color=C.green){line(x,y+10,x+10,y+20,color,5,clamp(p*2));if(p>.5)line(x+10,y+20,x+31,y-4,color,5,(p-.5)*2);}
function arrow(x1,y1,x2,y2,p,color=C.green){line(x1,y1,x2,y2,color,3,p);if(p>.94){const a=Math.atan2(y2-y1,x2-x1);line(x2,y2,x2-17*Math.cos(a-.45),y2-17*Math.sin(a-.45),color,3);line(x2,y2,x2-17*Math.cos(a+.45),y2-17*Math.sin(a+.45),color,3);}}
function stamp(label,x,y,w,t,color=C.red,bounded=false){const p=bounded?enter(t,0,.65):spring(t/.65);ctx.save();ctx.translate(x+w/2,y+60);ctx.rotate(-.045);ctx.scale(p,p);rect(-w/2,-56,w,112,null,color,1,5);text(label,0,-40,76,color,'Head','center',w-20);ctx.restore();}
function rail(t,idx,dark=false){const ink=dark?C.pale:C.green;line(100,92,1820,92,ink,1);text('IMPEACH / GENLAYER',100,47,25,ink,'Mono');text(chapter[idx],1820,47,25,ink,'Mono','right');line(100,990,1820,990,ink,1);const seg=1720/9;for(let i=0;i<9;i++){const p=clamp((t-cut[i])/(cut[i+1]-cut[i]));line(100+i*seg,990,100+(i+p)*seg,990,dark?C.white:C.green,5);}text('A COURT FOR BENCHMARK SCORES',100,1010,20,ink,'Mono');text(String(idx+1).padStart(2,'0')+' / 09',1820,1010,20,ink,'Mono','right');}
const texture=createCanvas(W,H);{
 const q=texture.getContext('2d');let seed=82473;
 for(let i=0;i<30000;i++){seed=(seed*1664525+1013904223)>>>0;const x=seed%W;seed=(seed*1664525+1013904223)>>>0;const y=seed%H;q.fillStyle=i%2?'rgba(30,55,36,.028)':'rgba(255,255,255,.1)';q.fillRect(x,y,1,1);}
}
function background(dark=false){ctx.fillStyle=dark?C.ink:C.paper;ctx.fillRect(0,0,W,H);if(!dark)ctx.drawImage(texture,0,0);}

function scene0(t){
 reveal('A PERFECT SCORE.',106,170,51,C.green,'Head',t,.1);
 const n=Math.round(100*enter(t,.25,1.8));
 text(String(n),85,257,405,C.ink,'Head');text('%',643,403,176,C.green,'Head');
 reveal('KNOWLEDGE',960,242,139,C.green,'Head',t,.5,'left',850);
 reveal('OR MEMORY?',960,388,139,C.green,'Head',t,.8,'left',850);
 reveal('A benchmark can reward',968,597,48,C.ink,'Serif',t,1.2);
 reveal('answers seen before.',968,659,48,C.ink,'Serif',t,1.45);
 for(let i=0;i<24;i++){const p=enter(t,.4+i*.055,.6);const red=clamp((t-3.1-i*.045)/.4);pill(110+i*71,829,58,37,red>.5?C.red:C.ink,p);}
 reveal('HIGH ACCURACY IS ONLY THE BEGINNING.',110,902,26,C.muted,'Mono',t,2.1);
}
function scene1(t){
 const p=enter(t,.1,1.1);ctx.save();ctx.translate(960,440);ctx.scale(.92+.08*p,.92+.08*p);ctx.globalAlpha=p;logo(-765,-220,1530,true);ctx.restore();
 reveal('A court for benchmark scores.',960,632,77,C.white,'Serif',t,.7,'center',1670);
 reveal('CHALLENGE THE CLAIM. RECORD THE EVIDENCE.',960,790,30,C.pale,'Mono',t,1.3,'center');
 for(let i=0;i<3;i++)line(680+i*200,892,804+i*200,892,i===1?C.hot:C.pale,10,enter(t,1.6+i*.2));
}
function scene2(t){
 reveal('PUT THE SCORE ON TRIAL.',108,170,123,C.green,'Head',t,0,'left',1700);
 reveal('The terms are fixed before the questions are revealed.',112,324,45,C.ink,'Serif',t,.3,'left',1670);
 const xs=[110,700,1290],titles=['SCORE + BOND','SEALED ITEMS','CHALLENGE'];
 const labels=[['A claim with','something at stake.'],['Commit the hashes.','Keep the items sealed.'],['A challenger opens','the cross-examination.']];
 for(let i=0;i<3;i++)group(t,.5+i*.28,()=>{
  const x=xs[i];rect(x+9,457,516,416,C.pale);rect(x,445,516,416,C.sheet,C.green);
  text('0'+(i+1),x+30,475,28,C.green,'Mono');text(titles[i],x+30,533,61,C.green,'Head','left',460);
  if(i===0){text('100%',x+30,613,103,C.ink,'Head');rect(x+300,637,145,51,C.green,null,26);text('BONDED',x+372,646,29,C.white,'Head','center');}
  if(i===1){for(let r=0;r<3;r++){text(['a2f6 · 91bc','d870 · 2e1a','56ad · 09c4'][r],x+33,620+r*34,25,C.muted,'Mono');}rect(x+355,650,56,46,C.green,null,5);ctx.beginPath();ctx.arc(x+383,649,19,Math.PI,0);ctx.strokeStyle=C.green;ctx.lineWidth=6;ctx.stroke();}
  if(i===2){line(x+44,672,x+134,672,C.red,12);line(x+89,627,x+89,717,C.red,12);text('OPEN',x+195,627,83,C.red,'Head');}
  text(labels[i][0],x+30,744,34,C.ink,'Serif');text(labels[i][1],x+30,786,34,C.ink,'Serif');
 });
 for(let i=0;i<2;i++)arrow(xs[i]+535,653,xs[i+1]-15,653,enter(t,1.7+i*.35));
}
function scene3(t){
 reveal('NEW WORDING. SAME ANSWER.',108,161,123,C.green,'Head',t,0,'left',1710);
 reveal('A rewrite counts only when both referee framings admit it.',112,312,42,C.ink,'Serif',t,.3,'left',1700);
 const x=[110,1000];
 for(let i=0;i<2;i++)group(t,.5+i*.3,()=>{
  rect(x[i],419,810,348,C.sheet,C.green);
  text(i?'THE REWRITE':'THE ORIGINAL',x[i]+34,450,31,C.green,'Mono');
  const lines=i?['Each box holds 4 pens.','There are 6 boxes. How many pens?']:['6 boxes contain 4 pens each.','How many pens are there in total?'];
  text(lines[0],x[i]+34,516,42,C.ink,'Serif','left',748);text(lines[1],x[i]+34,574,42,C.ink,'Serif','left',748);
  line(x[i]+34,645,x[i]+776,645,C.pale,2);text('ANSWER:',x[i]+34,674,31,C.muted,'Mono');reveal('24',x[i]+776,662,72,C.green,'Head',t,1.7+i*.25,'right');
 });
 arrow(937,595,983,595,enter(t,1.3));
 for(let i=0;i<2;i++)group(t,2.35+i*.42,()=>{const px=1000+i*409;rect(px,796,401,74,C.pale);check(px+20,823,enter(t,2.5+i*.42));text('REFEREE '+(i+1)+' / ADMIT',px+66,817,26,C.green,'Mono');});
 reveal('ILLUSTRATIVE QUESTION',110,823,24,C.muted,'Mono',t,1.6);
}
function scene4(t){
 rect(960,120,960,847,C.ink);
 reveal('TWO TESTS.',110,160,111,C.green,'Head',t,0);reveal('ONE RECORD.',1040,160,111,C.white,'Head',t,.2);
 reveal('Δ',122,325,260,C.green,'Serif',t,.35);reveal('R',1040,328,265,C.hot,'Head',t,.55);
 reveal('THE ACCURACY GAP',110,626,57,C.green,'Head',t,.8);reveal('VERBATIM RECALL',1040,626,57,C.white,'Head',t,1.0);
 reveal('Original score minus rewrite score.',110,710,37,C.ink,'Serif',t,1.2,'left',780);
 reveal('Can it continue a sealed question?',1040,710,37,C.white,'Serif',t,1.4,'left',780);
 for(let j=0;j<2;j++){text(j?'REWRITE':'ORIGINAL',390,365+j*95,24,C.muted,'Mono');for(let i=0;i<6;i++)pill(390+i*72,405+j*95,58,28,j?C.green:C.ink,enter(t,1.4+j*.3+i*.08));}
 text('PROMPT',1300,367,23,C.pale,'Mono');text('CONTINUATION',1500,367,23,C.pale,'Mono');
 for(let j=0;j<3;j++)for(let i=0;i<10;i++){const p=enter(t,.9+(j*10+i)*.045);rect(1300+i*48,422+j*43,34,12,i<4?C.pale:(p>.95?C.hot:'#45484a'),null,6);}
 line(1300,583,1490,583,C.pale,3,enter(t,2.2));line(1499,583,1766,583,C.hot,3,enter(t,2.4));
 reveal('40%',1395,541,26,C.pale,'Mono',t,2.2,'center');reveal('HELD OUT',1630,541,26,C.hot,'Mono',t,2.4,'center');
 reveal('TWO SIGNALS. FROZEN THRESHOLDS.',110,879,29,C.green,'Mono',t,2.5);
}
function scene5(t){
 reveal('VALIDATORS DECIDE.',110,168,119,C.green,'Head',t,0);
 reveal('Each calls the model. Consensus records the ruling.',113,321,43,C.ink,'Serif',t,.35);
 const cx=1015,cy=669;
 const nodes=[[585,536],[655,815],[1385,505],[1470,804]];
 for(let i=0;i<nodes.length;i++){
  const [x,y]=nodes[i];const p=enter(t,.6+i*.18);
  line(x,y,cx,cy,C.pale,3,p);const travel=((t*.47+i*.21)%1);if(t>1.3){pill(lerp(x,cx,travel)-7,lerp(y,cy,travel)-7,14,14,C.green);}
  group(t,.6+i*.18,()=>{rect(x-80,y-46,160,92,C.sheet,C.green,46);text('V'+(i+1),x,y-25,46,C.green,'Head','center');},0);
 }
 group(t,.4,()=>{rect(cx-235,445,470,430,C.sheet,C.green);text('PUBLIC CERTIFICATE',cx,480,29,C.green,'Mono','center');line(cx-198,533,cx+198,533,C.pale,2);text('VERDICT',cx,562,94,C.green,'Head','center');text('Δ  /  R  /  COUNTS',cx,691,27,C.muted,'Mono','center');stamp('ON-CHAIN',cx-170,735,340,t-2.1,C.green,true);});
 reveal('FROZEN',111,545,50,C.green,'Head',t,1);reveal('TERMS',111,603,50,C.green,'Head',t,1.13);
 reveal('CHECKABLE',1580,547,46,C.green,'Head',t,1.5,'left',244);reveal('EVIDENCE',1580,606,46,C.green,'Head',t,1.63);
}
function scene6(t){
 reveal('REVEALED ONCE. SPENT FOREVER.',109,161,112,C.green,'Head',t,0,'left',1706);
 reveal('Revealing the set burns every item into a public registry.',111,306,42,C.ink,'Serif',t,.3);
 let spent=0;
 for(let i=0;i<24;i++){
  const x=113+(i%6)*285,y=425+Math.floor(i/6)*99;
  const p=enter(t,.5+i*.025);const b=enter(t,1.55+i*.065,.45);if(b>.5)spent++;
  group(t,.5+i*.025,()=>{rect(x,y,267,78,b>.5?C.redlight:C.sheet,b>.5?C.red:C.green,39);text(b>.5?'SPENT':`ITEM ${String(i+1).padStart(2,'0')}`,x+133,y+22,29,b>.5?C.red:C.green,'Mono','center');if(b>0)line(x+34,y+39,x+233,y+39,C.red,2,b);},22);
 }
 reveal('is_spent(hash)',110,881,36,C.green,'Mono',t,2.4);
 text(String(spent).padStart(2,'0')+' / 24 ITEMS',1815,862,66,C.red,'Head','right');
}
function scene7(t){
 reveal('ON-CHAIN. ON RECORD.',111,157,123,C.white,'Head',t,0);
 reveal('Finalized results on GenLayer Bradbury.',114,308,45,C.pale,'Serif',t,.3);
 group(t,.5,()=>{
  rect(110,419,819,439,C.sheet);text('SCRIPTED MEMORISER',145,451,30,C.muted,'Mono');
  stamp('CONTAMINATED',145,519,742,t-1.1,C.red);
  text('24/24',145,676,92,C.red,'Head');text('recall matches',382,703,42,C.ink,'Serif');
  text('13 admitted rewrite pairs',145,790,29,C.muted,'Mono');
 });
 group(t,.8,()=>{
  rect(971,419,839,439,C.sheet);text('LLAMA 3.1 8B',1006,451,30,C.muted,'Mono');
  stamp('CLEAN',1006,519,769,t-1.5,C.green);
  text('23/24',1006,676,92,C.green,'Head');text('pairs admitted',1243,703,42,C.ink,'Serif');
  text('Partial trial / Δ = 0 / R = 0',1006,790,29,C.muted,'Mono');
 });
 reveal('DISCLOSED SYNTHETIC CORPUS. CLEAN APPLIES ONLY TO THIS TRIAL.',960,906,25,C.pale,'Mono',t,2.0,'center',1740);
}
function scene8(t){
 group(t,.04,()=>logo(406,215,1110),30);
 reveal('Make benchmark claims accountable.',960,571,69,C.green,'Serif',t,.45,'center',1700);
 group(t,.9,()=>{rect(534,724,852,101,C.green,null,51);text('impeach.click',960,749,47,C.white,'Mono','center');});
 reveal('BUILT ON GENLAYER',960,893,28,C.green,'Mono',t,1.2,'center');
}
const scenes=[scene0,scene1,scene2,scene3,scene4,scene5,scene6,scene7,scene8];
function draw(t){
 const idx=Math.min(8,cut.findIndex((x,i)=>i<9&&t>=x&&t<cut[i+1]));const i=idx<0?8:idx;
 const local=t-cut[i];const dark=i===1||i===7;
 ctx.resetTransform();ctx.globalAlpha=1;background(dark);
 ctx.save();const camera=1+.004*Math.sin(local/(cut[i+1]-cut[i])*Math.PI);ctx.translate(960,540);ctx.scale(camera,camera);ctx.translate(-960,-540);scenes[i](local);ctx.restore();rail(t,i,dark);
 // A physical wipe at each cut, with the two bars from the brand mark.
 if(i>0&&local<.45){const p=io(local/.45);rect(p*W,0,W*(1-p),H,dark?C.paper:C.ink);rect(p*W-13,0,13,H,C.red);}
 if(t<.45){ctx.globalAlpha=1-ease(t/.45);rect(0,0,W,H,C.paper);ctx.globalAlpha=1;}
 if(t>59){ctx.globalAlpha=io(t-59);rect(0,0,W,H,C.paper);ctx.globalAlpha=1;}
}
const manifest={title:'Impeach — A court for benchmark scores',duration_seconds:DURATION,width:W,height:H,fps:FPS,language:'en',music:{title:'Onchain Verdict',source:'/Users/zmaxx/Music/Onchain Verdict.mp3',source_start_seconds:12,source_duration_seconds:60},scenes:cut.slice(0,-1).map((s,i)=>({start:s,end:cut[i+1],chapter:chapter[i]})),evidence:['web/case.json','runs/v2-live-case.json'],scope:'Scripted control: 24 recall matches, 13 admitted pairs. Real Llama: finalized CLEAN on 23/24 admitted pairs. No claim of a completed full-24 trial.'};
fs.writeFileSync(path.join(OUT,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
if(process.argv.includes('--preview')){
 const times=[3.8,9.4,16.5,23.6,31.1,38.4,45.5,52.7,57.8];
 const contact=createCanvas(1440,810),q=contact.getContext('2d');
 for(let i=0;i<times.length;i++){draw(times[i]);const f=path.join(OUT,`scene-${i+1}.png`);const bytes=await canvas.encode('png');fs.writeFileSync(f,bytes);q.drawImage(await loadImage(bytes),(i%3)*480,Math.floor(i/3)*270,480,270);}
 fs.writeFileSync(path.join(OUT,'storyboard.jpg'),await contact.encode('jpeg',92));
 fs.writeFileSync(path.join(OUT,'layout-check.json'),JSON.stringify({overflows:audit},null,2)+'\n');
 console.log(JSON.stringify({preview:true,overflows:audit}));
}else{
 const output=path.join(OUT,'impeach-presentation-60s.mp4');
 const args=['-y','-hide_banner','-loglevel','warning','-f','rawvideo','-pixel_format','rgba','-video_size',`${W}x${H}`,'-framerate',String(FPS),'-i','pipe:0','-ss','12','-i',manifest.music.source,'-map','0:v:0','-map','1:a:0','-t','60','-c:v','libx264','-preset','fast','-crf','18','-threads','4','-pix_fmt','yuv420p','-r','30','-c:a','aac','-b:a','192k','-af','atrim=duration=60,asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=1.2,afade=t=out:st=56.5:d=3.5','-ar','48000','-ac','2','-movflags','+faststart','-metadata','title=Impeach — A court for benchmark scores','-metadata','comment=Music: Onchain Verdict by zhekinmaksim; source provided by project owner. Finalized evidence only.',output];
 const ff=spawn('ffmpeg',args,{stdio:['pipe','ignore','inherit']});
 const done=once(ff,'close');ff.stdin.on('error',()=>{});
 for(let f=0;f<FPS*DURATION;f++){
  draw(f/FPS);if(!ff.stdin.write(Buffer.from(canvas.data())))await once(ff.stdin,'drain');
  if(f%(FPS*5)===0)console.log(`Rendered ${f/FPS}s / ${DURATION}s`);
 }
 ff.stdin.end();const [code]=await done;if(code!==0)throw new Error('ffmpeg exit '+code);
 fs.writeFileSync(path.join(OUT,'layout-check.json'),JSON.stringify({overflows:[...new Map(audit.map(x=>[x.text,x])).values()]},null,2)+'\n');
 console.log(JSON.stringify({output,seconds:60,frames:1800}));
}
