import test from 'node:test';
import assert from 'node:assert/strict';
import { createMainLibraryAdapter, registerOwnerLibraryTools, LIBRARY_TOOL_NAMES } from '../src/index.mjs';

const chats = [{ id: 'owner', owner: true, mode: 'private' }, { id: 'group', mode: 'group' }, { id: 'friend', mode: 'private' }];
const meta = { title: 'Synthetic index', file_path: 'index.md', permalink: 'index', checksum: 'sha256-abc' };
const propertySets = {
  search_notes: 'query project search_all_projects page page_size search_type output_format compact',
  read_note: 'identifier project include_content output_format',
  write_note: 'title content directory project overwrite output_format',
  edit_note: 'identifier operation content project find_text expected_replacements expected_checksum output_format',
};
const tools = Object.entries(propertySets).map(([name, names]) => ({ name, inputSchema: { type: 'object', properties: Object.fromEntries(names.split(' ').map(n => [n, {}])) } }));
const encoded = value => ({ content: [{ type: 'text', text: JSON.stringify(value) }] });
function mock({ sse = false, handler, badTools = false } = {}) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    const message = JSON.parse(options.body); calls.push({ url, options, message });
    if (message.method === 'notifications/initialized') return new Response(null, { status: 202 });
    let result;
    if (message.method === 'initialize') result = { protocolVersion: '2025-06-18', capabilities: { tools: {} } };
    else if (message.method === 'tools/list') result = { tools: badTools ? [] : tools };
    else {
      const { name, arguments: args } = message.params;
      if (args.identifier === '00-总览/目录') result = encoded(meta);
      else result = handler ? await handler(message, options) : encoded(name === 'search_notes' ? { results: [], total: 0 } : name === 'read_note' ? { ...meta, content: 'synthetic only' } : name === 'write_note' ? { ...meta, action: 'created' } : { ...meta, operation: args.operation, fileCreated: false });
    }
    if (result instanceof Response) return result;
    const row = { jsonrpc: '2.0', id: message.id, result };
    const headers = { 'content-type': sse ? 'text/event-stream' : 'application/json', ...(message.method === 'initialize' ? { 'Mcp-Session-Id': 'synthetic-session' } : {}) };
    return new Response(sse ? `: keepalive\n\ndata: ${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/progress', params: {} })}\n\ndata: ${JSON.stringify(row)}\n\n` : JSON.stringify(row), { headers });
  };
  return { calls, fetchImpl };
}
const make = (network, options = {}) => createMainLibraryAdapter({ chats, url: 'http://127.0.0.1:8767/mcp', fetchImpl: network.fetchImpl, ...options });
const rejected = (promise, code) => assert.rejects(promise, error => error.code === code);

test('configured owner is authoritative; groups, friends, spoofing, traversal and project routes never fetch', async () => {
  const network = mock(), adapter = make(network);
  for (const id of ['group', 'friend', 'unknown']) {
    await rejected(adapter.call(id, 'search', { query: 'x' }), 'LIBRARY_OWNER_REQUIRED');
    await rejected(adapter.health(id), 'LIBRARY_OWNER_REQUIRED');
  }
  for (const args of [{ query: 'x', owner: true }, { query: 'x', project: 'main' }, { query: 'x', projects: ['private'] }, { query: 'x', endpoint: 'x' }]) await rejected(adapter.call('owner', 'search', args), 'LIBRARY_ARGUMENT_DENIED');
  for (const identifier of ['memory://private/note', 'memory://main/note', '../note', 'a/../note', '/note', 'C:\\secret', '\\\\server\\share', 'a/%2e%2e', '%252e%252e/note', 'private/note', 'a//b', 'a/.. /b']) await rejected(adapter.call('owner', 'read', { identifier }), 'LIBRARY_IDENTIFIER_DENIED');
  assert.equal(network.calls.length, 0);
});

test('only literal loopback MCP endpoint is allowed, including explicit denial of private port', () => {
  for (const url of ['http://example.com:8767/mcp', 'http://localhost:8767/mcp', 'http://127.0.0.1:8768/mcp', 'http://user:pw@127.0.0.1:8767/mcp', 'http://127.0.0.1:8767/mcp?q=x', 'http://127.0.0.1:8767/other']) assert.throws(() => make(mock(), { url }), e => e.code === 'LIBRARY_ENDPOINT_DENIED');
});

