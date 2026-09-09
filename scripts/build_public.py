"""Build a public-only directory; never publish the repository root."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'dist'

def build():
    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.mkdir()
    for pattern in ('*.html', '*.css', '*.js', 'robots.txt', 'sitemap.xml'):
        for source in ROOT.glob(pattern):
            shutil.copy2(source, DEST / source.name)
    for name in ('assets', 'products', 'legal'):
        shutil.copytree(ROOT / name, DEST / name,
                        ignore=shutil.ignore_patterns('.*', '*.py', '*.sqlite3'))
    print('Public files prepared in dist; server, credentials and order data excluded.')

if __name__ == '__main__':
    build()
