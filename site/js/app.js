/* GAP — explorador da rede (porta de genealogia-prototipo.html sobre data/grafo.json).
   Mesmo peso do Python: w(confiança) × (1 + 0,5 × (n_fontes − 1)), somado por par. */
'use strict';

const PESO_CONF = {documentado: 1.0, tradicao_oral: 0.6, hipotese: 0.3};
const el = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt = (x, nd = 2) => (x === null || x === undefined) ? '—' : (typeof x === 'number' ? (Number.isInteger(x) ? x : x.toFixed(nd)) : x);
const pct = x => (x === null || x === undefined) ? '—' : (x * 100).toFixed(1) + '%';

let D = null;                      // grafo.json
let ORD = [];                      // ordem dos tipos
const S = {tipos: new Set(), hip: true, rotulos: true, foco: null, inst: null, view: 'rede'};
let PESSOA = {};                   // id → pessoa
let FONTES = {};
let nos = [];                      // objetos de nó persistentes (posições)
let sim = null, W = 800, H = 600;

const svg = d3.select('#graph');
const g = svg.append('g');
const gRings = g.append('g');
const gLinks = g.append('g');
const gNodes = g.append('g');
const tip = d3.select('#tip');
svg.call(d3.zoom().scaleExtent([0.3, 3.5]).on('zoom', e => g.attr('transform', e.transform)));

function pesoRelacao(r){
  const n = new Set((r.fontes || []).map(f => f.fonte).filter(Boolean)).size;
  return (PESO_CONF[r.confianca] ?? 0.3) * (1 + 0.5 * (n - 1));
}
function citar(f){
  const src = FONTES[f.fonte];
  const ref = src ? `${src.autor || src.id}${src.ano ? ' (' + src.ano + ')' : ''}` : f.fonte;
  return ref + (f.pagina ? `, p. ${f.pagina}` : '');
}

// ------------------------------------------------------------------ carga
async function main(){
  try{
    const r = await fetch('data/grafo.json', {cache: 'no-store'});
    if(!r.ok) throw new Error(r.statusText);
    D = await r.json();
  }catch(e){
    el('subtitulo').textContent = 'não foi possível carregar data/grafo.json — rode `gap build` e sirva a pasta site/ por HTTP (gap site)';
    return;
  }
  ORD = Object.keys(D.tipos);
  S.tipos = new Set(ORD);
  D.pessoas.forEach(p => PESSOA[p.id] = p);
  FONTES = D.fontes || {};
  nos = D.pessoas.map(p => ({id: p.id, nome: p.nome, papel: p.papel || 'outro', pend: !!p.pendencia}));
  el('subtitulo').textContent = `${D.meta.n_pessoas} pessoas · ${D.meta.n_relacoes} relações · ${D.meta.n_arestas} pares · ${D.meta.n_fontes_processadas}/${D.meta.n_fontes} fontes processadas · dados ${D.meta.commit ? '@ ' + D.meta.commit : D.meta.gerado_em.slice(0, 10)}`;
  montarControles();
  dimensionar();
  window.addEventListener('resize', () => { dimensionar(); if(S.view === 'rede') render(); });
  window.addEventListener('hashchange', roteador);
  roteador();
}

// ------------------------------------------------------------------ roteador
function roteador(){
  const h = decodeURIComponent(location.hash || '#rede');
  if(h.startsWith('#pessoa=')){ S.view = 'rede'; S.foco = h.slice(8) in PESSOA ? h.slice(8) : null; }
  else if(h === '#metricas'){ S.view = 'metricas'; }
  else if(h === '#sobre'){ S.view = 'sobre'; }
  else { S.view = 'rede'; }
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('ativo', a.dataset.view === S.view));
  const rede = S.view === 'rede';
  el('controles').classList.toggle('oculto', !rede);
  el('canvasWrap').classList.toggle('oculto', !rede);
  el('painelPessoa').classList.toggle('fechado', !(rede && S.foco));
  el('viewMetricas').classList.toggle('oculto', S.view !== 'metricas');
  el('viewSobre').classList.toggle('oculto', S.view !== 'sobre');
  if(rede){ el('seletor').value = S.foco || ''; render(); }
  else if(S.view === 'metricas') renderMetricas();
  else renderSobre();
}
function focar(id){
  S.foco = (S.foco === id) ? null : id;
  history.replaceState(null, '', S.foco ? '#pessoa=' + encodeURIComponent(S.foco) : '#rede');
  el('seletor').value = S.foco || '';
  el('painelPessoa').classList.toggle('fechado', !S.foco);
  render();
}

