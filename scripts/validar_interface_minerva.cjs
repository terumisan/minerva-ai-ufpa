// Validação de navegador com perguntas sintéticas; requer Playwright.
const {chromium} = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
const mode = process.argv[2] || 'final';
const dir = process.env.MINERVA_UI_ARTIFACT_DIR || `/tmp/minerva-browser/${mode}`;
fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.MINERVA_CHROMIUM_EXECUTABLE || undefined});
 const context=await browser.newContext({viewport:{width:1280,height:1000},acceptDownloads:true});
 const page=await context.newPage();
 const errors=[]; page.on('pageerror',e=>errors.push(e.stack||e.message));
 const results=[];
 const save=()=>fs.writeFileSync(`${dir}/resultados.json`,JSON.stringify({mode,results,errors},null,2));
 async function record(name,data){results.push({name,...data});save();console.log(JSON.stringify({name,seconds:data.seconds,preserved:data.preserved,spinner:data.spinner,elapsed:data.elapsed,passed:data.passed}));}
 async function ask(question,related=false){
  await page.waitForTimeout(3300);
  const count=await page.locator('[data-testid="stChatMessage"]').count();
  const start=Date.now();
  if(related){
   const last=page.locator('[data-testid="stChatMessage"]').last();
   await last.getByText('Perguntas relacionadas',{exact:true}).click();
   await last.getByRole('button',{name:question,exact:true}).click();
  }else{
   await page.getByPlaceholder('Faça sua pergunta').fill(question);
   await page.getByPlaceholder('Faça sua pergunta').press('Enter');
  }
  let spinner=false;let elapsed=false;
  await page.waitForFunction(n=>document.querySelectorAll('[data-testid="stChatMessage"]').length>=n+2,count,{timeout:240000});
  while(Date.now()-start<240000){
   if(await page.locator('[data-testid="stSpinner"]').count()){
    if(!spinner)await page.screenshot({path:`${dir}/espera.png`});
    spinner=true; elapsed ||= /\d/.test(await page.locator('[data-testid="stSpinner"]').innerText());
   }
   const last=page.locator('[data-testid="stChatMessage"]').last();
   if(await last.getByRole('button',{name:'🤍',exact:true}).count()){
    const text=await last.innerText();
    await record(question,{seconds:(Date.now()-start)/1000,spinner,elapsed,text,links:await last.locator('a').evaluateAll(nodes=>nodes.map(n=>({text:n.textContent,url:n.href}))),expanders:await last.locator('summary').allTextContents(),related:await last.getByRole('button').allTextContents()});
    return text;
   }
   await page.waitForTimeout(500);
  }
  throw Error('Resposta não concluiu');
 }
 try{
  await page.goto(process.env.MINERVA_UI_URL || 'http://127.0.0.1:8501');
  await page.getByPlaceholder('Faça sua pergunta').waitFor({timeout:60000});
  await record('inicial',{text:await page.locator('body').innerText()});
  await ask('Passei em TCC I: o que preciso entregar para me matricular no TCC II?');
  await page.locator('[data-testid="stChatMessage"]').first().scrollIntoViewIfNeeded();
  await page.screenshot({path:`${dir}/resposta.png`,fullPage:true});
  if(mode==='final'){
   const answer=page.locator('[data-testid="stChatMessage"]').last();
   assert.equal(await answer.getByRole('link',{name:'Abrir fonte oficial',exact:true}).count(),2);
   const href=await answer.getByRole('link',{name:'Abrir fonte oficial',exact:true}).first().getAttribute('href');
   assert.match(href,/^https:\/\/www\.fct\.ufpa\.br\/.*\.pdf#page=2$/);
   const details=answer.locator('summary').filter({hasText:'Detalhes da fonte'}).first();
   await details.click();
   assert.match(await answer.innerText(),/[a-f0-9]{64}/);
   await details.click();
   await record('fontes',{passed:true,href});
   const collapse=page.locator('[data-testid="stSidebarCollapseButton"] button');
   if(await collapse.isVisible())await collapse.click();
   await page.setViewportSize({width:390,height:844});
   await page.waitForTimeout(500);
   const actions=page.locator('[class*="st-key-acoes_resposta_"]').last();
   const positions=await Promise.all(['🤍','🖤','🔄'].map(name=>actions.getByRole('button',{name,exact:true}).boundingBox()));
   assert.ok(positions.every(p=>p && Math.abs(p.y-positions[0].y)<3));
   await actions.scrollIntoViewIfNeeded();
   await page.screenshot({path:`${dir}/mobile_resposta.png`,fullPage:true});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
   assert.equal(overflow,false);await record('mobile_resposta',{passed:true,horizontalOverflow:overflow,actionsInOneRow:true});
   await page.setViewportSize({width:1280,height:1000});
  }
  await ask('Qual anexo apresentar em TCC II quando há mudança de orientador ou tema ou intervalo entre semestres na Resolução FCT 01/2012?',mode==='final');
  if(mode==='final'){
   const answer=await page.locator('[data-testid="stChatMessage"]').last().innerText();
   assert.match(answer,/Anexo I/);await record('relacionada',{passed:true});
  }
  await ask('Qual é o código secreto da sala subterrânea de Marte?');
  if(mode==='final'){
   assert.match(await page.locator('[data-testid="stChatMessage"]').last().innerText(),/Tente informar o curso/);
   await page.screenshot({path:`${dir}/abstencao.png`,fullPage:true});
  }
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Exportar histórico',exact:true}).click();
  const download=await downloadPromise;await download.saveAs(`${dir}/historico.txt`);
  const originalExport=fs.readFileSync(`${dir}/historico.txt`,'utf8');
  assert.equal((originalExport.match(/USUÁRIO:/g)||[]).length,3);
  const oldUrl=page.url();
  await page.getByRole('button',{name:'＋ Nova conversa',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-testid="stChatMessage"]').length===0);
  const title=page.getByRole('button',{name:/Passei em TCC I: o que preciso/});
  if(!await title.isVisible()){
   await page.locator('[data-testid="stExpandSidebarButton"] button').click();
  }
  await title.click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-testid="stChatMessage"]').length===6);
  await page.waitForTimeout(1000);
  const restoreDownload=page.waitForEvent('download');
  await page.getByRole('button',{name:'Exportar histórico',exact:true}).click();
  await (await restoreDownload).saveAs(`${dir}/historico_restaurado.txt`);
  const preserved=originalExport===fs.readFileSync(`${dir}/historico_restaurado.txt`,'utf8');
  assert.equal(preserved,true);await record('restaurar_conversa',{preserved,passed:true});
  if(mode==='final'){
   const separate=await browser.newContext();const other=await separate.newPage();
   await other.goto(oldUrl);await other.getByPlaceholder('Faça sua pergunta').waitFor({timeout:60000});
   await other.waitForTimeout(1000);
   assert.equal(await other.locator('[data-testid="stChatMessage"]').count(),0);
   await record('outra_sessao',{passed:true});await separate.close();
  }
  await page.reload();await page.getByPlaceholder('Faça sua pergunta').waitFor({timeout:60000});
  await page.waitForTimeout(1000);
  const reloadMessages=await page.locator('[data-testid="stChatMessage"]').count();assert.equal(reloadMessages,0);
  await record('reload',{passed:true,messages:reloadMessages,text:await page.locator('body').innerText()});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:`${dir}/mobile.png`,fullPage:true});
  await record('mobile',{horizontalOverflow:await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)});
  assert.equal(errors.length,0);
 }finally{save();await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
