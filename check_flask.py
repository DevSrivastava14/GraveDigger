import json
from gravedigger.exhume import find_deaths, enrich, exhume, _get_root_commit_date
from pathlib import Path

repo = Path(r'..\flask')
root_date = _get_root_commit_date(repo)
print(f"Root commit date: {root_date}")

deaths = find_deaths(repo)
graves, skipped = enrich(repo, deaths, root_date)

# Find flask.py
flask_py = next((g for g in graves if g.path == 'flask.py'), None)
if flask_py:
    print(f'flask.py Grave (with founder bonus):')
    print(f'  born_date: {flask_py.born_date}')
    print(f'  death_date: {flask_py.death_date}')
    print(f'  lifespan_days: {flask_py.lifespan_days}')
    print(f'  lines_at_death: {flask_py.lines_at_death}')
    print(f'  notability: {flask_py.notability:.1f}')
    print(f'  is_founder: {(flask_py.born_date - root_date).days <= 30}')
    print(f'  days from root: {(flask_py.born_date - root_date).days}')
    
    # Rank before cap
    all_graves = sorted(graves, key=lambda g: g.notability, reverse=True)
    rank = all_graves.index(flask_py) + 1
    print(f'  rank before cap: {rank}')
    print(f'  total graves before cap: {len(all_graves)}')
else:
    print('flask.py not found in graves')

# Also run full exhume to see top 30
print("\n--- Full exhume top 30 ---")
result = exhume(repo, limit=30)
for i, g in enumerate(result, 1):
    mass = ' [MASS]' if g.is_mass else ''
    print(f'  {i:2d}. {g.notability:10.1f}  {g.lifespan_days:4d}d  {g.lines_at_death:4d} lines  {g.path}{mass}')

# Check if flask.py is in top 30
in_top30 = any(g.path == 'flask.py' for g in result)
print(f"\nflask.py in top 30: {in_top30}")