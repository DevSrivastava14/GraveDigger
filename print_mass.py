import json

data = json.load(open('graveyard.json', encoding='utf-8'))
for g in data:
    if g['path'] in ('(6 files)', '(56 files)', '(11 files)'):
        print(f'Mass grave: {g["path"]}')
        print(f'  death_commit: {g["death_commit"]}')
        print(f'  members: {g["members"]}')
        print()