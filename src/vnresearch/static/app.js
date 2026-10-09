const $ = (id) => document.getElementById(id);
let activeJob = null;
let currentReportSources = {};
let providerSessionId = null;
let providerCapabilities = { llm_configured: false, jev_configured: false };

// Thiết lập ngày chốt mặc định là hôm nay (Asia/Bangkok)
$('asOf').value = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Bangkok', year: 'numeric', month: '2-digit', day: '2-digit'
}).format(new Date());

const phases = {
  queued: 'Đang xếp hàng',
  starting: 'Khởi tạo tác vụ',
  financial: 'Đọc số liệu BCTC và tính chỉ số',
  market: 'Dữ liệu giá & giao dịch',
  macro: 'Tổng quan vĩ mô',
  sector: 'So sánh trung vị ngành ICB',
  news: 'Khai phá tin tức & bằng chứng',
  valuation: 'Mô hình định giá & kịch bản',
  report: 'Tạo báo cáo PDF',
  completed: 'Đã hoàn tất báo cáo',
  failed: 'Tác vụ thất bại',
  interrupted: 'Tác vụ bị gián đoạn'
};

function headers(extra = {}, sessionId = providerSessionId) {
  const key = $('apiKey').value.trim();
  const result = { ...(key ? { 'X-API-Key': key } : {}), ...extra };
  if (sessionId) result['X-Provider-Session'] = sessionId;
  return result;
}

async function api(url, options = {}) {
  const { providerSessionHeader = providerSessionId, ...requestOptions } = options;
  const response = await fetch(url, {
    ...requestOptions,
    headers: headers(requestOptions.headers || {}, providerSessionHeader)
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
  }
  return response;
}

function textElement(tag, text, className = '') {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function applyProviderCapabilities() {
  const demo = $('mode').value === 'demo';
  $('useAi').checked = !demo && !!providerCapabilities.llm_configured;
  $('useJev').checked = !demo && !!providerCapabilities.jev_configured;
  $('useAi').disabled = demo || !providerCapabilities.llm_configured;
  $('useJev').disabled = demo || !providerCapabilities.jev_configured;
}

async function refreshProviderCapabilities() {
  try {
    const response = await api('/api/capabilities');
    providerCapabilities = await response.json();
  } catch {
    providerCapabilities = { llm_configured: false, jev_configured: false };
  }
  applyProviderCapabilities();
}

async function saveProviderConfig() {
  const providers = {};
  for (const [kind, prefix] of [['llm', 'llm'], ['jev', 'jev']]) {
    const apiKey = $(`${prefix}ApiKey`).value.trim();
    if (!apiKey) continue;
    const baseUrl = $(`${prefix}BaseUrl`).value.trim();
    const model = $(`${prefix}Model`).value.trim();
    if (!baseUrl || !model) throw new Error(`${kind.toUpperCase()}: nhập Base URL và model cùng API key.`);
    providers[kind] = { base_url: baseUrl, api_key: apiKey, model };
  }
  if (!Object.keys(providers).length) {
    $('providerConfigStatus').textContent = 'Nhập ít nhất một API key; cấu hình backend hiện có vẫn được giữ nguyên.';
    await refreshProviderCapabilities();
    return;
  }

  const response = await api('/api/provider-sessions', {
    method: 'POST',
    providerSessionHeader: null,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ providers })
  });
  const saved = await response.json();
  const previousSessionId = providerSessionId;
  providerSessionId = saved.id;
  for (const prefix of ['llm', 'jev']) $(`${prefix}ApiKey`).value = '';
  providerCapabilities = {
    llm_configured: !!saved.llm_configured,
    jev_configured: !!saved.jev_configured
  };
  applyProviderCapabilities();
  const active = [
    saved.llm_configured ? `LLM (${saved.llm_model})` : null,
    saved.jev_configured ? `Jev (${saved.jev_model})` : null
  ].filter(Boolean).join(' · ');
  $('providerConfigStatus').textContent = `Đã lưu ${active} trong RAM máy chủ; hết hạn sau ${Math.round(saved.expires_in_seconds / 60)} phút. Khóa đã xóa khỏi ô nhập.`;
  if (previousSessionId && previousSessionId !== providerSessionId) {
    api(`/api/provider-sessions/${encodeURIComponent(previousSessionId)}`, {
      method: 'DELETE', providerSessionHeader: previousSessionId
    }).catch(() => {});
  }
}

