import { CvVariant, GeneratedCV } from '@/types';

/** Longest name slug a filename carries; the backend uses the same cap (ADR 030). */
const MAX_NAME_CHARS = 48;

/** A parser can read a section heading as the candidate's name (ADR 030). */
const JUNK_NAMES = new Set(['cv', 'curriculum', 'curriculum-vitae', 'curriculo', 'resume']);

/** i18n key naming the variant that produced a tailored CV (ADR 016, ADR 029). */
export function variantLabelKey(variant: CvVariant): string {
  return variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule';
}

/** True when an artifact actually carries CV content. */
export function hasContent(item: GeneratedCV): boolean {
  return !!item.structured_json;
}

/**
 * The recruiter-facing base name of a CV export (ADR 030): `Ada-Lovelace-CV`.
 *
 * Mirrors `backend/app/services/cv_filename.py`, which names every *stored*
 * artifact (its `file_stem`); this is for the editor, whose render is never
 * persisted. Accents fold to ASCII because an accented capital becomes `_` or
 * `%C3%A9` on the way through a share sheet, and a junk name (a parser reading
 * a heading as the candidate) must not produce `Curriculum-Vitae-CV.pdf`.
 */
export function cvFileStem(name?: string | null): string {
  const ascii = (name ?? '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  const words = ascii
    .replace(/\([^)]*\)|\[[^\]]*\]/g, ' ')
    .replace(/[^A-Za-z0-9]+/g, ' ')
    .split(' ')
    .filter(Boolean);

  const kept = words.length ? [words[0].slice(0, MAX_NAME_CHARS)] : [];
  let length = kept.length ? kept[0].length : 0;
  for (const word of words.slice(1)) {
    if (length + 1 + word.length > MAX_NAME_CHARS) {
      break;
    }
    kept.push(word);
    length += 1 + word.length;
  }

  const slug = kept.join('-').replace(/^-+|-+$/g, '');
  return slug && !JUNK_NAMES.has(slug.toLowerCase()) ? `${slug}-CV` : 'CV';
}

/**
 * The artifact a CV panel opens on (ADR 029): the one recorded as sent with the
 * application, else the AI rewrite, else whatever the API returned first.
 *
 * The backend sorts a run AI-first, so this is mostly about the recorded choice:
 * once the user picked a variant with *Use this one*, the panel must open on that
 * one no matter how the list is ordered.
 */
export function defaultArtifact(
  artifacts: GeneratedCV[],
  linkedCvId?: string | null,
): GeneratedCV | null {
  const linked = linkedCvId ? artifacts.find((item) => item.id === linkedCvId) : undefined;
  const llm = artifacts.find((item) => item.variant === 'llm');
  return linked ?? llm ?? artifacts[0] ?? null;
}
