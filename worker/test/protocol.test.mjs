import test from 'node:test';
import assert from 'node:assert/strict';
import { randomCode, randomKey, hash, sayMessage, CODE_PATTERN } from '../src/protocol.js';
test('room codes have full expected alphabet and independent secrets', async () => {
  const codes = new Set(Array.from({length:1000},randomCode));
  assert.equal(codes.size,1000);
  for (const code of codes) assert.match(code,CODE_PATTERN);
  assert.match(randomKey(),/^[a-f0-9]{64}$/);
  assert.notEqual(randomKey(),randomKey());
  assert.equal(await hash('a'),await hash('a'));
});
test('only valid bounded utterances enter relay', () => {
  assert.deepEqual(sayMessage({type:'say',id:'valid-id-1234',text:' hello '}),{type:'say',id:'valid-id-1234',text:'hello'});
  for (const input of [null,[],{type:'say',id:'x',text:'a'},{type:'say',id:'valid-id-1234',text:'x'.repeat(501)},{type:'say',id:'valid-id-1234',text:[]},{type:'say',id:'valid-id-1234',text:'  '}]) assert.equal(sayMessage(input),null);
});
