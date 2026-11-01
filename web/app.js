function authHeaders() {
  const u = sessionStorage.getItem('panelUser') || '';
  const p = sessionStorage.getItem('panelPass') || '';
  if (!u && !p) return {};
  return { 'Authorization': 'Basic ' + btoa(u + ':' + p) };
}
function saveAuth() {
  sessionStorage.setItem('panelUser', document.getElementById('panelUser').value);
  sessionStorage.setItem('panelPass', document.getElementById('panelPass').value);
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
}
async function loadInstances() {
  try {
    const items = await api('/api/instances');
    document.getElementById('instanceRows').innerHTML = items.map(it => `
      <tr><td>${it.display_name || ''}</td><td>${it.shape || ''}</td><td>${it.lifecycle_state || ''}</td>
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
  const body = {
    availability_domain: document.getElementById('ad').value,
    image_id: document.getElementById('imageId').value,
    subnet_id: document.getElementById('subnetId').value,
    display_name: document.getElementById('displayName').value,
    ssh_authorized_keys: document.getElementById('sshKey').value,
    preset: document.getElementById('preset').value || null,
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
