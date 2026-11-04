import type { CvExportFormat, CvLanguage, CvTemplate } from '../services/cv.service';

/**
 * Recruiter-facing CV export filenames (ADR 030).
 *
 * Mirrors `backend/app/services/cv_filename.py`, which is the source of truth:
 * a tailored download is named by the *server* (the artifact's `file_stem` plus
 * the language marker), and this helper only exists for the editor, which
 * renders a structure the API never stored. Keep the two in step — a name the
 * browser saves must look like the name the API would return.
 */

const MAX_NAME_CHARS = 48;

const BRACKETED = /\([^)]*\)|\[[^\]]*\]/g;
const NON_ALNUM = /[^A-Za-z0-9]+/g;
// A parser can read a section heading as the candidate's name; joining it to
// the document type would print "Curriculum-Vitae-CV.pdf".
const JUNK_NAMES = new Set(['cv', 'curriculum', 'curriculum-vitae', 'curriculo', 'resume']);

/** ASCII-folded, hyphen-joined words: `Backend Engineer (Remote)` → `Backend-Engineer`. */
function slug(value: string | null | undefined, maxChars: number): string {
  const ascii = (value ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  const words = ascii
    .replace(BRACKETED, ' ')
    .replace(NON_ALNUM, ' ')
    .split(' ')
    .filter(Boolean);
  if (!words.length) {
    return '';
  }
  // An over-long single word is cut rather than dropped: an empty segment would
  // silently lose the name.
  const kept = [words[0].slice(0, maxChars)];
  let length = kept[0].length;
  for (const word of words.slice(1)) {
    if (length + 1 + word.length > maxChars) {
      break;
    }
    kept.push(word);
    length += 1 + word.length;
  }
  return kept.join('-').replace(/^-+|-+$/g, '');
}

/** The recruiter-facing base name: `Ada-Lovelace-CV`. */
export function cvFileStem(name?: string | null): string {
  const slugged = slug(name, MAX_NAME_CHARS);
  return slugged && !JUNK_NAMES.has(slugged.toLowerCase()) ? `${slugged}-CV` : 'CV';
}

/** `stem` + layout/language marker + extension: `Ada-Lovelace-CV-ATS-pt-br.pdf`. */
export function cvExportFilename(
  stem: string,
  format: CvExportFormat,
  template: CvTemplate,
  language: CvLanguage,
): string {
  const parts = [stem];
  // The classic/ATS split is a PDF-styling concern, so DOCX never carries it.
  if (format === 'pdf' && template === 'ats') {
    parts.push('ATS');
  }
  if (language !== 'en') {
    parts.push(language.toLowerCase());
  }
  return `${parts.join('-')}.${format}`;
}
