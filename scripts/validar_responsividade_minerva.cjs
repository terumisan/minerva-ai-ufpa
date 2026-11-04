// Executar com Playwright e Chromium; usa uma pergunta sintética no app real.
const {chromium} = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
const navigationOnly=process.argv.includes('--navegacao');
const dir = process.env.MINERVA_UI_ARTIFACT_DIR || `/tmp/minerva-browser/${navigationOnly?'responsivo_navegacao':'responsivo'}`;
const sizes = [[320,740],[390,844],[600,960],[768,1024],[820,1180],[1024,768],[1180,820],[1440,1000]];
fs.mkdirSync(dir,{recursive:true});
(async()=>{
 const browser = await chromium.launch({headless:true,executablePath:process.env.MINERVA_CHROMIUM_EXECUTABLE || undefined});
 const context = await browser.newContext({viewport:{width:390,height:844},hasTouch:true});
 const page = await context.newPage();
 const results=[],errors=[];
 page.on('pageerror',error=>errors.push(error.stack));
 const save=()=>fs.writeFileSync(`${dir}/resultados.json`,JSON.stringify({results,errors},null,2));
 const record=(name,data)=>{results.push({name,...data});save();console.log(JSON.stringify(results.at(-1)));};
 async function navigation(){
  for(const width of [390,820]){
   await page.setViewportSize({width,height:1024});
   await page.waitForTimeout(800);
   if(await page.locator('[data-testid="stSidebar"]').getAttribute('aria-expanded')==='true'){
    await page.locator('[data-testid="stSidebarCollapseButton"] button').click();
   }
   await page.getByTestId('stExpandSidebarButton').click();
   await page.waitForFunction(()=>document.querySelector('[data-testid="stSidebar"]')?.getAttribute('aria-expanded')==='true');
   await page.waitForTimeout(600);
   const sidebar=page.getByTestId('stSidebar');
   const box=await sidebar.boundingBox();
   assert.ok(box.x>=-1&&box.width<=width-40);
   await sidebar.getByRole('button',{name:'＋ Nova conversa',exact:true}).waitFor();
   await page.screenshot({path:`${dir}/sidebar_${width}.png`});
   await page.locator('[data-testid="stSidebarCollapseButton"] button').click();
   await page.waitForFunction(()=>document.querySelector('[data-testid="stSidebar"]')?.getAttribute('aria-expanded')==='false');
   record(`sidebar_${width}`,{width:box.width,openedAndClosed:true,passed:true});
  }
 }
 async function layout(phase,width,height){
  await page.setViewportSize({width,height});
  await page.waitForTimeout(600);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
  assert.equal(overflow,false,`${phase} ${width}: overflow`);
  const header=page.locator('.st-key-header_card');
  const title=await header.getByRole('heading',{name:'Minerva AI',exact:true}).boundingBox();
  const themes=await header.getByRole('radio').all();
  assert.equal(themes.length,3);
  const positions=await Promise.all(themes.map(r=>r.boundingBox()));
  for(const p of [title,...positions])assert.ok(p&&p.x>=0&&p.x+p.width<=width+1,`${phase} ${width}: header fora da tela`);
  if(width<=1024)assert.ok(positions.every(p=>p.height>=44));
  const input=await page.getByPlaceholder('Faça sua pergunta').boundingBox();
  assert.ok(input.x>=0&&input.x+input.width<=width+1&&input.y+input.height<=height+1);
  const font=await page.getByPlaceholder('Faça sua pergunta').evaluate(el=>getComputedStyle(el).fontSize);
  if(width<=1024)assert.ok(parseFloat(font)>=16);
  if(phase==='chat'){
   const actions=page.locator('[class*="st-key-acoes_resposta_"]').last();
   const buttons=await Promise.all(['🤍','🖤','🔄'].map(name=>actions.getByRole('button',{name,exact:true}).boundingBox()));
   assert.ok(buttons.every(p=>p&&Math.abs(p.y-buttons[0].y)<3),`${width}: ações empilhadas`);
   if(width<=1024)assert.ok(buttons.every(p=>p.height>=43.9),JSON.stringify(buttons));
   await actions.scrollIntoViewIfNeeded();
  }else{
   await header.scrollIntoViewIfNeeded();
  }
  await page.screenshot({path:`${dir}/${phase}_${width}.png`});
  record(`${phase}_${width}`,{width,height,overflow,textareaFont:font});
 }
 try{
  await page.goto(process.env.MINERVA_UI_URL || 'http://127.0.0.1:8501');
  await page.getByPlaceholder('Faça sua pergunta').waitFor({timeout:60000});
  if(navigationOnly){
   await navigation();
   assert.equal(errors.length,0);
   return;
  }
  for(const [width,height] of sizes)await layout('home',width,height);
  // Clique em categoria e troca de tema devem continuar funcionando.
  await page.getByRole('button',{name:'Estágio',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('.minerva-v2-active')?.innerText.includes('Estágio'));
  assert.match(await page.locator('.minerva-v2-active').innerText(),/Estágio/);
  await page.locator('.st-key-header_card').getByRole('radio').last().click();
  await page.waitForTimeout(600);
  record('tema_escuro',{background:await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--minerva-bg').trim())});
  await page.locator('.st-key-header_card').getByRole('radio').nth(1).click();
  // Fecha a navegação antes de medir a área principal nas demais larguras.
  const collapse=page.locator('[data-testid="stSidebarCollapseButton"] button');
  if(await collapse.isVisible())await collapse.click();
  await page.getByPlaceholder('Faça sua pergunta').fill('Passei em TCC I: o que preciso entregar para me matricular no TCC II?');
  await page.getByPlaceholder('Faça sua pergunta').press('Enter');
  await page.locator('[class*="st-key-acoes_resposta_"]').last().getByRole('button',{name:'🤍',exact:true}).waitFor({timeout:240000});
  await page.waitForTimeout(1000);
  record('resposta_documental',{text:await page.locator('[data-testid="stChatMessage"]').last().innerText()});
  await page.getByRole('link',{name:'Abrir fonte oficial',exact:true}).first().waitFor({timeout:10000});
  for(const [width,height] of sizes)await layout('chat',width,height);
  await navigation();
  assert.equal(errors.length,0);
 }finally{save();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