$('saveProviderConfig').addEventListener('click', async () => {
  $('providerConfigStatus').textContent = 'Đang lưu kết nối an toàn trong phiên máy chủ…';
  try {
    await saveProviderConfig();
  } catch (error) {
    $('providerConfigStatus').textContent = error.message;
  }
});

// Xử lý modal hiển thị nguồn
function showSourceModal(sourceId) {
  const source = currentReportSources[sourceId];
  if (!source) return;
  $('modalSourceTitle').textContent = `[${source.id}] ${source.title || 'Nguồn bằng chứng'}`;
  const body = $('modalSourceBody');
  body.replaceChildren();

  const addRow = (label, value, isLink = false) => {
    if (!value) return;
    const row = document.createElement('div');
    row.className = 'modal-row';
    const strong = document.createElement('strong');
    strong.textContent = label + ': ';
    row.appendChild(strong);
    if (isLink && (value.startsWith('http://') || value.startsWith('https://'))) {
      const a = document.createElement('a');
      a.href = value;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = value + ' ↗';
      row.appendChild(a);
    } else {
      const span = document.createElement('span');
      span.textContent = value;
      row.appendChild(span);
    }
    body.appendChild(row);
  };

  addRow('Loại nguồn', source.kind);
  addRow('Tình trạng xác minh', source.verification_status);
  addRow('Phạm vi báo cáo', source.report_basis);
  addRow('Kỳ dữ liệu', source.period || source.period_type);
  addRow('Ngày công bố', source.published_on || (source.published_at ? source.published_at.substring(0, 10) : 'Chưa có'));
  addRow('Thời điểm thu thập', source.retrieved_at);
  addRow('Đường dẫn URL', source.url, true);
  if (source.note) addRow('Ghi chú', source.note);
  if (source.sha256) addRow('Mã băm SHA-256', source.sha256);

  $('sourceModal').classList.remove('hidden');
}

$('modalClose').addEventListener('click', () => $('sourceModal').classList.add('hidden'));
$('sourceModal').addEventListener('click', (e) => {
  if (e.target === $('sourceModal')) $('sourceModal').classList.add('hidden');
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') $('sourceModal').classList.add('hidden');
});

