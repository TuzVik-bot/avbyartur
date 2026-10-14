#!/usr/bin/env python3
"""Enter a key locally without putting it into chat, argv, logs or Git."""
import getpass
import json
import subprocess
import sys

REMOTE = r'''
import json, os, pathlib, re, sys
p = json.load(sys.stdin)
root = pathlib.Path('/home/suite/apps/avtorinok').resolve()
env = root / '.env'
if not (root / 'web/src/app/api/assistant/route.ts').exists():
    raise SystemExit('Сначала задеплойте релиз помощника.')
values = {
 'ASSISTANT_API_KEY': p['key'],
 'ASSISTANT_BASE_URL': 'https://openrouter.ai/api/v1',
 'ASSISTANT_MODEL': p['model'],
}
content = env.read_text()
for name, value in values.items():
    line = name + '=' + value
    pattern = re.compile(r'^' + name + r'=.*$', re.M)
    content = pattern.sub(lambda _: line, content) if pattern.search(content) else content.rstrip() + '\n' + line + '\n'
temporary = env.with_name('.env.assistant-new')
fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write(content)
os.replace(temporary, env)
os.chmod(env, 0o600)
print('Ключ установлен на VPS; значение не выводится.')
'''

def main():
    model = input('Бесплатная модель [google/gemma-4-31b-it:free]: ').strip() or 'google/gemma-4-31b-it:free'
    if not re_valid(model):
        raise SystemExit('Допускается только идентификатор модели OpenRouter с суффиксом :free.')
    key = getpass.getpass('OpenRouter API-ключ (ввод скрыт): ').strip()
    if not key.startswith('sk-or-') or any(c.isspace() for c in key) or len(key) > 512:
        raise SystemExit('Неверный формат ключа OpenRouter.')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'fortebit-prod', 'python3', '-c', __import__('shlex').quote(REMOTE)], input=json.dumps({'key': key, 'model': model}), text=True)
    if result.returncode:
        raise SystemExit('Установка не завершена; ключ не сохранён локально.')
    key = ''
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'fortebit-prod', 'cd /home/suite/apps/avtorinok && docker compose -p avtorinok up -d --no-deps --no-build --wait web'])
    sys.exit(result.returncode)

def re_valid(model):
    import re
    return bool(re.fullmatch(r'[a-z0-9._-]+/[a-z0-9._-]+:free', model))

if __name__ == '__main__':
    main()
