function authHeaders() {
  const u = sessionStorage.getItem('panelUser') || '';
  const p = sessionStorage.getItem('panelPass') || '';
  if (!u && !p) return {};
  return { 'Authorization': 'Basic ' + btoa(u + ':' + p) };
}
function saveAuth() {
  sessionStorage.setItem('panelUser', document.getElementById('panelUser').value);
  sessionStorage.setItem('panelPass', document.getElementById('panelPass').value);
  loadCompartments();
  loadInstances();
}
async function api(path, method = 'GET', body = null) {
  const r = await fetch(path, {
    method,
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : null,
  });
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { raw: text }; }
  if (!r.ok) throw new Error(data.detail || text);
  return data;
}
function showTab(name) {
  document.querySelectorAll('.tab').forEach(el => el.classList.add('hidden'));
  document.getElementById('tab-' + name).classList.remove('hidden');
  if (name === 'credentials') loadCredentials();
  if (name === 'instances' || name === 'create') loadCompartments();
}
async function loadCompartments() {
  try {
    const comps = await api('/api/compartments');
    const filter = document.getElementById('compFilter');
    const curFilter = filter.value;
    filter.innerHTML = '<option value="">全部（自动获取）</option>' + comps.map(c => `<option value="${esc(c.id)}">${esc(c.name || c.id)}</option>`).join('');
    if ([...filter.options].some(o => o.value === curFilter)) filter.value = curFilter;
    const createSel = document.getElementById('createCompartment');
    const curCreate = createSel.value;
    createSel.innerHTML = comps.map(c => `<option value="${esc(c.id)}">${esc(c.name || c.id)}</option>`).join('');
    if ([...createSel.options].some(o => o.value === curCreate)) createSel.value = curCreate;
  } catch (e) { /* 没权限列 compartment 时，实例列表仍可走自动获取并在那里报错 */ }
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
async function loadCredentials() {
  try {
    const r = await api('/api/credentials');
    document.getElementById('credRows').innerHTML = r.profiles.map(p => `
      <tr><td>${esc(p.name)}</td><td>${esc(p.region)}</td><td>${esc(p.user_ocid)}</td><td>${esc(p.fingerprint)}</td>
      <td>${p.is_active ? '当前生效' : (p.has_key ? '已保存' : '私钥缺失')}</td>
      <td>
        ${p.is_active ? '' : `<button onclick="activateCredential('${p.id}')">切换到这条</button>`}
        <button onclick="testCredential('${p.id}')">测试</button>
        <button onclick="deleteCredential('${p.id}', '${esc(p.name)}')">删除</button>
      </td></tr>`).join('') || '<tr><td colspan="6">还没有保存的密钥，先在上面上传一条。</td></tr>';
    if (!r.active_id) document.getElementById('credResult').textContent = '当前没有激活的密钥，面板按原来的 .env / ~/.oci/config 工作。';
  } catch (e) { document.getElementById('credResult').textContent = '错误：' + e.message; }
}
async function uploadCredential() {
  const file = document.getElementById('credKeyFile').files[0];
  if (!file) { document.getElementById('credResult').textContent = '请先选私钥文件（.pem）。'; return; }
  const fd = new FormData();
  fd.append('name', document.getElementById('credName').value);
  fd.append('user_ocid', document.getElementById('credUser').value);
  fd.append('tenancy_ocid', document.getElementById('credTenancy').value);
  fd.append('fingerprint', document.getElementById('credFingerprint').value);
  fd.append('region', document.getElementById('credRegion').value);
  fd.append('compartment_ocid', document.getElementById('credCompartment').value);
  fd.append('key_file', file);
  try {
    const r = await fetch('/api/credentials', { method: 'POST', headers: authHeaders(), body: fd });
    const text = await r.text();
    let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!r.ok) throw new Error(data.detail || text);
    document.getElementById('credResult').textContent = '已保存：' + data.name + (data.is_active ? '（已是当前生效）' : '');
    document.getElementById('credKeyFile').value = '';
    loadCredentials();
  } catch (e) { document.getElementById('credResult').textContent = '错误：' + e.message; }
}
async function activateCredential(id) {
  await api(`/api/credentials/${id}/activate`, 'POST', {});
  loadCredentials(); loadInstances();
}
async function testCredential(id) {
  try {
    const r = await api(`/api/credentials/${id}/test`, 'POST', {});
    document.getElementById('credResult').textContent = (r.ok ? '测试通过：' : '测试未通过：') + r.detail;
  } catch (e) { document.getElementById('credResult').textContent = '错误：' + e.message; }
}
async function deleteCredential(id, name) {
  if (!confirm('确定删除密钥“' + name + '”吗？私钥文件会一并删掉，此操作不可撤销。')) return;
  await api(`/api/credentials/${id}`, 'DELETE');
  loadCredentials();
}
async function loadInstances() {
  try {
    const comp = document.getElementById('compFilter').value;
    const path = comp ? '/api/instances?compartment_id=' + encodeURIComponent(comp) : '/api/instances';
    const items = await api(path);
    document.getElementById('instanceRows').innerHTML = items.map(it => `
      <tr><td>${it.display_name || ''}</td><td>${it.shape || ''}</td><td>${it.lifecycle_state || ''}</td>
      <td title="${it.compartment_id || ''}">${(it.compartment_id || '').slice(-8)}</td>
      <td>
        <button onclick="doAction('${it.id}','START')">开机</button>
        <button onclick="doAction('${it.id}','STOP')">关机</button>
        <button onclick="doAction('${it.id}','RESET')">重启</button>
        <button onclick="terminateInstance('${it.id}')">终止</button>
      </td></tr>`).join('');
    document.getElementById('health').textContent = '已连接';
  } catch (e) { document.getElementById('health').textContent = '错误：' + e.message; }
}
async function doAction(id, action) {
  await api(`/api/instances/${id}/action`, 'POST', { action });
  loadInstances();
}
async function terminateInstance(id) {
  if (!confirm('确定终止该实例吗？此操作不可撤销。')) return;
  await api(`/api/instances/${id}/terminate`, 'POST', { confirm: true });
  loadInstances();
}
async function a1check() {
  const r = await api('/api/a1-check');
  document.getElementById('a1Result').textContent = JSON.stringify(r, null, 2);
}
async function syncHosts() {
  const hosts = await api('/api/hosts/sync');
  localStorage.setItem('ociHosts', JSON.stringify(hosts));
  alert('已同步 ' + hosts.length + ' 台主机，Web SSH 页可直接用公网 IP 连接。');
  if (hosts[0]) document.getElementById('sshHost').value = hosts[0].public_ip || '';
}
async function createInstance() {
  const rootPass = document.getElementById('enableRootPass').checked ? document.getElementById('rootPass').value : '';
  if (document.getElementById('enableRootPass').checked && rootPass.length < 8) {
    document.getElementById('createResult').textContent = '错误：root 密码至少 8 位。';
    return;
  }
  const body = {
    compartment_id: document.getElementById('createCompartment').value || null,
    availability_domain: document.getElementById('ad').value,
    image_id: document.getElementById('imageId').value,
    subnet_id: document.getElementById('subnetId').value,
    display_name: document.getElementById('displayName').value,
    ssh_authorized_keys: document.getElementById('sshKey').value,
    preset: document.getElementById('preset').value || null,
    root_password: rootPass || null,
  };
  try {
    const r = await api('/api/instances', 'POST', body);
    document.getElementById('createResult').textContent = JSON.stringify(r, null, 2);
  } catch (e) { document.getElementById('createResult').textContent = '错误：' + e.message; }
}
async function loadIps() {
  const r = await api('/api/public-ips');
  document.getElementById('ipResult').textContent = JSON.stringify(r, null, 2);
}
async function loadVolumes() {
  const r = await api('/api/volumes');
  document.getElementById('volResult').textContent = JSON.stringify(r, null, 2);
}
async function loadBuckets() {
  const r = await api('/api/buckets');
  document.getElementById('bucketResult').textContent = JSON.stringify(r, null, 2);
}
let ws = null;
function connectSsh() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(proto + '//' + location.host + '/ws/ssh');
  const out = document.getElementById('sshOut');
  ws.onopen = () => ws.send(JSON.stringify({
    host: document.getElementById('sshHost').value,
    username: document.getElementById('sshUser').value,
    password: document.getElementById('sshPass').value,
    key_path: document.getElementById('sshKeyPath').value,
  }));
  ws.onmessage = ev => { out.textContent += ev.data; out.scrollTop = out.scrollHeight; };
  ws.onclose = () => { out.textContent += '\n[连接已关闭]\n'; };
}
function sendSsh() {
  const input = document.getElementById('sshInput');
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'input', data: input.value + '\n' }));
  input.value = '';
}
loadInstances();