// ------------------------------------------------------------------ dados visíveis
function arestasVisiveis(){
  const out = [];
  for(const e of D.arestas){
    const rels = e.relacoes.filter(r => S.tipos.has(r.tipo) && (S.hip || r.confianca !== 'hipotese'));
    if(!rels.length) continue;
    const cnt = {};
    rels.forEach(r => cnt[r.tipo] = (cnt[r.tipo] || 0) + 1);
    const tipos = Object.keys(cnt).sort((a, b) => ORD.indexOf(a) - ORD.indexOf(b));
    const dom = tipos.slice().sort((a, b) => cnt[b] - cnt[a] || ORD.indexOf(a) - ORD.indexOf(b))[0];
    out.push({source: e.source, target: e.target, peso: rels.reduce((a, r) => a + pesoRelacao(r), 0), rels, tipos, dom, apenasHip: rels.every(r => r.confianca === 'hipotese')});
  }
  return out;
}
function hops(arestas, origem){
  const adj = new Map();
  arestas.forEach(e => {
    const s = e.source.id ?? e.source, t = e.target.id ?? e.target;
    if(!adj.has(s)) adj.set(s, []); if(!adj.has(t)) adj.set(t, []);
    adj.get(s).push(t); adj.get(t).push(s);
  });
  const dist = new Map([[origem, 0]]); const fila = [origem];
  while(fila.length){ const n = fila.shift(); (adj.get(n) || []).forEach(v => { if(!dist.has(v)){ dist.set(v, dist.get(n) + 1); fila.push(v); } }); }
  return dist;
}