// Vẽ biểu đồ SVG Doanh thu và Lợi nhuận
function renderRevenueChart(report) {
  const container = $('revenueChartSvg');
  container.replaceChildren();
  const years = report.financial_years || [];
  const data = years
    .map(y => ({
      year: y.year,
      rev: y.facts.revenue != null ? y.facts.revenue / 1e9 : null,
      ni: y.facts.net_income != null ? y.facts.net_income / 1e9 : null
    }))
    .filter(d => d.rev != null && d.rev > 0);

  if (data.length < 2) {
    container.textContent = 'Chưa đủ dữ liệu tối thiểu 2 năm để vẽ biểu đồ.';
    return;
  }

  const maxVal = Math.max(...data.flatMap(d => [Math.abs(d.rev || 0), Math.abs(d.ni || 0)])) || 1;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 480 270');
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');

  const slotW = 420 / data.length;
  const barW = Math.min(24, slotW * 0.36);
  const baseline = 145;
  const scale = 90 / maxVal;

  const zeroLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
  zeroLine.setAttribute('x1', '25');
  zeroLine.setAttribute('x2', '470');
  zeroLine.setAttribute('y1', baseline);
  zeroLine.setAttribute('y2', baseline);
  zeroLine.setAttribute('stroke', '#94a3b8');
  zeroLine.setAttribute('stroke-width', '1');
  svg.appendChild(zeroLine);

  data.forEach((d, i) => {
    const xBase = 35 + i * slotW;
    const revH = (d.rev * scale);
    const revY = baseline - revH;

    // Doanh thu (Teal)
    const rectRev = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectRev.setAttribute('x', xBase);
    rectRev.setAttribute('y', revY);
    rectRev.setAttribute('width', barW);
    rectRev.setAttribute('height', revH);
    rectRev.setAttribute('fill', '#008F86');
    rectRev.setAttribute('rx', '2');
    svg.appendChild(rectRev);

    const txtRev = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txtRev.setAttribute('x', xBase + barW / 2);
    txtRev.setAttribute('y', revY - 5);
    txtRev.setAttribute('text-anchor', 'middle');
    txtRev.setAttribute('font-size', '10');
    txtRev.setAttribute('fill', '#132B45');
    txtRev.setAttribute('font-weight', '600');
    txtRev.textContent = Math.round(d.rev).toLocaleString('vi-VN');
    svg.appendChild(txtRev);

    // LNST (Navy)
    if (d.ni != null) {
      const xNi = xBase + barW + 3;
      const niH = Math.max(1, Math.abs(d.ni) * scale);
      const isLoss = d.ni < 0;
      const niY = isLoss ? baseline : baseline - niH;
      const rectNi = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rectNi.setAttribute('x', xNi);
      rectNi.setAttribute('y', niY);
      rectNi.setAttribute('width', barW);
      rectNi.setAttribute('height', niH);
      rectNi.setAttribute('fill', isLoss ? '#DC2626' : '#132B45');
      rectNi.setAttribute('rx', '2');
      svg.appendChild(rectNi);

      const txtNi = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      txtNi.setAttribute('x', xNi + barW / 2);
      txtNi.setAttribute('y', isLoss ? niY + niH + 12 : niY - 5);
      txtNi.setAttribute('text-anchor', 'middle');
      txtNi.setAttribute('font-size', '9');
      txtNi.setAttribute('fill', isLoss ? '#B91C1C' : '#64748B');
      txtNi.textContent = Math.round(d.ni).toLocaleString('vi-VN');
      svg.appendChild(txtNi);
    }

    // Năm
    const txtYear = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txtYear.setAttribute('x', xBase + barW);
    txtYear.setAttribute('y', 262);
    txtYear.setAttribute('text-anchor', 'middle');
    txtYear.setAttribute('font-size', '11');
    txtYear.setAttribute('fill', '#64748B');
    txtYear.textContent = d.year;
    svg.appendChild(txtYear);
  });

  // Chú thích Legend
  const legendRev = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  legendRev.setAttribute('x', '260'); legendRev.setAttribute('y', '10');
  legendRev.setAttribute('width', '10'); legendRev.setAttribute('height', '10');
  legendRev.setAttribute('fill', '#008F86');
  svg.appendChild(legendRev);

  const legendRevTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  legendRevTxt.setAttribute('x', '276'); legendRevTxt.setAttribute('y', '19');
  legendRevTxt.setAttribute('font-size', '10'); legendRevTxt.setAttribute('fill', '#132B45');
  legendRevTxt.textContent = 'Doanh thu';
  svg.appendChild(legendRevTxt);

  const legendNi = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  legendNi.setAttribute('x', '360'); legendNi.setAttribute('y', '10');
  legendNi.setAttribute('width', '10'); legendNi.setAttribute('height', '10');
  legendNi.setAttribute('fill', '#132B45');
  svg.appendChild(legendNi);

  const legendNiTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  legendNiTxt.setAttribute('x', '376'); legendNiTxt.setAttribute('y', '19');
  legendNiTxt.setAttribute('font-size', '10'); legendNiTxt.setAttribute('fill', '#132B45');
  legendNiTxt.textContent = 'LNST';
  svg.appendChild(legendNiTxt);

  const legendLoss = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  legendLoss.setAttribute('x', '425'); legendLoss.setAttribute('y', '10');
  legendLoss.setAttribute('width', '10'); legendLoss.setAttribute('height', '10');
  legendLoss.setAttribute('fill', '#DC2626');
  svg.appendChild(legendLoss);

  const legendLossTxt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  legendLossTxt.setAttribute('x', '440'); legendLossTxt.setAttribute('y', '19');
  legendLossTxt.setAttribute('font-size', '10'); legendLossTxt.setAttribute('fill', '#B91C1C');
  legendLossTxt.textContent = 'Lỗ';
  svg.appendChild(legendLossTxt);

  container.appendChild(svg);
}

