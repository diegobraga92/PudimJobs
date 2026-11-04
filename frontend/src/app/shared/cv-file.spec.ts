import { cvExportFilename, cvFileStem } from './cv-file';

describe('cvFileStem', () => {
  it('names the candidate and the document, in that order (ADR 030)', () => {
    expect(cvFileStem('Ada Lovelace')).toBe('Ada-Lovelace-CV');
  });

  it('strips accents without losing the capitalisation', () => {
    expect(cvFileStem('José Conceição')).toBe('Jose-Conceicao-CV');
  });

  it('drops punctuation and collapses runs of separators', () => {
    expect(cvFileStem('Ada  --  Lovelace!!')).toBe('Ada-Lovelace-CV');
  });

  it('falls back to the bare document when there is no name', () => {
    expect(cvFileStem('')).toBe('CV');
    expect(cvFileStem(null)).toBe('CV');
    expect(cvFileStem(undefined)).toBe('CV');
  });

  it('never doubles the document type for a junk name', () => {
    expect(cvFileStem('Curriculum Vitae')).toBe('CV');
    expect(cvFileStem('Resume')).toBe('CV');
  });

  it('caps a long name on a word boundary', () => {
    const stem = cvFileStem('Maximiliano de Albuquerque Nascimento Filho Sobrinho');
    expect(stem.endsWith('-CV')).toBeTrue();
    expect(stem.length).toBeLessThanOrEqual(48 + '-CV'.length);
  });
});

describe('cvExportFilename', () => {
  it('marks the ATS layout on a PDF only', () => {
    expect(cvExportFilename('Ada-Lovelace-CV', 'pdf', 'ats', 'en')).toBe(
      'Ada-Lovelace-CV-ATS.pdf',
    );
    expect(cvExportFilename('Ada-Lovelace-CV', 'docx', 'ats', 'en')).toBe('Ada-Lovelace-CV.docx');
  });

  it('marks a translated copy so it cannot overwrite the English one', () => {
    expect(cvExportFilename('Ada-Lovelace-CV', 'pdf', 'classic', 'pt-BR')).toBe(
      'Ada-Lovelace-CV-pt-br.pdf',
    );
    expect(cvExportFilename('Ada-Lovelace-CV', 'pdf', 'ats', 'pt-BR')).toBe(
      'Ada-Lovelace-CV-ATS-pt-br.pdf',
    );
  });
});
