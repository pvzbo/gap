/* GAP — triagem (porta do protótipo genealogia-triagem.html sobre a API FastAPI). */
const FONTE = document.body.dataset.fonte;
const el = id => document.getElementById(id);
const toast = el('toast');
function aviso(msg, erro){ toast.textContent = msg; toast.className = 'toast on' + (erro ? ' erro' : ''); setTimeout(()=>toast.className='toast', 3000); }
async function api(url, body){
  const r = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  const j = await r.json().catch(()=>({erro:'resposta inválida'}));
  if(!r.ok) throw new Error(j.erro || r.statusText);
  return j;
}
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

let VOCAB = null, PESSOAS = [], FILA = [], DECISOES = [], PLACAR = {}, N_TOTAL = 0;
let i = 0, categoriaAtual = 'relacao';

const ALERTA_ROT = {entidade:'Resolução de entidade', novo:'Pessoa nova', dup:'Vínculo já existente', fraco:'Evidência fraca', info:'Contexto', depoimento:'Não é uma relação', erro:'Erro'};
const NOVO = '__novo__';

function opcoesPessoas(sel, comVazio, comNovo){
  const atual = sel.value;
  sel.innerHTML = comVazio ? '<option value="">— indefinido —</option>' : '';
  if(comNovo){ const o = document.createElement('option'); o.value = NOVO; o.textContent = '+ nova pessoa…'; sel.appendChild(o); }
  PESSOAS.forEach(p=>{ const o = document.createElement('option'); o.value = p.id; o.textContent = p.nome + (p.atribuicao ? ` · ${p.atribuicao}` : ''); sel.appendChild(o); });
  if([...sel.options].some(o=>o.value===atual)) sel.value = atual;
}
function opcoesTipos(sel, comVazio){
  sel.innerHTML = comVazio ? '<option value="">— nenhum —</option>' : '';
  VOCAB.tipos.forEach((t, k)=>{ const o = document.createElement('option'); o.value = t.id; o.textContent = `${k+1} · ${t.rotulo}`; sel.appendChild(o); });
}
function nome(id){ const p = PESSOAS.find(x=>x.id===id); return p ? p.nome : (id || '?'); }

async function carregarTudo(){
  [VOCAB, PESSOAS] = await Promise.all([api('/api/vocabulario'), api('/api/pessoas')]);
  ['fOrigem','fDestino','mOrigem','mDestino'].forEach(id => opcoesPessoas(el(id), true, id.startsWith('f')));
  opcoesPessoas(el('dPessoa'), true, true);
  opcoesTipos(el('fTipo'), true); opcoesTipos(el('mTipo'), true);
  const mf = el('mFonte'); mf.innerHTML = '<option value="">— sem fonte (só hipótese com pendência) —</option>';
  VOCAB.fontes.forEach(f=>{ const o = document.createElement('option'); o.value = f.id; o.textContent = f.rotulo; mf.appendChild(o); });
  if(FONTE !== 'manual') mf.value = FONTE;
  await carregarFila();
}

async function carregarFila(){
  const j = await api(`/api/fila/${FONTE}`);
  FILA = j.itens; DECISOES = j.decisoes; PLACAR = j.placar; N_TOTAL = j.n_total;
  el('git').textContent = j.git.disponivel ? `· git ${j.git.branch} @ ${j.git.commit || '—'}` : '· sem git (grava sem commit)';
  i = 0; atualizar(); mostrar();
}

