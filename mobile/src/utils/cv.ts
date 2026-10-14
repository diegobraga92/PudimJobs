import { CvVariant, GeneratedCV } from '@/types';

/** i18n key naming the variant that produced a tailored CV (ADR 016). */
export function variantLabelKey(variant: CvVariant): string {
  return variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule';
}

/** True when an artifact actually carries CV content. */
export function hasContent(item: GeneratedCV): boolean {
  return !!item.structured_json;
}
