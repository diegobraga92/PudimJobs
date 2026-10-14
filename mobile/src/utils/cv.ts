import { CvVariant, GeneratedCV } from '@/types';

/** i18n key naming the variant that produced a tailored CV (ADR 016). */
export function variantLabelKey(variant: CvVariant): string {
  return variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule';
}

/**
 * True when an artifact actually carries CV content.
 *
 * `generated_cvs.structured_json` is nullable and rows written before ADR 016
 * exist with it NULL — an artifact with nothing to preview, edit or score. Such
 * a row is not a CV, so the panel must never present one as if it were.
 */
export function hasContent(item: GeneratedCV): boolean {
  return !!item.structured_json;
}