function realcar(texto, item){
  let html = esc(texto || '');
  const nomes = [];
  if(item.categoria === 'relacao'){ nomes.push(item.proposta.origem_nome, item.proposta.destino_nome); }
  else { nomes.push(item.proposta.pessoa_nome); }
  const trecho = item.proposta.trecho;
  if(trecho && trecho.length > 12){
    const t = esc(trecho).replace(/\s+/g,' ').trim();
    const idx = html.replace(/\s+/g,' ').indexOf(t);
    if(idx >= 0){ const norm = html.replace(/\s+/g,' '); html = norm.slice(0, idx) + '<mark>' + norm.slice(idx, idx + t.length) + '</mark>' + norm.slice(idx + t.length); }
  }
  nomes.filter(Boolean).forEach(n=>{
    const re = new RegExp(esc(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    html = html.replace(re, m => `<span class="nome">${m}</span>`);
  });
  return html;
}

function mostrar(){
  const cartao = el('cartao');
  if(!FILA.length){
    el('cabFonte').textContent = FONTE === 'manual' ? 'Entrada manual' : `${FONTE}`;
    el('indice').textContent = N_TOTAL ? `${N_TOTAL} / ${N_TOTAL} decididos` : 'sem fila';
    el('barra').style.width = '100%';
    el('trecho').innerHTML = N_TOTAL
      ? '<span class="ctx">Fila concluída. Use a entrada manual à direita para relações que o leitor infere, ou volte ao painel para marcar a fonte como processada.</span>'
      : '<span class="ctx">Esta fonte ainda não tem fila de candidatos (rode Chunks → Pré-filtro → Extrair → Fila no painel). A entrada manual à direita funciona normalmente.</span>';
    el('alertas').innerHTML = '';
    el('formRelacao').classList.add('oculto'); el('formDepoimento').classList.add('oculto');
    ['bAceitar','bAdiar','bDescartar','bDepoimento'].forEach(b=>el(b).disabled = true);
    return;
  }
  ['bAceitar','bAdiar','bDescartar','bDepoimento'].forEach(b=>el(b).disabled = false);
  const c = FILA[i];
  categoriaAtual = c.categoria;
  el('cabFonte').textContent = `${c.fonte} · p. ${c.pagina ?? '?'} · ${c.candidato_id}` + (c.modelo ? ` · ${c.modelo}` : '');
  el('indice').textContent = `${N_TOTAL - FILA.length + 1} / ${N_TOTAL}`;
  el('barra').style.width = ((N_TOTAL - FILA.length) / Math.max(N_TOTAL,1) * 100) + '%';
  el('trecho').innerHTML =
    (c.contexto_anterior ? `<span class="ctx">${esc(c.contexto_anterior)} </span>` : '') +
    realcar(c.texto, c) +
    (c.contexto_posterior ? `<span class="ctx"> ${esc(c.contexto_posterior)}</span>` : '');
  const alertas = [...(c.alertas || [])];
  if(c.observacao) alertas.push({tipo:'info', texto:`Nota do extrator: ${c.observacao}`});
  if(c.erro_extracao) alertas.push({tipo:'erro', texto:c.erro_extracao});
  if(c.proposta && c.proposta.justificativa) alertas.push({tipo:'info', texto:`Justificativa: ${c.proposta.justificativa}`});
  el('alertas').innerHTML = alertas.map(a=>`<div class="alerta ${a.tipo}"><b>${ALERTA_ROT[a.tipo] || a.tipo}.</b> ${esc(a.texto)}</div>`).join('');

  if(c.categoria === 'relacao'){
    el('formRelacao').classList.remove('oculto'); el('formDepoimento').classList.add('oculto');
    const p = c.proposta;
    el('fOrigem').value = p.origem || ''; el('fDestino').value = p.destino || '';
    el('fOrigemNome').textContent = p.origem_nome ? `no texto: “${p.origem_nome}”` : '';
    el('fDestinoNome').textContent = p.destino_nome ? `no texto: “${p.destino_nome}”` : '';
    prepararNova('Origem', c.resolucao.origem, p.origem_nome);
    prepararNova('Destino', c.resolucao.destino, p.destino_nome);
    el('fTipo').value = p.tipo || ''; el('fConf').value = p.confianca || 'documentado';
    el('fSubtipo').value = p.subtipo || ''; el('fPeriodo').value = p.periodo || '';
    el('fDesc').value = p.descricao || ''; el('fTrecho').value = p.trecho || '';
    el('fPagina').value = c.pagina ?? ''; el('fSim').checked = !!p.simetrico; el('fPend').value = p.pendencia || '';
    mostrarPar();
  } else {
    el('formRelacao').classList.add('oculto'); el('formDepoimento').classList.remove('oculto');
    const p = c.proposta;
    el('dPessoa').value = p.pessoa || (c.resolucao.pessoa && c.resolucao.pessoa.decisao === 'novo' ? NOVO : '');
    el('dPessoaNome').textContent = p.pessoa_nome ? `no texto: “${p.pessoa_nome}”` : '';
    el('dExiste').value = p.existe_escola === true ? 'true' : p.existe_escola === false ? 'false' : '';
    el('dArg').value = p.argumento || ''; el('dTrecho').value = p.trecho || ''; el('dPagina').value = c.pagina ?? ''; el('dData').value = '';
  }
}

function prepararNova(lado, res, nomeTexto){
  const box = el('nova' + lado), sel = el(lado === 'Origem' ? 'fOrigem' : 'fDestino');
  const pref = lado === 'Origem' ? 'no' : 'nd';
  if(res && res.decisao === 'novo' && !sel.value){ sel.value = NOVO; }
  box.classList.toggle('oculto', sel.value !== NOVO);
  el(pref + 'Nome').value = (res && res.nome_limpo) || nomeTexto || '';
}
['fOrigem','fDestino'].forEach(id => el(id).onchange = ()=>{
  el(id === 'fOrigem' ? 'novaOrigem' : 'novaDestino').classList.toggle('oculto', el(id).value !== NOVO);
  mostrarPar();
});
el('dPessoa').onchange = ()=>{};

async function mostrarPar(){
  const o = el('fOrigem').value, d = el('fDestino').value;
  const box = el('parExistente');
  if(!o || !d || o === NOVO || d === NOVO){ box.textContent = ''; return; }
  try{
    const rels = await api(`/api/par/${o}/${d}`);
    box.innerHTML = rels.length ? 'Já na base para este par: ' + rels.map(r=>`<b>${r.id}</b> ${r.tipo}${r.periodo ? ' ('+esc(r.periodo)+')' : ''} · ${(r.fontes||[]).length} fonte(s)`).join(' · ') : 'Nenhum vínculo registrado ainda para este par.';
  }catch(e){ box.textContent = ''; }
}

function dadosRelacao(){
  const d = {
    origem: el('fOrigem').value === NOVO ? null : el('fOrigem').value,
    destino: el('fDestino').value === NOVO ? null : el('fDestino').value,
    tipo: el('fTipo').value || null, confianca: el('fConf').value, subtipo: el('fSubtipo').value,
    periodo: el('fPeriodo').value, descricao: el('fDesc').value, trecho: el('fTrecho').value,
    pagina: el('fPagina').value, simetrico: el('fSim').checked, pendencia: el('fPend').value,
  };
  const c = FILA[i];
  if(c){ d.origem_nome = c.proposta.origem_nome; d.destino_nome = c.proposta.destino_nome; }
  if(el('fOrigem').value === NOVO) d.nova_origem = {nome: el('noNome').value, atribuicao: el('noAtrib').value, papel_historiografico: el('noPapel').value};
  if(el('fDestino').value === NOVO) d.nova_destino = {nome: el('ndNome').value, atribuicao: el('ndAtrib').value, papel_historiografico: el('ndPapel').value};
  return d;
}
function dadosDepoimento(){
  const c = FILA[i];
  const d = {
    pessoa: el('dPessoa').value === NOVO ? null : el('dPessoa').value,
    existe_escola: el('dExiste').value === '' ? null : el('dExiste').value === 'true',
    argumento: el('dArg').value, trecho: el('dTrecho').value, pagina: el('dPagina').value, data_depoimento: el('dData').value,
    pessoa_nome: c ? c.proposta.pessoa_nome : null,
  };
  if(el('dPessoa').value === NOVO) d.nova_pessoa = {nome: c ? (c.resolucao.pessoa.nome_limpo || c.proposta.pessoa_nome) : ''};
  return d;
}

async function decidir(acao){
  if(!FILA.length) return;
  const c = FILA[i];
  const resumo = c.categoria === 'relacao' ? `${c.proposta.origem_nome || '?'} → ${c.proposta.destino_nome || '?'} · ${c.proposta.tipo || '?'}` : `depoimento de ${c.proposta.pessoa_nome || '?'}`;
  try{
    let j;
    if(acao === 'aceitar'){
      const body = {fonte: FONTE, item_id: c.id, acao, categoria: categoriaAtual, dados: categoriaAtual === 'depoimento' ? dadosDepoimento() : dadosRelacao()};
      j = await api('/api/decisao', body);
      el('saida').textContent = JSON.stringify(j.decisao.dados, null, 0) + (j.commit ? `\n// commit ${j.commit}` : '\n// sem commit (git indisponível)');
      aviso(j.mesclada ? `Fonte acrescentada a ${j.relacao_id}` : `Gravado ${j.relacao_id || j.depoimento_id}` + (j.commit ? ` · commit ${j.commit}` : ''));
      if(j.efeitos && j.efeitos.some(e=>e.tipo==='pessoa_nova' || e.tipo==='alias_novo')) PESSOAS = await api('/api/pessoas'), ['fOrigem','fDestino','mOrigem','mDestino'].forEach(id => opcoesPessoas(el(id), true, id.startsWith('f'))), opcoesPessoas(el('dPessoa'), true, true);
    } else {
      j = await api('/api/decisao', {fonte: FONTE, item_id: c.id, acao, resumo});
      aviso(acao === 'adiar' ? 'Adiado (volta ao fim da fila)' : 'Descartado');
    }
    FILA.splice(i, 1); if(acao === 'adiar') FILA.push(c);
    DECISOES.unshift(j.decisao); PLACAR[acao === 'aceitar' ? 'aceitos' : acao === 'adiar' ? 'adiados' : 'descartados']++;
    if(i >= FILA.length) i = 0;
    atualizar(); mostrar();
  }catch(e){ aviso(e.message, true); }
}

async function desfazer(){
  try{
    const j = await api(`/api/desfazer/${FONTE}`, {});
    aviso('Desfeito: ' + (j.desfeita.resumo || j.desfeita.item_id) + (j.avisos.length ? ' · ' + j.avisos.join(' ') : ''));
    PESSOAS = await api('/api/pessoas');
    await carregarFila();
  }catch(e){ aviso(e.message, true); }
}

function atualizar(){
  el('nA').textContent = PLACAR.aceitos || 0; el('nD').textContent = PLACAR.descartados || 0; el('nS').textContent = PLACAR.adiados || 0;
  el('nDecisoes').textContent = DECISOES.length ? `${DECISOES.length}` : '';
  const ul = el('historico');
  ul.innerHTML = DECISOES.length ? '' : '<li class="vazio">Nenhuma decisão ainda.</li>';
  DECISOES.slice(0, 40).forEach(h=>{
    const li = document.createElement('li');
    const cls = h.acao === 'aceitar' ? 'a' : h.acao === 'descartar' ? 'd' : 's';
    li.innerHTML = `<span class="tag ${cls}">${h.acao === 'aceitar' ? 'aceito' : h.acao === 'descartar' ? 'descarte' : 'adiado'}</span><span>${esc(h.resumo || h.item_id || '')}${h.commit ? ` <span class="sub">· ${h.commit}</span>` : ''}</span>`;
    ul.appendChild(li);
  });
}

el('bAceitar').onclick = ()=>decidir('aceitar');
el('bDescartar').onclick = ()=>decidir('descartar');
el('bAdiar').onclick = ()=>decidir('adiar');
el('bDesfazer').onclick = desfazer;
el('bDepoimento').onclick = ()=>{
  if(!FILA.length) return;
  const c = FILA[i];
  categoriaAtual = categoriaAtual === 'relacao' ? 'depoimento' : 'relacao';
  el('formRelacao').classList.toggle('oculto', categoriaAtual !== 'relacao');
  el('formDepoimento').classList.toggle('oculto', categoriaAtual !== 'depoimento');
  if(categoriaAtual === 'depoimento' && c.categoria === 'relacao'){
    el('dPessoa').value = c.proposta.destino || c.proposta.origem || '';
    el('dArg').value = c.proposta.descricao || ''; el('dTrecho').value = c.proposta.trecho || ''; el('dPagina').value = c.pagina ?? '';
  }
  el('bDepoimento').textContent = categoriaAtual === 'relacao' ? '→ Depoimento' : '→ Relação';
};

el('bManual').onclick = async ()=>{
  const body = {fonte: el('mFonte').value || 'manual', acao: 'aceitar', categoria: 'relacao', dados: {
    origem: el('mOrigem').value, destino: el('mDestino').value, tipo: el('mTipo').value, confianca: el('mConf').value,
    pagina: el('mPagina').value, periodo: el('mPeriodo').value, simetrico: el('mSim').checked,
    descricao: el('mDesc').value, trecho: el('mTrecho').value, pendencia: el('mPend').value,
  }};
  try{
    const j = await api('/api/decisao', body);
    el('saida').textContent = JSON.stringify(j.decisao.dados) + (j.commit ? `\n// commit ${j.commit}` : '');
    aviso((j.mesclada ? `Fonte acrescentada a ${j.relacao_id}` : `Gravado ${j.relacao_id}`) + (j.commit ? ` · commit ${j.commit}` : ''));
    ['mPagina','mPeriodo','mDesc','mTrecho','mPend'].forEach(id=>el(id).value='');
    if(body.fonte === FONTE || FONTE === 'manual') DECISOES.unshift(j.decisao), PLACAR.aceitos = (PLACAR.aceitos||0)+1, atualizar();
  }catch(e){ aviso(e.message, true); }
};

el('bPessoa').onclick = async ()=>{
  try{
    const j = await api('/api/pessoa', {nome: el('pNome').value, atribuicao: el('pAtrib').value, papel_historiografico: el('pPapel').value, notas: el('pNotas').value, fonte: FONTE === 'manual' ? null : FONTE});
    aviso(`Pessoa criada: ${j.pessoa.id}` + (j.commit ? ` · commit ${j.commit}` : ''));
    PESSOAS = await api('/api/pessoas');
    ['fOrigem','fDestino','mOrigem','mDestino'].forEach(id => opcoesPessoas(el(id), true, id.startsWith('f'))); opcoesPessoas(el('dPessoa'), true, true);
    ['pNome','pNotas'].forEach(id=>el(id).value='');
  }catch(e){ aviso(e.message, true); }
};

document.addEventListener('keydown', e=>{
  if(/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  const k = e.key.toLowerCase();
  if(k === 'a') decidir('aceitar');
  else if(k === 'd') decidir('descartar');
  else if(k === 's') decidir('adiar');
  else if(k === 'z') desfazer();
  else if(k === 'x'){ const o = el('fOrigem').value; el('fOrigem').value = el('fDestino').value; el('fDestino').value = o; mostrarPar(); }
  else if(/^[1-7]$/.test(k) && VOCAB){ el('fTipo').value = VOCAB.tipos[+k-1].id; }
});

carregarTudo().catch(e=>aviso(e.message, true));
