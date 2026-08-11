const fs = require('node:fs');
const path = require('node:path');

const assetsDirectory = path.join(__dirname, '..', 'dist', 'assets');
const javascriptAssets = fs
  .readdirSync(assetsDirectory)
  .filter((name) => name.endsWith('.js'));

if (javascriptAssets.length === 0) {
  throw new Error('No production JavaScript assets were found to validate.');
}

const forbiddenIdentifiers = [
  'ADMITLY_RELEASE',
  'ADMITLY_DIST',
];

for (const asset of javascriptAssets) {
  const source = fs.readFileSync(path.join(assetsDirectory, asset), 'utf8');
  for (const identifier of forbiddenIdentifiers) {
    if (source.includes(identifier)) {
      throw new Error(`Unresolved ${identifier} identifier found in ${asset}.`);
    }
  }
}

console.log(`Release injection check passed for ${javascriptAssets.length} JavaScript asset(s).`);
