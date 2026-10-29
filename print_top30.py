import json

data = json.load(open('graveyard.json', encoding='utf-8'))
print('Rank  Notability  Lifespan  Mass  Path')
for i, g in enumerate(data, 1):
    mass = 'YES' if g['is_mass'] else 'no'
    print(f'{i:4}  {g["notability"]:10.1f}  {g["lifespan_days"]:8}d  {mass:5}  {g["path"]}')

# Check specific paths
targets = ['flask.py', 'flask/ext/', 'examples/persona/']
print()
for t in targets:
    found = [g for g in data if t in g['path']]
    if found:
        for f in found:
            print(f'FOUND: {f["path"]} (rank {data.index(f)+1})')
    else:
        print(f'NOT FOUND: {t}')