
nflverse_dir = base_dir / 'data' / 'nflverse'

# Dataset configurations: (file, join_column, name_column_for_fallback)
datasets = [
    (nflverse_dir / 'combine.csv', 'pfr_id', 'pfr_id', 'player_name'),
    (nflverse_dir / 'rosters.csv', 'gsis_id', 'gsis_id', 'full_name'),
    (nflverse_dir / 'draft_picks.csv', 'pfr_player_id', 'pfr_id', 'pfr_player_name'),
    (nflverse_dir / 'player_stats.csv', 'player_id', 'player_display_name'),
    (nflverse_dir / 'injuries.csv', 'gsis_id', 'full_name'),
    # (nflverse_dir / 'depth_charts.csv', 'gsis_id', 'full_name'),  # TODO:  Add to split depth chart files
]

where_statement_mapping = {
    'combine': 'u.pfr_id = dt.pfr_id OR (u.merge_name = ',
}
