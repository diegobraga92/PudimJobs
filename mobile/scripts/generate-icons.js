/**
 * Generates the mobile app icon / splash / adaptive-icon PNGs from the web
 * brand mark (frontend/src/assets/icons/icon-512.svg). Run from anywhere:
 *
 *   node mobile/scripts/generate-icons.js
 *
 * Requires `sharp` (a devDependency of the mobile package).
 */
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const ROOT = path.join(__dirname, '..', '..');
const OUT = path.join(ROOT, 'mobile', 'assets');

// The white briefcase glyph, extracted from the web brand mark (the navy
// rounded-rect background is rendered separately / via the splash background).
const GLYPH = `
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <g fill="none" stroke="#ffffff" stroke-width="28" stroke-linecap="round" stroke-linejoin="round">
    <path d="M256 340V140a22 22 0 0 0-22-22h-36a22 22 0 0 0-22 22v200"/>
    <rect x="76" y="160" width="360" height="212" rx="32"/>
  </g>
</svg>`;

// Glyph scaled to ~60% and centered — fits the adaptive-icon safe zone.
const GLYPH_CENTERED = GLYPH.replace(
  '<g fill="none"',
  '<g transform="translate(102.4 102.4) scale(0.6)" fill="none"',
);

const NAVY_BG = `
<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024">
  <rect width="1024" height="1024" fill="#1e3a5f"/>
</svg>
`;

async function render(svg, fileName, width, height) {
  await sharp(Buffer.from(svg), { density: 300 })
    .resize(width, height, { fit: 'contain', background: { r: 0, g: 0, b: 0, alpha: 0 } })
    .png()
    .toFile(path.join(OUT, fileName));
  console.log(`  wrote ${fileName}`);
}

async function main() {
  const brand = fs.readFileSync(
    path.join(ROOT, 'frontend', 'src', 'assets', 'icons', 'icon-512.svg'),
    'utf8',
  );

  fs.mkdirSync(OUT, { recursive: true });

  console.log('Generating icons…');
  await render(brand, 'icon.png', 1024, 1024); // launcher icon
  await render(brand, 'favicon.png', 48, 48); // web favicon
  await render(GLYPH, 'splash-icon.png', 512, 512); // splash logo (navy splash bg)
  await render(GLYPH_CENTERED, 'android-icon-foreground.png', 1024, 1024); // adaptive fg
  await render(GLYPH_CENTERED, 'android-icon-monochrome.png', 1024, 1024); // themed icon
  await render(NAVY_BG, 'android-icon-background.png', 1024, 1024); // adaptive bg
  console.log('Done.');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