// Vẽ biểu đồ SVG so sánh ngành
function renderSectorBenchmarkChart(report) {
  const container = $('sectorBenchmarkSvg');
  container.replaceChildren();
  const sector = report.sections.sector;
  if (!sector || !sector.rows || !sector.rows.length) {
    container.textContent = 'Chưa có dữ liệu so sánh ngành.';
    return;
  }

  const tickerRow = sector.rows.find(r => r['Mã'] === report.ticker) || sector.rows[0];
  const medianRow = sector.rows.find(r => String(r['Mã']).toUpperCase().includes('TRUNG VỊ'));

  if (!tickerRow || !medianRow) {
    container.textContent = 'Chưa đủ mẫu doanh nghiệp và trung vị ngành để đối sánh.';
    return;
  }

  const metrics = [
    { name: 'ROE', key: 'ROE', unit: '%' },
    { name: 'ROA', key: 'ROA', unit: '%' },
    { name: 'Biên LNST', key: 'Biên LNST', unit: '%' },
  ].filter(m => typeof tickerRow[m.key] === 'number' && typeof medianRow[m.key] === 'number');

  if (!metrics.length) {
    container.textContent = 'Chưa có các chỉ tiêu sinh lời đồng nhất để đối sánh.';
    return;
  }

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 480 200');
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');

  const maxVal = Math.max(...metrics.flatMap(m => [tickerRow[m.key], medianRow[m.key]])) || 0.1;
  const slotW = 420 / metrics.length;
  const barW = Math.min(28, slotW * 0.35);

  metrics.forEach((m, i) => {
    const xBase = 40 + i * slotW;
    const vTicker = tickerRow[m.key];
    const vMedian = medianRow[m.key];

    const hTicker = Math.max(3, (Math.max(0, vTicker) / maxVal) * 120);
    const yTicker = 160 - hTicker;
    const rectTicker = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectTicker.setAttribute('x', xBase); rectTicker.setAttribute('y', yTicker);
    rectTicker.setAttribute('width', barW); rectTicker.setAttribute('height', hTicker);
    rectTicker.setAttribute('fill', '#008F86'); rectTicker.setAttribute('rx', '2');
    svg.appendChild(rectTicker);

    const txtT = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txtT.setAttribute('x', xBase + barW / 2); txtT.setAttribute('y', yTicker - 5);
    txtT.setAttribute('text-anchor', 'middle'); txtT.setAttribute('font-size', '10');
    txtT.setAttribute('fill', '#008F86'); txtT.setAttribute('font-weight', '700');
    txtT.textContent = (vTicker * 100).toFixed(1) + '%';
    svg.appendChild(txtT);

    const xMedian = xBase + barW + 4;
    const hMedian = Math.max(3, (Math.max(0, vMedian) / maxVal) * 120);
    const yMedian = 160 - hMedian;
    const rectMedian = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rectMedian.setAttribute('x', xMedian); rectMedian.setAttribute('y', yMedian);
    rectMedian.setAttribute('width', barW); rectMedian.setAttribute('height', hMedian);
    rectMedian.setAttribute('fill', '#94A3B8'); rectMedian.setAttribute('rx', '2');
    svg.appendChild(rectMedian);

    const txtM = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txtM.setAttribute('x', xMedian + barW / 2); txtM.setAttribute('y', yMedian - 5);
    txtM.setAttribute('text-anchor', 'middle'); txtM.setAttribute('font-size', '10');
    txtM.setAttribute('fill', '#64748B');
    txtM.textContent = (vMedian * 100).toFixed(1) + '%';
    svg.appendChild(txtM);

    const txtLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    txtLabel.setAttribute('x', xBase + barW); txtLabel.setAttribute('y', 178);
    txtLabel.setAttribute('text-anchor', 'middle'); txtLabel.setAttribute('font-size', '11');
    txtLabel.setAttribute('fill', '#132B45'); txtLabel.setAttribute('font-weight', '600');
    txtLabel.textContent = m.name;
    svg.appendChild(txtLabel);
  });

  // Chú thích
  const l1 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  l1.setAttribute('x', '220'); l1.setAttribute('y', '10'); l1.setAttribute('width', '10'); l1.setAttribute('height', '10'); l1.setAttribute('fill', '#008F86');
  svg.appendChild(l1);
  const l1t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  l1t.setAttribute('x', '236'); l1t.setAttribute('y', '19'); l1t.setAttribute('font-size', '10'); l1t.setAttribute('fill', '#132B45');
  l1t.textContent = report.ticker;
  svg.appendChild(l1t);

  const l2 = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  l2.setAttribute('x', '320'); l2.setAttribute('y', '10'); l2.setAttribute('width', '10'); l2.setAttribute('height', '10'); l2.setAttribute('fill', '#94A3B8');
  svg.appendChild(l2);
  const l2t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
  l2t.setAttribute('x', '336'); l2t.setAttribute('y', '19'); l2t.setAttribute('font-size', '10'); l2t.setAttribute('fill', '#132B45');
  l2t.textContent = 'Trung vị ngành';
  svg.appendChild(l2t);

  container.appendChild(svg);
}

