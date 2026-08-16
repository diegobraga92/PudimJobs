/**
 * Regenerates `mobile/src/i18n/dictionary.ts` from the Angular web frontend so
 * web + mobile strings stay identical:
 *
 *   node scripts/extract-dictionary.js   (run from the repo root)
 */
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(
  path.join('frontend', 'src', 'app', 'services', 'i18n.service.ts'),
  'utf8',
);
const startMarker = 'export const DICTIONARY: Record<string, TranslationEntry> = {';
const start = src.indexOf(startMarker);
if (start === -1) {
  console.error('start marker not found in i18n.service.ts');
  process.exit(1);
}

let depth = 0;
let end = -1;
for (let i = src.indexOf('{', start); i < src.length; i++) {
  if (src[i] === '{') depth++;
  else if (src[i] === '}') {
    depth--;
    if (depth === 0) {
      end = i + 1;
      break;
    }
  }
}
if (end === -1) {
  console.error('end of dictionary not found');
  process.exit(1);
}

const body = src.slice(start + startMarker.length, end - 1);
const out = `/**
 * Translation dictionary for the PudimJobs app.
 * Every user-facing string lives here in English (en) and Brazilian
 * Portuguese (pt-BR). Keys are dot-namespaced by feature/domain.
 *
 * NOTE: this file is generated from the Angular web frontend
 * (frontend/src/app/services/i18n.service.ts) to keep web + mobile strings
 * identical. Regenerate with: node scripts/extract-dictionary.js
 */

export interface TranslationEntry {
  en: string;
  'pt-BR': string;
}

export const DICTIONARY: Record<string, TranslationEntry> = {${body}\n};\n`;

fs.mkdirSync(path.join('mobile', 'src', 'i18n'), { recursive: true });
fs.writeFileSync(path.join('mobile', 'src', 'i18n', 'dictionary.ts'), out);
const entries = (body.match(/^\s*'[^']+':/gm) || []).length;
console.log(`wrote mobile/src/i18n/dictionary.ts (${entries} entries)`);
