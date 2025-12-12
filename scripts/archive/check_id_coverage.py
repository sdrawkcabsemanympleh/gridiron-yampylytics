import pandas as pd

df = pd.read_csv('../../data/nflverse/player_ids.csv')

# All ID columns
id_cols = [
    'mfl_id', 'sportradar_id', 'fantasypros_id', 'gsis_id', 'pff_id',
    'sleeper_id', 'nfl_id', 'espn_id', 'yahoo_id', 'fleaflicker_id',
    'cbs_id', 'pfr_id', 'cfbref_id', 'rotowire_id', 'rotoworld_id',
    'ktc_id', 'stats_id', 'stats_global_id', 'fantasy_data_id', 'swish_id'
]

total = len(df)
print(f'Total players in crosswalk: {total:,}\n')
print(f'{"ID Column":<20} {"Count":>8} {"Coverage":>10}')
print('=' * 40)

coverage = {}
for col in id_cols:
    if col in df.columns:
        valid = (df[col].notna() & (df[col] != '')).sum()
        pct = valid / total * 100
        coverage[col] = valid
        print(f'{col:<20} {valid:>8,} {pct:>9.1f}%')

# Find which IDs we need to guarantee 100% coverage
print('\n' + '=' * 40)
print('COVERAGE ANALYSIS')
print('=' * 40)

# Check if name + birthdate covers everything
has_name = (df['name'].notna() & (df['name'] != '')).sum()
has_birthdate = (df['birthdate'].notna() & (df['birthdate'] != '')).sum()
has_both_name_birth = ((df['name'].notna() & (df['name'] != '')) &
                       (df['birthdate'].notna() & (df['birthdate'] != ''))).sum()

print(f'\nName coverage: {has_name:,} ({has_name/total*100:.1f}%)')
print(f'Birthdate coverage: {has_birthdate:,} ({has_birthdate/total*100:.1f}%)')
print(f'Name + Birthdate: {has_both_name_birth:,} ({has_both_name_birth/total*100:.1f}%)')

# Check top IDs combined
top_ids = ['gsis_id', 'pfr_id', 'mfl_id', 'espn_id', 'nfl_id']
has_any_top = pd.Series([False] * total)
for col in top_ids:
    if col in df.columns:
        has_any_top |= (df[col].notna() & (df[col] != ''))

print(f'\nHas ANY of {top_ids}: {has_any_top.sum():,} ({has_any_top.sum()/total*100:.1f}%)')
print(f'Missing ALL top IDs: {(~has_any_top).sum():,}')
