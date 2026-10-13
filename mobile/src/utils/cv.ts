import { CvVariant } from '@/types';

/** i18n key naming the variant that produced a tailored CV (ADR 016). */
export function variantLabelKey(variant: CvVariant): string {
  return variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule';
}
