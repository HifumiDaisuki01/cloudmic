export const VERSION = '2.0.0';
export const ROOM_TTL = 24 * 60 * 60 * 1000;
export const PAIR_TTL = 10 * 60 * 1000;
export const CODE_PATTERN = /^[A-HJ-NP-Z2-9]{8}$/;
export function randomKey(bytes = 32) {
  return Array.from(crypto.getRandomValues(new Uint8Array(bytes)), x => x.toString(16).padStart(2, '0')).join('');
}
export function randomCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return Array.from(crypto.getRandomValues(new Uint8Array(8)), x => chars[x & 31]).join('');
}
export async function hash(value) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))), x => x.toString(16).padStart(2, '0')).join('');
}
export function sayMessage(obj) {
  if (!obj || obj.type !== 'say' || typeof obj.id !== 'string' || !/^[a-zA-Z0-9-]{8,64}$/.test(obj.id)) return null;
  if (typeof obj.text !== 'string' || !obj.text.trim() || obj.text.length > 500) return null;
  return { type: 'say', id: obj.id, text: obj.text.trim() };
}
export function json(value, status = 200) {
  return Response.json(value, { status, headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
}