// ------------------------------------------------------------------ render do grafo
function render(){
  const arestas = arestasVisiveis();
  const grau = new Map(nos.map(n => [n.id, 0])), forca = new Map(nos.map(n => [n.id, 0]));
  arestas.forEach(e => {
    const s = e.source.id ?? e.source, t = e.target.id ?? e.target;
    grau.set(s, (grau.get(s) || 0) + 1); grau.set(t, (grau.get(t) || 0) + 1);
    forca.set(s, (forca.get(s) || 0) + e.peso); forca.set(t, (forca.get(t) || 0) + e.peso);
  });
  nos.forEach(n => { n.grau = grau.get(n.id) || 0; n.forca = forca.get(n.id) || 0; });
  const dist = S.foco ? hops(arestas, S.foco) : null;
  const membros = S.inst ? new Set((D.instituicoes.find(i => i.id === S.inst) || {membros: []}).membros) : null;
  const raio = d => 5 + Math.min(d.forca, 9) * 1.5;

  const link = gLinks.selectAll('line').data(arestas, d => `${d.source.id ?? d.source}|${d.target.id ?? d.target}`);
  link.exit().remove();
  const linkAll = link.enter().append('line').attr('stroke-linecap', 'round').merge(link)
    .attr('stroke', d => D.tipos[d.dom].cor)
    .attr('stroke-width', d => Math.min(1 + d.peso * 1.4, 5))
    .attr('stroke-dasharray', d => d.apenasHip ? '3 4' : null)
    .attr('opacity', d => {
      if(dist){ const s = d.source.id ?? d.source, t = d.target.id ?? d.target; return (dist.get(s) <= 1 && dist.get(t) <= 1) ? .85 : .1; }
      if(membros){ const s = d.source.id ?? d.source, t = d.target.id ?? d.target; return (membros.has(s) && membros.has(t)) ? .85 : .12; }
      return .55;
    })
    .style('pointer-events', 'stroke')
    .on('mouseenter', (e, d) => mostrarTipAresta(e, d)).on('mousemove', moverTip).on('mouseleave', () => tip.style('opacity', 0));

  const node = gNodes.selectAll('g.no').data(nos, d => d.id);
  node.exit().remove();
  const nodeE = node.enter().append('g').attr('class', 'no').style('cursor', 'pointer');
  nodeE.append('circle'); nodeE.append('circle').attr('class', 'halo');
  nodeE.append('text').attr('class', 'node-label').attr('text-anchor', 'middle');
  const nodeAll = nodeE.merge(node);
  nodeAll.select('circle:not(.halo)')
    .attr('r', raio)
    .attr('fill', d => D.papeis[d.papel] ? D.papeis[d.papel].cor : D.papeis.outro.cor)
    .attr('stroke', d => d.id === S.foco ? '#14161A' : (d.grau === 0 ? '#8A8578' : 'none'))
    .attr('stroke-width', d => d.id === S.foco ? 2.5 : (d.grau === 0 ? 1 : 0))
    .attr('stroke-dasharray', d => (d.grau === 0 && d.id !== S.foco) ? '2 3' : null)
    .attr('opacity', d => {
      if(dist){ const h = dist.get(d.id); return h === undefined ? .12 : (h === 0 ? 1 : h === 1 ? .9 : h === 2 ? .4 : .12); }
      if(membros) return membros.has(d.id) ? .95 : .15;
      return d.grau === 0 ? .45 : .9;
    });
  nodeAll.select('circle.halo')
    .attr('r', d => raio(d) + 4).attr('fill', 'none')
    .attr('stroke', d => membros && membros.has(d.id) ? '#14161A' : 'none').attr('stroke-width', 1.2).attr('stroke-dasharray', '1 3');
  nodeAll.select('text')
    .text(d => d.nome)
    .attr('dy', d => raio(d) + 11)
    .attr('opacity', d => {
      if(dist){ const h = dist.get(d.id); return h === undefined ? .1 : (h <= 1 ? 1 : h === 2 ? .45 : .1); }
      if(membros) return membros.has(d.id) ? 1 : .15;
      return S.rotulos ? (d.forca >= 2 ? 1 : .7) : (d.forca >= 3 ? 1 : 0);
    });
  nodeAll.on('click', (e, d) => focar(d.id))
    .on('mouseenter', (e, d) => {
      const m = PESSOA[d.id].metricas || {};
      tip.style('opacity', 1).html(`<strong>${esc(d.nome)}</strong><span class="tt">${esc(D.papeis[d.papel]?.rotulo || '')} · ${d.grau} par(es) · força ${d.forca.toFixed(1)}${m.comunidade !== null && m.comunidade !== undefined ? ' · comunidade ' + m.comunidade : ''}</span>`);
      moverTip(e);
    })
    .on('mousemove', moverTip).on('mouseleave', () => tip.style('opacity', 0));
  nodeAll.call(d3.drag()
    .on('start', (e, d) => { if(!e.active) sim.alphaTarget(.25).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
    .on('end', (e, d) => { if(!e.active) sim.alphaTarget(0); if(d.id !== S.foco){ d.fx = null; d.fy = null; } }));

  gRings.selectAll('*').remove();
  if(S.foco){
    [1, 2].forEach(h => {
      gRings.append('circle').attr('class', 'ring').attr('cx', W / 2).attr('cy', H / 2).attr('r', h * 135);
      gRings.append('text').attr('class', 'ring-lbl').attr('x', W / 2).attr('y', H / 2 - h * 135 + 13).attr('text-anchor', 'middle').text(h === 1 ? 'CONTATO DIRETO' : 'SEGUNDO GRAU');
    });
  }

  if(sim) sim.stop();
  sim = d3.forceSimulation(nos)
    .force('link', d3.forceLink(arestas).id(d => d.id).distance(d => S.foco ? 90 : 105 - Math.min(d.peso, 3) * 14).strength(d => Math.min(.15 + d.peso * .14, .75)))
    .force('charge', d3.forceManyBody().strength(S.foco ? -260 : -330))
    .force('collide', d3.forceCollide().radius(d => 14 + Math.min(d.forca, 9) * 1.5))
    .force('center', S.foco ? null : d3.forceCenter(W / 2, H / 2))
    .force('x', S.foco ? null : d3.forceX(W / 2).strength(.045))
    .force('y', S.foco ? null : d3.forceY(H / 2).strength(.06));
  if(S.foco && dist){
    nos.forEach(n => { if(n.id === S.foco){ n.fx = W / 2; n.fy = H / 2; } else { n.fx = null; n.fy = null; } });
    sim.force('radial', d3.forceRadial(d => { const h = dist.get(d.id); return h === undefined ? 330 : h * 135; }, W / 2, H / 2).strength(d => dist.get(d.id) === undefined ? .35 : .85));
  } else {
    nos.forEach(n => { n.fx = null; n.fy = null; });
  }
  sim.alpha(0.9).on('tick', () => {
    linkAll.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    nodeAll.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  atualizarMetricasMini(arestas);
  if(S.foco) renderPessoa(S.foco, arestas, dist);
}

function moverTip(e){
  const rect = el('canvasWrap').getBoundingClientRect();
  const x = e.clientX - rect.left + 14, y = e.clientY - rect.top + 10;
  tip.style('left', Math.min(x, rect.width - 330) + 'px').style('top', y + 'px');
}
function mostrarTipAresta(e, d){
  const a = PESSOA[d.source.id ?? d.source], b = PESSOA[d.target.id ?? d.target];
  const rels = d.rels.map(r => {
    const fontes = (r.fontes || []).map(f => `<span class="src">${esc(citar(f))}${f.trecho ? ' — <em>“' + esc(f.trecho) + '”</em>' : ''}</span>`).join('');
    return `<div class="rel"><strong>${esc(D.tipos[r.tipo].rotulo)}</strong>${r.subtipo ? ' · ' + esc(r.subtipo) : ''}${r.periodo ? ' · ' + esc(r.periodo) : ''} <span class="tt" style="display:inline">${esc(r.confianca)}</span>${r.descricao ? '<br>' + esc(r.descricao) : ''}${fontes || '<span class="src">sem fonte — ' + esc(r.pendencia || 'pendência não registrada') + '</span>'}</div>`;
  }).join('');
  tip.style('opacity', 1).html(`<strong>${esc(a.nome)} — ${esc(b.nome)}</strong><span class="tt">peso ${d.peso.toFixed(2)} · ${d.rels.length} relação(ões)</span>${rels}`);
  moverTip(e);
}

// ------------------------------------------------------------------ painel de pessoa
function renderPessoa(id, arestas, dist){
  const p = PESSOA[id]; if(!p) return;
  const m = p.metricas || {};
  const viz = arestas.filter(e => (e.source.id ?? e.source) === id || (e.target.id ?? e.target) === id)
    .map(e => { const outro = (e.source.id ?? e.source) === id ? (e.target.id ?? e.target) : (e.source.id ?? e.source); return {id: outro, nome: PESSOA[outro]?.nome || outro, peso: e.peso, tipos: e.tipos, dom: e.dom}; })
    .sort((a, b) => b.peso - a.peso);
  const relsPorTipo = {};
  (D.arestas.filter(e => e.source === id || e.target === id)).forEach(e => e.relacoes.forEach(r => (relsPorTipo[r.tipo] = relsPorTipo[r.tipo] || []).push(r)));
  const inst = id => (D.instituicoes.find(i => i.id === id) || {}).nome || id;
  const saltos = Object.entries(m.saltos || {}).filter(([, v]) => v !== null && v !== undefined).map(([o, v]) => `${PESSOA[o]?.nome || o}: ${v}`).join(' · ');
  let html = `<div class="painel">
    <h3>${esc(p.nome)}</h3>
    <div class="papel">${esc(D.papeis[p.papel]?.rotulo || '')}${p.atribuicao ? ' · ' + esc(p.atribuicao) : ''} <span class="tag ${esc(p.status)}">${esc(p.status)}</span></div>`;
  if(p.pendencia) html += `<div class="viz pend"><em>Pendência:</em> ${esc(p.pendencia)}</div>`;
  (p.depoimentos || []).forEach(d => html += `<div class="viz ${d.existe_escola === false ? 'nega' : ''}"><em>Sobre a Escola do Recife (${d.existe_escola === true ? 'afirma' : d.existe_escola === false ? 'nega' : 'indefinido'}${d.data_depoimento ? ', ' + esc(d.data_depoimento) : ''}):</em> ${esc(d.argumento)}<span class="tp" style="display:block;margin-top:3px">${esc(citar(d.fonte))}</span></div>`);
  html += `<div class="bloco"><dl>
    ${p.nome_completo && p.nome_completo !== p.nome ? `<dt>Nome completo</dt><dd>${esc(p.nome_completo)}</dd>` : ''}
    ${(p.nascimento || p.morte) ? `<dt>Datas</dt><dd>${p.nascimento || '?'} – ${p.morte || ''}</dd>` : ''}
    ${p.local_nascimento ? `<dt>Nascimento</dt><dd>${esc(p.local_nascimento)}</dd>` : ''}
    ${p.titulo_epoca ? `<dt>Título à época</dt><dd>${esc(p.titulo_epoca)}</dd>` : ''}
    ${p.aliases && p.aliases.length ? `<dt>Variantes</dt><dd>${p.aliases.map(esc).join(' · ')}</dd>` : ''}
    <dt>Rede</dt><dd>${m.grau ?? 0} par(es) · força ${fmt(m.forca, 1)} · intermediação ${fmt(m.intermediacao, 3)}${m.comunidade !== null && m.comunidade !== undefined ? ' · comunidade ' + m.comunidade : ''}</dd>
    ${saltos ? `<dt>Saltos até</dt><dd>${esc(saltos)}</dd>` : ''}
  </dl></div>`;
  if(p.notas) html += `<div class="bloco" style="font-size:12.5px;color:#33363B">${esc(p.notas)}</div>`;
  if((p.formacao || []).length) html += `<div class="bloco"><h2>Formação</h2><ul class="timeline">${p.formacao.map(f => `<li><span class="ano">${f.ano_inicio || ''}${(f.ano_inicio || f.ano_conclusao) ? '–' : ''}${f.ano_conclusao || ''}</span><span>${esc(f.curso || 'Formação')} — ${esc(inst(f.instituicao))}</span></li>`).join('')}</ul></div>`;
  if((p.atuacao || []).length) html += `<div class="bloco"><h2>Atuação</h2><ul class="timeline">${p.atuacao.map(a => `<li><span class="ano">${esc(a.periodo || '')}</span><span>${esc(a.papel || 'atuação')} — ${esc(inst(a.nome))}</span></li>`).join('')}</ul></div>`;
  html += `<div class="bloco"><h2>Vizinhança na rede visível</h2><ul class="viz-list">${viz.length ? viz.map(v => `<li><span class="bar" style="width:${Math.max(8, v.peso * 16)}px;background:${D.tipos[v.dom].cor}"></span><span class="nm" data-id="${esc(v.id)}">${esc(v.nome)}<br><span class="tp">${v.tipos.map(t => D.tipos[t].rotulo.toLowerCase()).join(' + ')}</span></span><span class="frc">${v.peso.toFixed(1)}</span></li>`).join('') : '<li style="color:var(--graphite)">Sem vínculos documentados na seleção atual. A ausência é registro, não omissão.</li>'}</ul>${dist ? `<div class="nota">${[...dist.values()].filter(h => h === 2).length} figura(s) a dois saltos.</div>` : ''}</div>`;
  html += `<div class="bloco"><h2>Relações e fontes</h2>`;
  ORD.forEach(t => {
    const rels = relsPorTipo[t]; if(!rels) return;
    html += `<div style="margin:8px 0 4px;font-size:12.5px;font-weight:600;color:${D.tipos[t].cor}">${esc(D.tipos[t].rotulo)}</div><ul class="src-list">`;
    rels.forEach(r => {
      const outro = r.origem === id ? r.destino : r.origem;
      const seta = r.simetrico ? '↔' : (r.origem === id ? '→' : '←');
      html += `<li>${seta} <a data-id="${esc(outro)}" style="cursor:pointer">${esc(PESSOA[outro]?.nome || outro)}</a>${r.periodo ? ' · ' + esc(r.periodo) : ''} <span class="tag ${r.confianca === 'hipotese' ? 'hip' : ''}">${esc(r.confianca)}</span>${r.descricao ? '<br>' + esc(r.descricao) : ''}${(r.fontes || []).map(f => `<span class="cit">${esc(citar(f))}${f.trecho ? ' — <q>' + esc(f.trecho) + '</q>' : ''}</span>`).join('')}${r.pendencia ? `<span class="cit">pendência: ${esc(r.pendencia)}</span>` : ''}</li>`;
    });
    html += '</ul>';
  });
  html += `</div>`;
  if((p.eventos || []).length) html += `<div class="bloco"><h2>Linha do tempo</h2><ul class="timeline">${p.eventos.map(e => `<li><span class="ano">${e.ano}${e.fim && e.fim !== e.ano ? '–' + e.fim : ''}</span><span>${esc(e.rotulo)}</span></li>`).join('')}</ul></div>`;
  if((p.fontes || []).length) html += `<div class="bloco"><h2>Fontes da ficha</h2><div class="tp">${p.fontes.map(f => esc(citar({fonte: f}))).join(' · ')}</div></div>`;
  html += `</div>`;
  el('pessoaConteudo').innerHTML = html;
  el('pessoaConteudo').querySelectorAll('[data-id]').forEach(a => a.onclick = () => { S.foco = null; focar(a.dataset.id); });
}

// ------------------------------------------------------------------ controles
function montarControles(){
  const sel = el('seletor'), dl = el('nomes');
  D.pessoas.slice().sort((a, b) => a.nome.localeCompare(b.nome, 'pt')).forEach(p => {
    const o = document.createElement('option'); o.value = p.id; o.textContent = p.nome; sel.appendChild(o);
    const d = document.createElement('option'); d.value = p.nome; dl.appendChild(d);
    (p.aliases || []).forEach(a => { if(a.toLowerCase() !== p.nome.toLowerCase()){ const x = document.createElement('option'); x.value = a; x.label = p.nome; dl.appendChild(x); } });
  });
  sel.onchange = e => { S.foco = null; if(e.target.value) focar(e.target.value); else { history.replaceState(null, '', '#rede'); el('painelPessoa').classList.add('fechado'); render(); } };
  el('busca').addEventListener('change', e => {
    const q = e.target.value.trim().toLowerCase(); if(!q) return;
    const p = D.pessoas.find(p => p.nome.toLowerCase() === q || (p.aliases || []).some(a => a.toLowerCase() === q))
      || D.pessoas.find(p => p.nome.toLowerCase().includes(q) || (p.aliases || []).some(a => a.toLowerCase().includes(q)));
    if(p){ S.foco = null; focar(p.id); e.target.value = ''; }
  });
  el('limpar').onclick = () => { S.foco = null; S.inst = null; el('instituicao').value = ''; el('seletor').value = ''; history.replaceState(null, '', '#rede'); el('painelPessoa').classList.add('fechado'); render(); };
  el('reorganizar').onclick = () => { if(sim) sim.alpha(.9).restart(); };
  el('fecharPainel').onclick = () => { S.foco = null; el('seletor').value = ''; history.replaceState(null, '', '#rede'); el('painelPessoa').classList.add('fechado'); render(); };
  el('chkHip').onchange = e => { S.hip = e.target.checked; render(); };
  el('chkRotulos').onchange = e => { S.rotulos = e.target.checked; render(); };

  const filtros = el('filtros');
  ORD.forEach(t => {
    const n = D.arestas.reduce((a, e) => a + e.relacoes.filter(r => r.tipo === t).length, 0);
    const l = document.createElement('label'); l.className = 'chk';
    l.innerHTML = `<input type="checkbox" checked data-t="${t}"><span class="swatch" style="background:${D.tipos[t].cor}"></span><span>${esc(D.tipos[t].rotulo)}</span><span class="count">${n}</span>`;
    l.querySelector('input').onchange = e => { e.target.checked ? S.tipos.add(t) : S.tipos.delete(t); render(); };
    filtros.appendChild(l);
  });

  const inst = el('instituicao');
  D.instituicoes.filter(i => i.membros.length).forEach(i => { const o = document.createElement('option'); o.value = i.id; o.textContent = `${i.nome} (${i.membros.length})`; inst.appendChild(o); });
  inst.onchange = e => { S.inst = e.target.value || null; const i = D.instituicoes.find(x => x.id === S.inst); el('instNota').textContent = i ? `${i.tipo}${i.cidade ? ' · ' + i.cidade : ''}${i.periodo ? ' · ' + i.periodo : ''}: ` + i.membros.map(m => PESSOA[m]?.nome || m).join(', ') : ''; render(); };

  el('legendaPapeis').innerHTML = Object.entries(D.papeis).map(([k, v]) => `<label class="chk" style="cursor:default"><span class="dot" style="background:${v.cor}"></span><span>${esc(v.rotulo)}</span><span class="count">${D.pessoas.filter(p => (p.papel || 'outro') === k).length}</span></label>`).join('');
}

function atualizarMetricasMini(arestas){
  const conectados = nos.filter(n => n.grau > 0).length;
  const adj = new Map(nos.map(n => [n.id, []]));
  arestas.forEach(e => { const s = e.source.id ?? e.source, t = e.target.id ?? e.target; adj.get(s).push(t); adj.get(t).push(s); });
  const visto = new Set(); let comps = 0, maior = 0;
  nos.forEach(n => {
    if(visto.has(n.id) || !n.grau) return;
    comps++; let tam = 0; const fila = [n.id]; visto.add(n.id);
    while(fila.length){ const c = fila.pop(); tam++; adj.get(c).forEach(v => { if(!visto.has(v)){ visto.add(v); fila.push(v); } }); }
    maior = Math.max(maior, tam);
  });
  const top = nos.slice().sort((a, b) => b.forca - a.forca).slice(0, 3);
  const g = D.metricas_globais || {};
  el('metricasMini').innerHTML = `
    <div class="metric"><span>Pessoas</span><span>${nos.length}</span></div>
    <div class="metric"><span>Com ≥ 1 vínculo visível</span><span>${conectados}</span></div>
    <div class="metric"><span>Isoladas</span><span>${nos.length - conectados}</span></div>
    <div class="metric"><span>Pares conectados</span><span>${arestas.length}</span></div>
    <div class="metric"><span>Componentes</span><span>${comps}</span></div>
    <div class="metric"><span>Maior componente</span><span>${maior}</span></div>
    <div class="metric"><span>Modularidade (build)</span><span>${fmt(g.modularidade, 3)}</span></div>
    <div class="nota">Maior força acumulada:<br>${top.map(t => `${esc(t.nome)} (${t.forca.toFixed(1)})`).join('<br>')}</div>
    <div class="nota"><a href="#metricas">Relatório completo →</a></div>`;
}

function dimensionar(){
  const wrap = el('canvasWrap');
  W = wrap.clientWidth || 800; H = wrap.clientHeight || 600;
  svg.attr('viewBox', `0 0 ${W} ${H}`);
}

// ------------------------------------------------------------------ vista de métricas
function tabela(cab, linhas){
  return `<table class="tb"><thead><tr>${cab.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>${linhas.map(l => `<tr>${l.map((v, i) => typeof v === 'number' ? `<td class="num">${fmt(v)}</td>` : `<td>${v === null || v === undefined ? '—' : v}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}
const linkP = id => `<a data-id="${esc(id)}">${esc(PESSOA[id]?.nome || id)}</a>`;

function renderMetricas(){
  const g = D.metricas_globais, a = D.auditoria_confianca, c = D.convergencia_origens, pr = D.proselitismo, t = D.temporal, cob = D.cobertura, rk = D.ranking;
  let h = `<h2 class="titulo">Métricas da rede</h2><p class="lead">Cada bloco responde a um critério teórico do que constitui uma “escola” (Zein, Collins, Crane, Fleck, Bourdieu, Kris & Kurz). Nenhuma métrica decide sozinha; o resultado é dizer sob quais critérios o conjunto se qualifica e sob quais não. Gerado em ${esc(D.meta.gerado_em)}${D.meta.commit ? ', commit ' + esc(D.meta.commit) : ''}.</p>`;
  h += `<section><h3>Resumo</h3>${tabela(['Indicador', 'Valor'], [
    ['Pessoas na base', g.n_pessoas], ['Relações (linhas)', g.n_relacoes], ['Arestas (pares únicos)', g.n_arestas], ['Pessoas com ≥ 1 vínculo', g.n_conectados], ['Isoladas', g.n_isolados],
    ['Componentes (não triviais)', g.n_componentes], ['Maior componente', `${g.maior_componente} (${pct(g.proporcao_no_maior_componente)} da base)`], ['Densidade (conectados)', g.densidade_conectados],
    ['Coeficiente de agrupamento médio', g.agrupamento_medio], ['Transitividade', g.transitividade], ['Caminho médio (maior comp.)', g.caminho_medio_maior_componente], ['Diâmetro (maior comp.)', g.diametro_maior_componente],
    ['Modularidade (Louvain)', g.modularidade], ['Comunidades', g.n_comunidades], ['Fontes processadas / total', `${D.meta.n_fontes_processadas} / ${D.meta.n_fontes}`],
  ])}</section>`;
  h += `<section><h3>Comunidades</h3><div class="crit">Zein 3, 4 — identidade de grupo restrito · modularidade alta = agrupamento real; baixa = rede difusa</div>${tabela(['#', 'Tamanho', 'Papéis', 'Atribuições', 'Membros'], g.comunidades.map(cm => [cm.id, cm.tamanho, Object.entries(cm.papeis).map(([k, v]) => `${k}: ${v}`).join(', '), Object.entries(cm.atribuicoes).map(([k, v]) => `${k}: ${v}`).join(', '), cm.membros.map(linkP).join(', ')]))}</section>`;
  h += `<section><h3>Componentes</h3><div class="crit">Bourdieu — dissidência estruturante; pontes ausentes são achado, não defeito</div>${tabela(['#', 'Tamanho', 'Papéis', 'Membros'], g.componentes.map(cm => [cm.id, cm.tamanho, Object.entries(cm.papeis).map(([k, v]) => `${k}: ${v}`).join(', '), cm.membros.map(linkP).join(', ')]))}${cob.isolados.length ? `<div class="nota">Isolados: ${cob.isolados.map(i => linkP(i.id)).join(', ')}.</div>` : ''}</section>`;
  h += `<section><h3>Centralidades</h3><div class="crit">Fleck — círculo esotérico vs. exotérico</div><div class="grid2">${[['grau', 'Grau'], ['forca', 'Força (grau ponderado)'], ['intermediacao', 'Intermediação'], ['proximidade', 'Proximidade'], ['autovetor', 'Autovetor']].map(([k, r]) => tabela([r, ''], rk[k].map(x => [linkP(x.id), x[k]]))).join('')}</div></section>`;
  h += `<section><h3>Por tipo de relação</h3><div class="crit">topologias semelhantes sustentam uma escola unificada; diferentes argumentam contra origem única</div>${tabela(['Tipo', 'Relações', 'Nós', 'Arestas', 'Comp.', 'Maior comp.', 'Densidade', 'Agrupamento', 'Caminho médio', 'Mais conectado'], Object.values(D.por_tipo).map(x => [x.rotulo, x.n_relacoes, x.n_nos, x.n_arestas, x.n_componentes, x.maior_componente, x.densidade, x.agrupamento_medio, x.caminho_medio_maior_componente, x.top_grau[0] ? `${linkP(x.top_grau[0].id)} (${x.top_grau[0].grau})` : '—']))}</section>`;
  h += `<section><h3>Auditoria de confiança</h3><div class="crit">Kris & Kurz — a narrativa mestre-discípulo como tópos</div>${tabela(['Tipo', 'Documentado', 'Tradição oral', 'Hipótese', 'Total', '% documentado'], [...Object.entries(a.por_tipo).map(([k, v]) => [D.tipos[k].rotulo, v.documentado, v.tradicao_oral, v.hipotese, v.total, pct(v.proporcao_documentado)]), ['<b>Total</b>', a.total.documentado, a.total.tradicao_oral, a.total.hipotese, a.total.total, pct(a.total.proporcao_documentado)]])}<div class="leitura">${esc(a.leitura)}</div></section>`;
  h += `<section><h3>Convergência de origens</h3><div class="crit">Zein 2 — origens comuns · a maioria dos caminhos passa por poucos nós?</div>${Object.keys(c.alcance).length ? tabela(['Origem', 'Grau', '1 salto', '2 saltos', '3 saltos', 'Alcançáveis', '% da rede conectada'], Object.entries(c.alcance).map(([id, v]) => [linkP(id), v.grau, v.saltos_1, v.saltos_2, v.saltos_3, v.alcancaveis, pct(v.proporcao_alcancavel)])) : ''}<div class="leitura">${esc(c.leitura)}</div></section>`;
  h += `<section><h3>Proselitismo</h3><div class="crit">Zein 5 — transmissão deliberada · direção das arestas de estudo e mestre-aprendiz</div>${pr.emissores.length ? tabela(['Emissor', 'Arestas de ensino emitidas'], pr.emissores.map(e => [linkP(e.id), e.saida])) : ''}<div class="leitura">${esc(pr.leitura)}</div></section>`;
  h += `<section><h3>Camada temporal</h3><div class="crit">o tempo é métrica sempre que existe · relações com período: ${t.cobertura.n_com_periodo} de ${t.cobertura.n_relacoes} (${pct(t.cobertura.proporcao_com_periodo)})</div>${t.decadas.length ? tabela(['Década', 'Rel. ativas', 'Nós', 'Arestas', 'Comp.', 'Rel. acumuladas', 'Nós acum.', 'Arestas acum.', 'Maior comp. acum.'], t.decadas.map(d => [d.rotulo, d.fatia.n_relacoes, d.fatia.n_nos, d.fatia.n_arestas, d.fatia.n_componentes, d.acumulado.n_relacoes, d.acumulado.n_nos, d.acumulado.n_arestas, d.acumulado.maior_componente])) : '<p class="nota">Nenhuma relação datada ainda.</p>'}<div class="nota">Fatia = relações ativas na década; acumulado = iniciadas até o fim da década (a rede “nascendo”). Períodos abertos valem apenas pelo ano documentado.</div></section>`;
  h += `<section><h3>Depoimentos e cobertura</h3>${tabela(['Indicador', 'Valor'], [['Posições sobre a Escola do Recife', `${D.depoimentos_resumo.n} (${D.depoimentos_resumo.afirmam} afirmam · ${D.depoimentos_resumo.negam} negam · ${D.depoimentos_resumo.indefinidos} indefinidas)`], ['Pendências abertas', cob.n_pendencias], ['Fontes não processadas', cob.fontes.nao_processadas.length], ['Status das relações', Object.entries(cob.status_relacoes).map(([k, v]) => `${k}: ${v}`).join(', ')]])}${cob.pendencias.length ? tabela(['Entidade', 'Quem / o quê', 'Pendência'], cob.pendencias.map(p => [p.entidade, p.entidade === 'pessoa' ? linkP(p.id) : esc(p.nome), esc(p.pendencia)])) : ''}</section>`;
  h += `<section><h3>Método</h3><p class="nota">${esc(D.meta.formula)}. Distância para caminhos ponderados = 1 / peso. Comunidades: Louvain com peso, seed ${D.meta.seed_comunidades}. Intermediação e proximidade ponderadas pela distância; autovetor no maior componente. Relações e arestas são níveis distintos: contagens por tipo usam relações; métricas de rede usam arestas.</p></section>`;
  el('viewMetricas').innerHTML = h;
  el('viewMetricas').querySelectorAll('a[data-id]').forEach(x => x.onclick = () => { location.hash = 'pessoa=' + encodeURIComponent(x.dataset.id); });
}

function renderSobre(){
  el('viewSobre').innerHTML = `<h2 class="titulo">Sobre o GAP</h2>
  <p class="lead">Genealogia da Arquitetura Pernambucana — um instrumento de pesquisa que mapeia a rede de pessoas que fizeram a arquitetura de Pernambuco no último século como um grafo de relações documentadas: parentesco, mestre–aprendiz, estudo, trabalho, sociedade, dissidência e coautoria.</p>
  <section><h3>A pergunta</h3><p>Existiu uma “Escola do Recife”, no sentido em que a historiografia fala de “Escola Paulista” e “Escola Carioca”? Alguns situam a origem em Luiz Nunes e sua equipe na DAC/PE (1934–1937); outros nos primeiros professores do curso da EBAP após 1949 — Mário Russo, Delfim Amorim, Acácio Gil Borsoi, Heitor Maia Neto — e seus discípulos. Há quem negue: sem comunicação de ideias nem união profissional, não houve escola. O projeto não pressupõe resposta.</p></section>
  <section><h3>Como se mede</h3><ul>
    <li><b>Identidade de grupo</b> (Zein) → detecção de comunidades e modularidade.</li>
    <li><b>Origens comuns</b> → convergência dos caminhos para poucos nós de origem.</li>
    <li><b>Proselitismo</b> → direção e concentração das arestas de ensino.</li>
    <li><b>Coesão informal</b> (Crane, colégio invisível) → agrupamento e caminho médio.</li>
    <li><b>Núcleo e periferia</b> (Fleck) → centralidades de intermediação e grau.</li>
    <li><b>Dissidência estruturante</b> (Bourdieu) → componentes separados e pontes ausentes.</li>
    <li><b>Tópos narrativo</b> (Kris & Kurz) → distribuição da confiança por tipo de relação.</li>
  </ul></section>
  <section><h3>Regras da base</h3><ul>
    <li>Nenhuma relação é inventada: co-menção não é relação. Em dúvida, hipótese com pendência — ou nada.</li>
    <li>Toda aresta tem proveniência (fonte, página, trecho) ou está visivelmente marcada como carente dela.</li>
    <li>Confiança da evidência (documentado · tradição oral · hipótese) é distinta do status de revisão editorial.</li>
    <li>Pesos são computados, nunca atribuídos à mão: w(confiança) × (1 + 0,5 × (n.º de fontes independentes − 1)).</li>
    <li>Lacunas aparecem: nós isolados, pontes ausentes e pendências são resultados.</li>
    <li>Os dados vivem em um repositório Git; cada estado tem um commit citável.</li>
  </ul></section>
  <section><h3>Contribuir</h3><p>A base cresce por triagem de fontes (teses, artigos, anais, acervos). Propostas externas entram na mesma fila de revisão e exigem aprovação editorial. Exportações completas (CSV, GEXF, GraphML, relatório de métricas) são regeneradas a cada build.</p></section>`;
}

main();