// Hàm render toàn bộ kết quả lên giao diện
function render(report, job = {}) {
  $('welcome').classList.add('hidden');
  $('result').classList.remove('hidden');

  // Lưu trữ sources để xem modal
  currentReportSources = {};
  (report.sources || []).forEach(s => { currentReportSources[s.id] = s; });

  // Thông tin tiêu đề
  $('companyName').textContent = `${report.ticker} · ${report.company_name}`;
  $('resultMeta').textContent = `CHẾ ĐỘ: ${report.request.mode.toUpperCase()} · NGÀY CHỐT: ${report.request.as_of} · TRẠNG THÁI: ${report.status.toUpperCase()}`;
  $('decision').textContent = report.decision;

  // Cập nhật thẻ KPI
  $('kpiJobStatus').textContent = (job.status || 'completed').toUpperCase();
  $('kpiJobStatus').className = 'kpi-badge ' + (job.status === 'failed' ? 'badge-danger' : 'badge-success');

  const mode = report.request.mode;
  $('kpiMode').textContent = mode.toUpperCase();
  $('kpiMode').className = 'kpi-badge ' + (mode === 'live' ? 'badge-success' : mode === 'snapshot' ? 'badge-info' : 'badge-warning');

  // Đánh giá chất lượng dữ liệu
  const qualityBadge = $('kpiDataQuality');
  if (mode === 'demo') {
    qualityBadge.textContent = 'DỮ LIỆU MINH HỌA (DEMO)';
    qualityBadge.className = 'kpi-badge badge-warning';
  } else if (report.status === 'complete' && (!report.issues || !report.issues.length)) {
    qualityBadge.textContent = 'ĐÃ XÁC MINH NGUỒN GỐC';
    qualityBadge.className = 'kpi-badge badge-success';
  } else if (report.status === 'partial') {
    qualityBadge.textContent = 'DỮ LIỆU TỪNG PHẦN (PARTIAL)';
    qualityBadge.className = 'kpi-badge badge-warning';
  } else {
    qualityBadge.textContent = 'CẦN KIỂM CHỨNG BỔ SUNG';
    qualityBadge.className = 'kpi-badge badge-info';
  }

  // Khuyến nghị sơ bộ
  const decisionBadge = $('kpiDecisionBadge');
  const decUpper = (report.decision || '').toUpperCase();
  if (decUpper.includes('MUA') || decUpper.includes('KHẢ QUAN')) {
    decisionBadge.textContent = 'MUA / KHẢ QUAN';
    decisionBadge.className = 'kpi-badge badge-success';
  } else if (decUpper.includes('NẮM GIỮ') || decUpper.includes('THEO DÕI')) {
    decisionBadge.textContent = 'NẮM GIỮ / THEO DÕI';
    decisionBadge.className = 'kpi-badge badge-warning';
  } else if (decUpper.includes('BÁN') || decUpper.includes('GIẢM')) {
    decisionBadge.textContent = 'BÁN / THẬN TRỌNG';
    decisionBadge.className = 'kpi-badge badge-danger';
  } else {
    decisionBadge.textContent = 'XEM BÁO CÁO';
    decisionBadge.className = 'kpi-badge badge-info';
  }

  // Vẽ biểu đồ trực quan
  $('chartsPanel').classList.remove('hidden');
  renderRevenueChart(report);
  renderSectorBenchmarkChart(report);

  // Cơ hội & Rủi ro
  const oppList = $('opportunitiesList');
  oppList.replaceChildren();
  (report.opportunities || []).forEach(item => oppList.appendChild(textElement('li', '✓ ' + item)));
  if (!report.opportunities || !report.opportunities.length) {
    oppList.appendChild(textElement('li', 'Chưa có thông tin cơ hội cụ thể.', 'muted'));
  }

  const riskList = $('risksList');
  riskList.replaceChildren();
  (report.risks || []).forEach(item => riskList.appendChild(textElement('li', '⚠️ ' + item)));
  if (!report.risks || !report.risks.length) {
    riskList.appendChild(textElement('li', 'Chưa có thông tin rủi ro cụ thể.', 'muted'));
  }

  // Render các Phân hệ chi tiết
  $('sections').replaceChildren();
  for (const [secKey, section] of Object.entries(report.sections)) {
    const card = textElement('article', '', 'panel');
    const title = textElement('h2', section.title);
    title.appendChild(textElement('span', section.status, 'section-status'));
    card.appendChild(title);
    card.appendChild(textElement('p', section.summary, 'section-summary'));

    // Bảng dữ liệu có lọc
    if (section.rows && section.rows.length) {
      const filterBar = textElement('div', '', 'table-filter-bar');
      filterBar.appendChild(textElement('span', `Tổng số dòng: ${section.rows.length}`, 'muted'));

      const searchInput = document.createElement('input');
      searchInput.type = 'text';
      searchInput.placeholder = '🔍 Tìm kiếm chỉ tiêu...';
      searchInput.className = 'table-filter-input';
      filterBar.appendChild(searchInput);
      card.appendChild(filterBar);

      const wrap = textElement('div', '', 'table-wrap');
      const table = document.createElement('table');
      const keys = Object.keys(section.rows[0]);

      const thead = document.createElement('thead');
      const headRow = document.createElement('tr');
      keys.forEach(k => headRow.appendChild(textElement('th', k)));
      thead.appendChild(headRow);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      const renderRows = (filteredRows) => {
        tbody.replaceChildren();
        filteredRows.forEach(row => {
          const tr = document.createElement('tr');
          keys.forEach(key => {
            const val = row[key];
            let displayVal = 'Chưa có dữ liệu';
            if (val !== null && val !== undefined) {
              if (typeof val === 'number') {
                displayVal = Math.abs(val) < 100
                  ? val.toLocaleString('vi-VN', { maximumFractionDigits: 4 })
                  : val.toLocaleString('vi-VN', { maximumFractionDigits: 0 });
              } else {
                displayVal = String(val);
              }
            }
            const td = textElement('td', displayVal);
            if (val === null) td.style.color = '#94a3b8';
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
      };

      renderRows(section.rows);
      table.appendChild(tbody);
      wrap.appendChild(table);
      card.appendChild(wrap);

      // Lọc tức thì khi gõ
      searchInput.addEventListener('input', () => {
        const query = searchInput.value.toLowerCase().trim();
        if (!query) {
          renderRows(section.rows);
        } else {
          const matched = section.rows.filter(row =>
            keys.some(k => String(row[k] || '').toLowerCase().includes(query))
          );
          renderRows(matched);
        }
      });
    }

    // Danh sách nguồn bằng chứng dạng pills bấm được
    if (section.source_ids && section.source_ids.length) {
      const sourcesP = textElement('p', 'Nguồn tham chiếu: ', 'muted');
      sourcesP.style.marginTop = '12px';
      section.source_ids.forEach(sid => {
        const pill = textElement('span', `[${sid}]`, 'source-pill');
        pill.title = 'Nhấp để xem chi tiết nguồn bằng chứng';
        pill.addEventListener('click', () => showSourceModal(sid));
        sourcesP.appendChild(pill);
      });
      card.appendChild(sourcesP);
    }

    $('sections').appendChild(card);
  }

  // Danh sách issues
  const issuesList = $('issues');
  issuesList.replaceChildren();
  if (report.issues && report.issues.length) {
    report.issues.forEach(issue => {
      const li = textElement('li', `[${issue.severity.toUpperCase()}] ${issue.code}: ${issue.message}`);
      if (issue.severity === 'error') li.style.color = '#dc2626';
      else if (issue.severity === 'warning') li.style.color = '#d97706';
      issuesList.appendChild(li);
    });
  } else {
    issuesList.appendChild(textElement('li', 'Không phát hiện vấn đề bất thường về dữ liệu.'));
  }

  // Kết quả AI và Jev
  const aiBox = $('aiResult');
  aiBox.replaceChildren();
  aiBox.appendChild(textElement('p', `Trạng thái LLM AI: ${report.ai.status || 'disabled'} — ${report.ai.note || ''}`));
  aiBox.appendChild(textElement('p', `Trạng thái Jev TypeSafe: ${report.jev.status || 'disabled'} | Quyết định áp dụng: ${report.jev.applied_decision || 'Chưa chạy'} | Ghi chú: ${report.jev.note || ''}`));

  if (report.ai.claims && report.ai.claims.length) {
    const claimsTitle = document.createElement('strong');
    claimsTitle.textContent = 'Luận điểm do AI tổng hợp (đã kiểm duyệt ranh giới nguồn):';
    claimsTitle.style.display = 'block';
    claimsTitle.style.margin = '10px 0 6px';
    aiBox.appendChild(claimsTitle);

    report.ai.claims.forEach(c => {
      const p = textElement('p', '• ' + c.text + ' ');
      (c.source_ids || []).forEach(sid => {
        const pill = textElement('span', `[${sid}]`, 'source-pill');
        pill.addEventListener('click', () => showSourceModal(sid));
        p.appendChild(pill);
      });
      aiBox.appendChild(p);
    });
  }
}

// Xử lý Polling tiến trình
async function poll() {
  if (!activeJob) return;
  try {
    const response = await api('/api/jobs/' + activeJob.id, { headers: { 'X-Job-Token': activeJob.token } });
    const job = await response.json();
    $('phase').textContent = phases[job.phase] || job.phase;
    $('percent').textContent = job.percent + '%';
    $('progressBar').value = job.percent;

    if (job.status === 'completed') {
      render(job.report, job);
      $('submit').disabled = false;
      return;
    }
    if (['failed', 'interrupted'].includes(job.status)) {
      throw new Error(job.error || `Tác vụ kết thúc với trạng thái: ${job.status}`);
    }
    setTimeout(poll, 600);
  } catch (error) {
    $('error').textContent = error.message;
    $('submit').disabled = false;
  }
}

// Gửi form phân tích
$('analysisForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('submit').disabled = true;
  $('error').textContent = '';
  $('progress').classList.remove('hidden');

  try {
    if ($('llmApiKey').value.trim() || $('jevApiKey').value.trim()) await saveProviderConfig();
    const datasets = {};
    for (const kind of ['prices', 'macro', 'news']) {
      const file = $(kind + 'File').files[0];
      if (file) {
        const form = new FormData();
        form.append('file', file);
        const response = await api('/api/uploads/' + kind, { method: 'POST', body: form });
        datasets[kind] = (await response.json()).id;
      }
    }

    const request = {
      ticker: $('ticker').value.trim().toUpperCase(),
      mode: $('mode').value,
      as_of: $('asOf').value,
      start_year: Number($('startYear').value),
      end_year: Number($('endYear').value),
      risk_profile: $('risk').value,
      horizon_months: Number($('horizon').value),
      use_ai: $('useAi').checked,
      use_jev: $('useJev').checked,
      sections: [...document.querySelectorAll('input[name=section]:checked')].map(el => el.value),
      datasets,
      valuation: {}
    };

    if ($('targetPe').value) {
      request.valuation.target_pe = Number($('targetPe').value);
    }

    const response = await api('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request)
    });

    activeJob = await response.json();
    sessionStorage.setItem('vnresearch-job', JSON.stringify(activeJob));
    poll();
  } catch (error) {
    $('error').textContent = error.message;
    $('submit').disabled = false;
  }
});

// Xử lý tải tệp (PDF, JSON, Manifest)
document.querySelectorAll('[data-file]').forEach(button => {
  button.addEventListener('click', async () => {
    if (!activeJob) return;
    try {
      const filename = button.dataset.file;
      const response = await api(`/api/jobs/${activeJob.id}/files/${filename}`, {
        headers: { 'X-Job-Token': activeJob.token }
      });
      const objectUrl = URL.createObjectURL(await response.blob());
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `${activeJob.id.substring(0, 8)}_${$('ticker').value}_${filename}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
      $('error').textContent = error.message;
    }
  });
});

// Gợi ý mã khi gõ
$('ticker').addEventListener('input', async () => {
  try {
    const val = $('ticker').value.trim();
    if (val.length < 1) return;
    const response = await api('/api/companies?query=' + encodeURIComponent(val));
    const records = await response.json();
    $('companies').replaceChildren(...records.map(record => {
      const option = document.createElement('option');
      option.value = record.ticker;
      option.label = record.name;
      return option;
    }));
  } catch (e) {}
});

// Nút chọn nhanh mã cổ phiếu gợi ý
document.querySelectorAll('.ticker-chip').forEach(btn => {
  btn.addEventListener('click', () => {
    $('ticker').value = btn.dataset.ticker;
    $('ticker').dispatchEvent(new Event('input'));
  });
});

// Khôi phục tác vụ lưu trong session
try {
  const saved = sessionStorage.getItem('vnresearch-job');
  if (saved) {
    activeJob = JSON.parse(saved);
    $('progress').classList.remove('hidden');
    poll();
  }
} catch {
  sessionStorage.removeItem('vnresearch-job');
}

// Đọc trạng thái cấu hình provider, không nhận hoặc hiển thị API key.
refreshProviderCapabilities();

$('mode').addEventListener('change', () => {
  refreshProviderCapabilities();
});
