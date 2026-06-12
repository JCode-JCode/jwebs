# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
_DEPS = {
    'brotli': False,
    'chardet': False,
    'charset_normalizer': False,
    'vaderSentiment': False,
    'deep_translator': False,
    'price_parser': False,
    'mmh3': False,
    'cachetools': False,
    'langdetect': False,
    'ftfy': False,
    'unidecode': False,
    'dateparser': False,
    'yaml': False,
    'msgpack': False,
}

def _check_dep(name: str) -> bool:
    return _DEPS.get(name, False)

def _try_imports():
    imports = {
        'brotli': 'brotli',
        'chardet': 'chardet',
        'charset_normalizer': ('charset_normalizer', 'from_bytes'),
        'vaderSentiment': ('vaderSentiment.vaderSentiment', 'SentimentIntensityAnalyzer'),
        'deep_translator': ('deep_translator', 'GoogleTranslator'),
        'price_parser': ('price_parser', 'Price'),
        'mmh3': 'mmh3',
        'cachetools': 'cachetools',
        'langdetect': 'langdetect',
        'ftfy': 'ftfy',
        'unidecode': ('unidecode', 'unidecode'),
        'dateparser': 'dateparser',
        'yaml': 'yaml',
        'msgpack': 'msgpack',
    }
    for key, mod in imports.items():
        try:
            if isinstance(mod, tuple):
                __import__(mod[0])
            else:
                __import__(mod)
            _DEPS[key] = True
        except ImportError:
            pass

_try_imports()