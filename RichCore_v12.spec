# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(globals().get('SPECPATH', '.')).resolve()
AIASIST_DIR = ROOT.parent / "Скрипти" / "AiAsist"
AIASIST_KNOWLEDGE_DIR = AIASIST_DIR / "Освіта нейронки"
REQUESTS_HIDDENIMPORTS = (
    collect_submodules('requests')
    + collect_submodules('urllib3')
    + collect_submodules('charset_normalizer')
    + collect_submodules('idna')
    + ['certifi']
)
DATA_FILES = [
    ('assets', 'assets'),
    ('ai', 'ai'),
    ('src\\atools\\ui\\main_window_full.pyc', 'atools\\ui'),
]


def add_data_if_exists(source, target):
    path = Path(source)
    if path.exists():
        DATA_FILES.append((str(path), target))


add_data_if_exists(AIASIST_DIR / 'ukrainegta_bot.py', 'internal_ai/ai_asist')
add_data_if_exists(AIASIST_DIR / 'qa_cache.json', 'internal_ai/ai_asist')
add_data_if_exists(AIASIST_KNOWLEDGE_DIR / 'Правила.txt', 'internal_ai/ai_asist/Освіта нейронки')
add_data_if_exists(AIASIST_KNOWLEDGE_DIR / 'Посібник адміністратора.txt', 'internal_ai/ai_asist/Освіта нейронки')

a = Analysis(
    ['launcher.py'],
    pathex=['.', 'src'],
    binaries=[],
    datas=DATA_FILES,
    hiddenimports=REQUESTS_HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='RichCore_v12',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\iconka.ico'],
    uac_admin=True,
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='RichCore_v12',
)
