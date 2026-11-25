'use strict';
const $ = id => document.getElementById(id);
const state = {answer:'',question:'',sources:[],selectedIds:[],searchId:null,busy:false,history:[],detailNumber:null};
const safeStorage = {
  get(){try{return JSON.parse(sessionStorage.getItem('landlex_history')||'[]')}catch{return []}},
  set(x){try{sessionStorage.setItem('landlex_history',JSON.stringify(x))}catch{}}
};
const el = (tag, cls, txt) => {
  const node=document.createElement(tag);
  if(cls) node.className=cls;
  if(txt!==undefined) node.textContent=String(txt);
  return node;
};
const formatDate = v => {
  if(!v) return '발행일 미확인';
  if(/^\d{8}$/.test(v)) return `${v.slice(0,4)}-${v.slice(4,6)}-${v.slice(6,8)}`;
  return v;
};
const newQuestion = () => {
  $('results').classList.add('hidden');$('welcome').classList.remove('hidden');
  $('question').value='';$('question').focus();
  $('sidebar').classList.remove('open');
  closeDetailPanel();
};
const showHistory = () => {
  $('history').replaceChildren();
  for(const rec of state.history.slice(0,12)){
    const b=el('button','history-item',rec.question);
    b.type='button';b.title=rec.question;
    b.addEventListener('click',()=>renderResult(rec));
    $('history').append(b);
  }
};
const addHistory = rec => {
  state.history=[rec,...state.history.filter(x=>x.question!==rec.question)].slice(0,10);
  safeStorage.set(state.history);showHistory();
};
// A blue reference means a statute/regulation; green means an interpretation or Q&A.
// Do not use innerHTML for user/AI generated text: citation links are safe DOM nodes.
function sourceColor(kind){
  if(kind === '법령') return 'law';
  if(['법제처 해석례','법제처 법령해석','국토부 질의회신','질의회신'].includes(kind)) return 'qa';
  if(kind === '판례') return 'case';
  return 'other';
}