test('JSON transport initializes once, preserves session/protocol headers, forces main and no cross-project search', async () => {
  const network = mock(), adapter = make(network);
  const [a, b] = await Promise.all([adapter.call('owner', 'search', { query: 'x' }), adapter.call('owner', 'read', { identifier: 'note' })]);
  assert.deepEqual(a.data.results, []); assert.equal(a.data.total, 0); assert.equal(b.data.content, 'synthetic only');
  assert.equal(network.calls.filter(x => x.message.method === 'initialize').length, 1);
  for (const row of network.calls) {
    assert.equal(row.options.redirect, 'error');
    if (row.message.method !== 'initialize') {
      assert.equal(row.options.headers['Mcp-Session-Id'], 'synthetic-session');
      assert.equal(row.options.headers['MCP-Protocol-Version'], '2025-06-18');
    }
    if (row.message.method === 'tools/call') assert.equal(row.message.params.arguments.project, 'main');
  }
  const search = network.calls.find(x => x.message.params?.name === 'search_notes').message.params.arguments;
  assert.equal(search.search_all_projects, false); assert.equal(search.search_type, 'text'); assert.equal(search.compact, true);
});

test('SSE accepts matching response, ignores notifications and supports FastMCP union wrapper', async () => {
  const network = mock({ sse: true, handler: () => ({ structuredContent: { result: { results: [] } } }) });
  assert.equal((await make(network).call('owner', 'search', { query: 'x' })).ok, true);
});

test('health distinguishes unconfigured, refused connection, contract mismatch and real readiness without note bodies', async () => {
  assert.equal((await make(mock(), { url: null }).health('owner')).code, 'LIBRARY_NOT_CONFIGURED');
  const offline = make({ fetchImpl: async () => { throw new Error('ECONNREFUSED secret body'); } });
  assert.equal((await offline.health('owner')).code, 'LIBRARY_UNREACHABLE');
  assert.equal((await make(mock({ badTools: true })).health('owner')).code, 'LIBRARY_TOOL_CONTRACT_MISSING');
  const network = mock(), health = await make(network).health('owner');
  assert.deepEqual(health, { ok: true, status: 'ready', project: 'main', anchorVerified: true });
  for (const call of network.calls.filter(x => x.message.method === 'tools/call')) assert.equal(call.message.params.arguments.include_content, false);
  assert.equal(JSON.stringify(health).includes(meta.title), false);
});

test('empty replacement library is refused and cannot trigger writes', async () => {
  const network = mock();
  const fetchImpl = async (url, options) => {
    const message = JSON.parse(options.body);
    if (message.params?.arguments?.identifier === '00-总览/目录') return new Response(JSON.stringify({ jsonrpc: '2.0', id: message.id, result: encoded({ error: 'NOTE_NOT_FOUND' }) }), { headers: { 'content-type': 'application/json' } });
    return network.fetchImpl(url, options);
  };
  const adapter = make({ fetchImpl });
  assert.equal((await adapter.health('owner')).code, 'LIBRARY_NOTE_NOT_FOUND');
  await rejected(adapter.call('owner', 'write', { title: 'new', content: 'test', directory: '.' }), 'LIBRARY_NOTE_NOT_FOUND');
  assert.equal(network.calls.some(x => x.message.params?.name === 'write_note'), false);
});

test('MCP tool errors and malformed textual search errors are not empty successful searches', async () => {
  for (const [response, code] of [[{ isError: true, content: [{ type: 'text', text: 'private diagnostic' }] }, 'LIBRARY_TOOL_ERROR'], [{ content: [{ type: 'text', text: '# Search unavailable' }] }, 'LIBRARY_RESULT_INVALID'], [encoded({ error: 'NOTE_NOT_FOUND' }), 'LIBRARY_NOTE_NOT_FOUND']]) {
    await rejected(make(mock({ handler: () => response })).call('owner', 'search', { query: 'x' }), code);
  }
});

test('foreign project routing metadata is rejected rather than returned', async () => {
  for (const row of [{ title: 'x', project: 'private', permalink: 'note' }, { title: 'x', permalink: 'memory://other/note' }, { title: 'x', file_path: '../secret.md' }]) await assert.rejects(make(mock({ handler: () => encoded({ results: [row] }) })).call('owner', 'search', { query: 'x' }), e => ['LIBRARY_RESULT_SCOPE_DENIED', 'LIBRARY_IDENTIFIER_DENIED'].includes(e.code));
});

test('writes are create-only; edits require checksum and exactly one replacement', async () => {
  const network = mock(), adapter = make(network);
  await rejected(adapter.call('owner', 'write', { title: 'x', directory: '.', content: 'x', overwrite: true }), 'LIBRARY_ARGUMENT_DENIED');
  await rejected(adapter.call('owner', 'edit', { identifier: 'note', operation: 'append', content: 'x' }), 'LIBRARY_ARGUMENT_INVALID');
  assert.equal(network.calls.length, 0);
  assert.equal((await adapter.call('owner', 'write', { title: 'new', content: 'test', directory: 'notes' })).outcome, 'confirmed');
  assert.equal((await adapter.call('owner', 'edit', { identifier: 'note', operation: 'find_replace', find_text: 'old', content: 'new', expected_checksum: 'sha256-abc' })).outcome, 'confirmed');
  const write = network.calls.find(x => x.message.params?.name === 'write_note').message.params.arguments;
  const edit = network.calls.find(x => x.message.params?.name === 'edit_note').message.params.arguments;
  assert.equal(write.overwrite, false); assert.equal(edit.expected_replacements, 1); assert.equal(edit.expected_checksum, 'sha256-abc');
});

