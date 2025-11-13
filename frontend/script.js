let pricing = null;
let pieChart = null;

async function fetchPricing(){
  try{
    const r = await fetch('/data/pricing.json');
    pricing = await r.json();
  }catch(e){
    console.error('Failed loading pricing.json', e);
    pricing = null;
  }
}

function createResourceRow(id){
  const wrapper = document.createElement('div');
  wrapper.className = 'resource-row';
  wrapper.dataset.id = id;

  // Type select
  const typeSel = document.createElement('select');
  typeSel.className = 'type small';
  ['vm','storage','sqldb'].forEach(t => {
    const opt = document.createElement('option')
    opt.value = t; opt.text = t.toUpperCase();
    typeSel.appendChild(opt);
  });

  const skuSel = document.createElement('select');
  skuSel.className = 'sku small';

  const regionSel = document.createElement('select');
  regionSel.className = 'region small';
  Object.keys((pricing && pricing.region_multipliers) || {eastus:1}).forEach(r => {
    const opt = document.createElement('option'); opt.value = r; opt.text = r;
    regionSel.appendChild(opt);
  });

  const qty = document.createElement('input');
  qty.type = 'number'; qty.min = 1; qty.value = 1; qty.className = 'small qty';

  const hours = document.createElement('input');
  hours.type = 'number'; hours.min = 1; hours.value = 720; hours.className = 'small hours';

  const removeBtn = document.createElement('button');
  removeBtn.textContent = 'Remove'; removeBtn.className = 'btn';
  removeBtn.onclick = () => wrapper.remove();

  // update sku options when type changes
  typeSel.onchange = () => populateSku(typeSel.value, skuSel);

  populateSku('vm', skuSel);

  wrapper.appendChild(typeSel);
  wrapper.appendChild(skuSel);
  wrapper.appendChild(regionSel);
  wrapper.appendChild(qty);
  wrapper.appendChild(hours);
  wrapper.appendChild(removeBtn);

  return wrapper;
}

function populateSku(type, skuSel){
  skuSel.innerHTML = '';
  if(!pricing) return;
  const list = pricing[type] || {};
  Object.keys(list).forEach(k => {
    const opt = document.createElement('option'); opt.value = k;
    opt.text = list[k].display || k;
    skuSel.appendChild(opt);
  });
}

document.getElementById('add-row').addEventListener('click', () => {
  const list = document.getElementById('resource-list');
  const id = Date.now();
  const row = createResourceRow(id);
  list.appendChild(row);
});

document.getElementById('calculate').addEventListener('click', async () => {
  const rows = [...document.querySelectorAll('.resource-row')];
  const resources = rows.map(r => {
    return {
      type: r.querySelector('.type').value,
      sku: r.querySelector('.sku').value,
      region: r.querySelector('.region').value,
      quantity: Number(r.querySelector('.qty').value || 1),
      hours_per_month: Number(r.querySelector('.hours').value || 720)
    };
  });

  // POST to backend
  const resp = await fetch('/api/calc', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({resources})
  });
  const data = await resp.json();
  renderResults(data);
});

function renderResults(data){
  const tbody = document.querySelector('#results-table tbody');
  tbody.innerHTML = '';
  (data.items || []).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${item.type}</td>
                    <td>${item.sku}</td>
                    <td>${item.region}</td>
                    <td>${item.quantity}</td>
                    <td>${item.hours_per_month}</td>
                    <td>${formatCurrency(item.cost)}</td>`;
    tbody.appendChild(tr);
  });

  // Pie chart
  const ctx = document.getElementById('pieChart').getContext('2d');
  const labels = data.items.map(i => `${i.sku} (${i.type})`);
  const values = data.items.map(i => Number(i.cost.toFixed(2)));
  if(pieChart) pieChart.destroy();
  pieChart = new Chart(ctx, {
    type: 'pie',
    data: {labels, datasets:[{data: values}]},
    options: {plugins:{legend:{position:'bottom'}}}
  });

  // AI summary (if present)
  const aiBox = document.getElementById('ai-text');
  if(data.ai_summary){
    aiBox.textContent = data.ai_summary;
  } else {
    aiBox.textContent = 'No AI summary available. If you configured Azure OpenAI keys, the backend will generate suggestions.';
  }
}

function formatCurrency(v){
  // assume USD for demo; you can change to INR symbol if you like
  return '$' + Number(v).toFixed(2);
}

// init
(async () => {
  await fetchPricing();
  // add default row
  document.getElementById('add-row').click();
})();