function setDetailPanelSource(number){
  const src=state.sources[number-1];
  if(!src) return;
  state.detailNumber=number;
  const color=sourceColor(src.kind);
  $('detail-index').className='detail-index cite-'+color;
  $('detail-index').textContent='['+number+']';
  $('detail-kind').className='detail-kind kind-'+color;
  $('detail-kind').textContent=src.kind||'자료';
  $('detail-title').textContent=src.title||src.kind||'근거자료';
  $('detail-meta').textContent=`${src.case_number?'안건 '+src.case_number+' · ':''}${src.organization||'기관 미확인'} · ${formatDate(src.issued_date)}`;
  const score=$('detail-score');
  if(typeof src.match_score==='number'){
    score.textContent='검색 일치 '+src.match_score+'점 · 제목·본문·안건번호 일치 정도를 바탕으로 계산한 상대 점수입니다.';
    score.classList.remove('hidden');
  }else{
    score.classList.add('hidden');
    score.textContent='';
  }
  $('detail-body').textContent=src.body||'원문 요약을 가져오지 못했습니다.';
  const link=$('detail-link');
  if(src.url && /^https?:\/\//i.test(src.url)){
    link.href=src.url;
    link.classList.remove('hidden');
  }else{
    link.removeAttribute('href');
    link.classList.add('hidden');
  }
  const openBtn=$('detail-inline-open');
  openBtn.classList.remove('hidden');
  openBtn.onclick=()=>{
    const card=$('source-card-'+number);
    if(!card) return;
    const detail=card.querySelector('.source-details');
    const toggle=card.querySelector('.source-inline-toggle');
    if(detail.classList.contains('hidden')){
      detail.classList.remove('hidden');
      if(toggle){toggle.textContent='−';toggle.setAttribute('aria-expanded','true');}
    }
    card.scrollIntoView({behavior:'smooth',block:'center'});
  };
  $('detail-panel').classList.remove('hidden');
  $('detail-panel').querySelector('.detail-panel-body').scrollTop=0;
  document.body.classList.add('detail-open');
}
function closeDetailPanel(){
  state.detailNumber=null;
  document.body.classList.remove('detail-open');
  $('detail-panel').classList.add('hidden');
}
function openDetailPanel(number){
  setDetailPanelSource(number);
}
function openCitation(number){
  const card=$('source-card-'+number);
  if(!card)return;
  openDetailPanel(number);
  // Preserve scroll position: the full text is opened in the fixed right panel.
  card.classList.add('citation-focus');
  setTimeout(()=>card.classList.remove('citation-focus'),1800);
}
function citationTitle(s){
  if(s.kind==='법령'){
    return (s.title||'법령')
      .replace('경제자유구역의 지정 및 운영에 관한 특별법','경제자유구역법')
      .replace('국토의 계획 및 이용에 관한 법률','국토계획법')
      .replace('산업집적활성화 및 공장설립에 관한 법률','산업집적법');
  }
  if(s.case_number){
    const who=s.kind==='국토부 질의회신'?'국토부':s.kind==='법제처 해석례'||s.kind==='법제처 법령해석'?'법제처':s.kind;
    return who+' '+s.case_number;
  }
  return s.title||s.kind||'근거자료';
}
function showAnswer(answer, sources, selectedIds){
  const container=$('answer-text');container.replaceChildren();
  const allowed=new Set(selectedIds||[]);
  // Supports new [1], legacy [자료 1], and simple **bold** from LLMs.
  const parts=/\[(?:자료\s*)?(\d{1,2})\]|\*\*([^*\n]+)\*\*/g;
  let from=0,m;
  while((m=parts.exec(answer))!==null){
    if(m.index>from) container.append(document.createTextNode(answer.slice(from,m.index)));
    if(m[2] !== undefined){
      container.append(el('strong','',m[2]));
    }else{
      const idx=Number(m[1]);
      const src=sources[idx-1];
      const id=src && (src.ref_id||'s'+idx);
      // Never link a hallucinated or non-selected citation as verified evidence.
      if(src && allowed.has(id)){
        const cite=el('button','citation-link cite-'+sourceColor(src.kind));
        cite.append(el('b','citation-number','['+idx+']'),el('span','citation-title',citationTitle(src)));
        cite.type='button';cite.title='오른쪽 패널에서 원문 보기 · '+src.kind+' · '+src.title;
        cite.setAttribute('aria-label','근거 ['+idx+'] '+src.title+' 확인');
        cite.addEventListener('click',()=>openCitation(idx));
        container.append(cite);
      }else{
        const bad=el('span','citation-unverified','['+idx+']');
        bad.title='현재 AI 참고자료에 없는 번호입니다. 근거로 인정하지 마세요.';
        container.append(bad);
      }
    }
    from=parts.lastIndex;
  }
  if(from<answer.length)container.append(document.createTextNode(answer.slice(from)));
}
function updateSelectionTools(){
  $('selected-count').textContent='다음 분석에 선택 '+state.selectedIds.length+'/12건';
  $('reanalyze').disabled=state.busy || !state.searchId || state.selectedIds.length===0 || state.selectedIds.length>12;
  $('reanalyze').title=state.searchId?'체크한 근거만 AI에게 보내 답변을 다시 만듭니다.':'검색 결과를 새로 만들어야 선택 근거 분석을 사용할 수 있습니다.';
}
function showSources(sources){
  $('sources').replaceChildren();
  $('source-count').textContent=String(sources.length);
  if(!sources.length){
    $('sources').append(el('p','legal-warning','검색된 근거자료가 없습니다. 관련 키워드로 다시 검색하거나 관리자가 원문을 등록해야 합니다.'));
    updateSelectionTools();return;
  }
  sources.forEach((s,i)=>{
    const number=i+1;
    const color=sourceColor(s.kind);
    const id=s.ref_id||'s'+number;
    const card=el('article','source-card');card.id='source-card-'+number;
    card.classList.toggle('ai-selected',state.selectedIds.includes(id));
    const row=el('div','source-row');
    const select=el('label','source-checkbox');
    const check=el('input');check.type='checkbox';check.checked=state.selectedIds.includes(id);
    check.disabled=!state.searchId;
    check.setAttribute('aria-label','['+number+'] '+s.title+' AI 참고자료 선택');
    check.addEventListener('change',()=>{
      if(check.checked){
        if(state.selectedIds.length>=12){check.checked=false;alert('AI 참고자료는 최대 12건까지 선택할 수 있습니다.');return;}
        state.selectedIds.push(id);
      }else state.selectedIds=state.selectedIds.filter(x=>x!==id);
      card.classList.toggle('ai-selected',check.checked);
      updateSelectionTools();
    });
    select.append(check,el('span','','AI'));
    const top=el('button','source-top');top.type='button';
    top.setAttribute('aria-label','['+number+'] '+(s.title||'제목 없음')+' 오른쪽 패널에서 열기');
    top.title='오른쪽 패널에서 원문 보기';
    top.append(el('span','source-index cite-'+color,'['+number+']'));
    const copy=el('div','source-copy');
    const meta=el('div','source-kind kind-'+color,s.kind);
    copy.append(meta,el('div','source-title',s.title||'제목 없음'));
    copy.append(el('div','source-meta',`${s.case_number?'안건 '+s.case_number+' · ':''}${s.organization||'기관 미확인'} · ${formatDate(s.issued_date)}`));
    const score=s.match_score;
    if(typeof score==='number'){
      const indicator=el('div','source-score',`검색 일치 ${score}점`);
      indicator.title='제목·본문의 검색어 일치 정도와 안건번호로 계산한 상대 점수입니다. 법적 정확도는 아닙니다.';
      copy.append(indicator);
    }
    top.append(copy);
    const inlineToggle=el('button','source-inline-toggle','＋');
    inlineToggle.type='button';
    inlineToggle.setAttribute('aria-label','['+number+'] 아래에서 원문 펼치기');
    inlineToggle.title='여기에서 원문 펼치기';
    inlineToggle.setAttribute('aria-expanded','false');
    const detail=el('div','source-details hidden');
    detail.append(el('pre','',s.body||'원문 요약을 가져오지 못했습니다.'));
    if(s.url && /^https?:\/\//i.test(s.url)){
      const link=el('a','','원문 페이지 열기 ↗');link.href=s.url;link.target='_blank';link.rel='noopener noreferrer';detail.append(link);
    }else detail.append(el('span','no-link','등록된 공개 원문 링크가 없습니다.'));
    top.addEventListener('click',()=>{openDetailPanel(number);});
    inlineToggle.addEventListener('click',(e)=>{
      e.stopPropagation();
      const hidden=detail.classList.toggle('hidden');
      inlineToggle.setAttribute('aria-expanded',String(!hidden));
      inlineToggle.textContent=hidden?'＋':'−';
    });
    row.append(select,top,inlineToggle);card.append(row,detail);$('sources').append(card);
  });
  updateSelectionTools();
}
function renderResult(data){
  const plan=data.search_plan||{};
  const planPanel=$('search-plan-panel');
  const planList=$('search-plan-list');
  planList.replaceChildren();
  // v10: never silently hide a failed planner. Show status only on expansion.
  planPanel.classList.remove('hidden');
  planPanel.open=false;
  const descriptions={
    ok:'AI 질문 재구성 성공',disabled:'AI 질문 재구성 비활성화',
    provider_not_gemini:'AI 질문 재구성 미지원 제공자',
    missing_key:'AI 질문 재구성 키 미설정',invalid_model:'모델 설정 오류',
    http_400:'AI 질문 재구성 요청 오류(400)',
    http_401:'AI 질문 재구성 인증 오류(401)',
    http_403:'AI 질문 재구성 접근 제한(403)',
    http_429:'AI 질문 재구성 사용량 한도(429)',
    timeout:'AI 질문 재구성 시간 초과',network_error:'AI 질문 재구성 네트워크 오류',
    invalid_response:'AI 질문 재구성 응답 해석 실패',
    invalid_questions:'AI 검색 질문 생성 실패',
    unavailable:'AI 질문 재구성 실패 또는 설정 미확인',
    not_generated:'AI 질문 재구성 결과 없음'
  };
  const worked=!!plan.used_ai && Array.isArray(plan.search_questions) && plan.search_questions.length>0;
  const title=descriptions[plan.status] || (worked?'AI 질문 재구성 성공':'AI 질문 재구성 미실행');
  planList.append(el('p','search-plan-status',title));
  if(worked){
    if(plan.issue)planList.append(el('div','search-plan-issue','검색 쟁점: '+plan.issue));
    for(const q of plan.search_questions.slice(0,2))planList.append(el('p','','생성: '+q));
  }else{
    planList.append(el('p','','원래 질문으로 검색했습니다. 검색 계획을 AI가 생성하지 못했을 수 있습니다.'));
  }
  if(Array.isArray(plan.official_queries)){
    planList.append(el('p','','추가 법령 조회: '+plan.official_queries.length+'회'));
    for(const q of plan.official_queries)planList.append(el('p','','조회: '+q));
  }
  if(typeof plan.statute_articles_selected==='number'){
    planList.append(el('p','','AI에 전달된 법령 조문: '+plan.statute_articles_selected+'건'));
    if(plan.statute_articles_selected===0){
      planList.append(el('p','','법령 조문이 선택되지 않았습니다. 현재 답변은 단정하기 어렵습니다.'));
    }
  }
  planList.append(el('small','','생성한 검색 질문은 법적 근거가 아니며, 공식 법령 원문으로 검증해야 합니다.'));
  state.answer=data.answer;state.question=data.question;state.sources=data.sources||[];
  state.searchId=data.search_id||null;
  state.selectedIds=Array.isArray(data.selected_ids)?[...data.selected_ids]:state.sources.slice(0,12).map((s,i)=>s.ref_id||'s'+(i+1));
  $('welcome').classList.add('hidden');$('results').classList.remove('hidden');
  $('question-title').textContent=data.question;
  $('answer-date').textContent=new Date().toLocaleDateString('ko-KR');
  const labels={ai:'AI 분석 완료',search_only:'자료 검색 결과 (AI 미연결)',ai_error:'AI 생성 실패 · 자료만 표시',no_sources:'검색 결과 없음'};
  $('analysis-mode').textContent=labels[data.mode]||'문헌 검토';
  showAnswer(data.answer,state.sources,state.selectedIds);
  $('alerts').replaceChildren();
  for(const message of data.alerts||[]) $('alerts').append(el('div','alert',message));
  showSources(state.sources);
  closeDetailPanel();
  window.scrollTo({top:0,behavior:'smooth'});
  $('sidebar').classList.remove('open');
}
const ask = async question => {
  if(state.busy) return;
  const categories=[...document.querySelectorAll('#filters input[value]:checked')].map(e=>e.value);
  if(!categories.length){alert('검색 대상을 하나 이상 선택하세요.');return}
  state.busy=true;$('send').disabled=true;$('send').querySelector('span').textContent='검색 중...';
  try{
    const r=await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,categories,deep_search:$('deep-search').checked})});
    const result=await r.json();
    if(!r.ok)throw new Error(result.detail||'요청 오류');
    renderResult(result);
    addHistory(result);
  }catch(e){alert('요청을 처리하지 못했습니다: '+e.message)}
  finally{state.busy=false;$('send').disabled=false;$('send').querySelector('span').textContent='검색 및 분석'}
};
$('reanalyze').addEventListener('click', async()=>{
  if(state.busy || !state.searchId || !state.selectedIds.length)return;
  state.busy=true;updateSelectionTools();
  document.querySelectorAll('#sources .source-checkbox input').forEach(x=>x.disabled=true);
  $('reanalyze').textContent='다시 분석 중...';
  try{
    const r=await fetch('/api/reanalyze',{
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({search_id:state.searchId,selected_ids:state.selectedIds})
    });
    const result=await r.json();
    if(!r.ok)throw new Error(result.detail||'다시 분석하지 못했습니다.');
    renderResult(result);addHistory(result);
  }catch(e){alert('다시 분석 실패: '+e.message);}
  finally{state.busy=false;$('reanalyze').textContent='선택 자료로 다시 분석';
    document.querySelectorAll('#sources .source-checkbox input').forEach(x=>x.disabled=!state.searchId);
    updateSelectionTools();}
});
$('ask-form').addEventListener('submit',e=>{
  e.preventDefault();const question=$('question').value.trim();
  if(question.length<4){alert('질문을 4자 이상 입력하세요.');return}
  ask(question);
});
$('question').addEventListener('keydown',e=>{
  if(e.key==='Enter' && !e.shiftKey && !e.isComposing){e.preventDefault();$('ask-form').requestSubmit()}
});
$('new-chat').addEventListener('click',newQuestion);
$('nav-search').addEventListener('click',newQuestion);
$('mobile-menu').addEventListener('click',()=>$('sidebar').classList.toggle('open'));
for(const button of document.querySelectorAll('.example')){
  button.addEventListener('click',()=>{ $('question').value=button.dataset.question; ask(button.dataset.question) });
}
$('copy-answer').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(state.answer);$('copy-answer').textContent='복사됨';setTimeout(()=>$('copy-answer').textContent='복사',1300)}
  catch{alert('복사할 수 없습니다. 답변을 직접 선택해 복사해 주세요.')}
});
$('download-txt').addEventListener('click',()=>{
  let text=state.question+'\n\n'+state.answer+'\n\n[검색 근거자료]\n';
  state.sources.forEach((s,i)=>{text+=`${i+1}. ${s.title} (${s.organization||''}, ${formatDate(s.issued_date)})\n${s.url||'공개 링크 없음'}\n\n`});
  text+='\n[유의] 법령 시행일과 자료의 개정 여부는 원문에서 확인해 주세요.\n';
  const blob=new Blob(['\ufeff'+text],{type:'text/plain;charset=utf-8'});
  const url=URL.createObjectURL(blob),a=el('a');a.href=url;a.download='법령검토_검색결과.txt';
  document.body.append(a);a.click();a.remove();URL.revokeObjectURL(url);
});
$('nav-admin').addEventListener('click',()=>{$('sidebar').classList.remove('open');$('admin-dialog').showModal()});
$('admin-close').addEventListener('click',()=>$('admin-dialog').close());
function adminHeader(){return {'X-Admin-Token':$('admin-token').value.trim()}}
function adminMessage(message,isError=false){$('admin-message').textContent=message;$('admin-message').style.color=isError?'#b25a59':'#41765e'}
async function refreshDocs(){
  try{
    const r=await fetch('/api/admin/documents',{headers:adminHeader()});const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'관리자 인증에 실패했습니다.');
    $('doc-list').replaceChildren();
    if(!data.documents.length){$('doc-list').append(el('p','','아직 등록된 문서가 없습니다.'));return}
    for(const doc of data.documents){
      const row=el('div','doc-entry'), left=el('div');
      left.append(el('b','',doc.title),el('small','',`${doc.kind} · ${doc.organization||'발행기관 미확인'} · ${(doc.chunks||0).toLocaleString()}개 검색 구간 · ${(doc.page_count||0) ? doc.page_count+'쪽 · ':''}${(doc.characters||0).toLocaleString()}자`));
      const del=el('button','delete-button','삭제');del.type='button';
      del.addEventListener('click',async()=>{
        if(!confirm('이 자료를 삭제하시겠습니까?'))return;
        const res=await fetch(`/api/admin/documents/${doc.id}`,{method:'DELETE',headers:adminHeader()});
        if(!res.ok){adminMessage('삭제 실패',true);return}
        await refreshDocs();
      });
      row.append(left,del);$('doc-list').append(row);
    }
  }catch(e){adminMessage(e.message,true)}
}
$('refresh-docs').addEventListener('click',refreshDocs);
$('upload-form').addEventListener('submit',async e=>{
  e.preventDefault();adminMessage('자료를 등록하는 중입니다...');
  const fd=new FormData(e.target);
  try{
    const r=await fetch('/api/admin/upload',{method:'POST',headers:adminHeader(),body:fd});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'업로드 실패');
    if(!data.job_id)throw new Error('작업번호가 반환되지 않았습니다.');
    adminMessage('파일 전송 완료. 본문 추출과 검색 색인 생성 중입니다. 창을 닫지 않아도 서버에서 계속 진행됩니다.');
    e.target.reset();
    await pollIndexJob(data.job_id);
  }catch(error){adminMessage(error.message,true)}
});
async function pollIndexJob(jobId){
  for(;;){
    await new Promise(resolve=>setTimeout(resolve,1800));
    const r=await fetch(`/api/admin/jobs/${encodeURIComponent(jobId)}`,{headers:adminHeader()});
    const data=await r.json();
    if(!r.ok)throw new Error(data.detail||'색인 상태 조회 실패');
    if(data.status==='completed'){
      adminMessage(`${data.title} 등록 완료 · ${(data.chunks||0).toLocaleString()}개 검색 구간`);
      await refreshDocs();return;
    }
    if(data.status==='failed')throw new Error(data.message||'색인 생성 실패');
    adminMessage(`등록 진행 중: ${data.message||data.status} (큰 파일은 처리 시간이 길어질 수 있습니다)`);
  }
}
async function loadStatus(){
  try{
    const r=await fetch('/api/status');const data=await r.json();
    const providerLabels={gemini:'Gemini',ollama:'Ollama',openai:'OpenAI',off:'미설정'};
    const aiName=providerLabels[data.ai_provider]||'AI';
    const s=`${data.law_api_connected?'법령 API 설정됨':'법령 API 미설정'} · ${data.ai_connected?aiName+' 설정됨':'AI 미설정'}`;
    $('connections').textContent=s;$('side-status').textContent=s;$('status-dot').classList.toggle('online',data.law_api_connected);
    $('nav-admin').classList.toggle('hidden', !data.admin_enabled);
  }catch{$('connections').textContent='서버 상태 미확인';$('side-status').textContent='서버 상태 미확인'}
}
state.history=safeStorage.get();showHistory();loadStatus();

$('detail-close').addEventListener('click',closeDetailPanel);
$('detail-overlay').addEventListener('click',closeDetailPanel);
document.addEventListener('keydown',e=>{if(e.key==='Escape' && state.detailNumber!==null) closeDetailPanel();});