test('write timeout, MCP failure and session expiry have unknown outcome and are never replayed', async () => {
  const failures = [async () => new Promise(() => {}), () => ({ isError: true, content: [] }), () => new Response('', { status: 404 })];
  for (const handler of failures) {
    const network = mock({ handler }), adapter = make(network, { timeoutMs: 30 });
    await assert.rejects(adapter.call('owner', 'write', { title: 'new', content: 'x', directory: '.' }), e => e.code === 'LIBRARY_WRITE_OUTCOME_UNKNOWN' && e.outcome === 'unknown');
    assert.equal(network.calls.filter(x => x.message.params?.name === 'write_note').length, 1);
  }
});

test('mismatched RPC id, oversized body, HTTP auth and redirected requests fail safely', async () => {
  const cases = [
    [() => new Response(JSON.stringify({ jsonrpc: '2.0', id: -99, result: encoded({ results: [] }) }), { headers: { 'content-type': 'application/json' } }), 'LIBRARY_RESPONSE_MISSING'],
    [() => encoded({ results: [], padding: 'x'.repeat(4000) }), 'LIBRARY_RESPONSE_TOO_LARGE'],
    [() => new Response('', { status: 401 }), 'LIBRARY_AUTH_REQUIRED'],
    [() => { throw new TypeError('redirect blocked'); }, 'LIBRARY_UNREACHABLE'],
  ];
  for (const [handler, code] of cases) await rejected(make(mock({ handler }), { maxResponseBytes: 3000 }).call('owner', 'search', { query: 'x' }), code);
});

test('native wrapper binds one Agent, denies changed active identity, and never exposes raw errors', async () => {
  const network = mock({ handler: () => ({ isError: true, content: [{ type: 'text', text: 'SECRET' }] }) });
  const adapter = make(network), agent = {}, registered = [], agentCtx = { tools: { register: tool => registered.push(tool) } };
  const options = { agentCtx, agent, adapter, defineTool: value => value, isActive: () => true };
  assert.deepEqual(registerOwnerLibraryTools({ ...options, chatId: 'group' }), []);
  assert.deepEqual(registerOwnerLibraryTools({ ...options, chatId: 'owner' }), LIBRARY_TOOL_NAMES);
  const search = registered.find(x => x.name.endsWith('_search'));
  await rejected(search.execute({ query: 'x' }, { agent: {} }), 'LIBRARY_AGENT_SCOPE_DENIED');
  const result = await search.execute({ query: 'x' }, { agent });
  assert.equal(result.code, 'LIBRARY_TOOL_ERROR'); assert.equal(JSON.stringify(result).includes('SECRET'), false);
  const inactive = [];
  registerOwnerLibraryTools({ ...options, chatId: 'owner', agentCtx: { tools: { register: x => inactive.push(x) } }, isActive: () => false });
  await rejected(inactive[0].execute({}, { agent }), 'LIBRARY_AGENT_SCOPE_DENIED');
});

test('an edit service missing the single-replacement guard is not accepted', async () => {
  const network = mock();
  const fetchImpl = async (url, options) => {
    const message = JSON.parse(options.body);
    if (message.method !== 'tools/list') return network.fetchImpl(url, options);
    const olderTools = structuredClone(tools);
    delete olderTools.find(x => x.name === 'edit_note').inputSchema.properties.expected_replacements;
    return new Response(JSON.stringify({ jsonrpc: '2.0', id: message.id, result: { tools: olderTools } }), { headers: { 'content-type': 'application/json' } });
  };
  assert.equal((await make({ fetchImpl }).health('owner')).code, 'LIBRARY_TOOL_CONTRACT_MISSING');
});

test('cancelling one initialization waiter is prompt and does not cancel another or send its write', async () => {
  const network = mock(); let release;
  const gate = new Promise(resolve => { release = resolve; });
  const fetchImpl = async (url, options) => { if (JSON.parse(options.body).method === 'initialize') await gate; return network.fetchImpl(url, options); };
  const adapter = make({ fetchImpl }), controller = new AbortController();
  const cancelled = adapter.call('owner', 'write', { title: 'new', content: 'x', directory: '.' }, { signal: controller.signal });
  const remaining = adapter.call('owner', 'search', { query: 'x' });
  controller.abort();
  await assert.rejects(cancelled, e => e.code === 'LIBRARY_CANCELLED' && e.outcome === 'not_sent');
  release(); assert.equal((await remaining).ok, true);
  assert.equal(network.calls.some(x => x.message.params?.name === 'write_note'), false);
});
