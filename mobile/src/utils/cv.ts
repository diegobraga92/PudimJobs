import { CvVariant, GeneratedCV } from '@/types';

/** i18n key naming the variant that produced a tailored CV (ADR 016, ADR 029). */
export function variantLabelKey(variant: CvVariant): string {
  return variant === 'llm' ? 'cv.variant.llm' : 'cv.variant.rule';
}

/** True when an artifact actually carries CV content. */
export function hasContent(item: GeneratedCV): boolean {
  return !!item.structured_json;
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
