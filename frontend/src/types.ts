export interface PlayerInfo {
  player_id: string;
  name: string;
  position: string;
  team: string;
  projected_points: number;
  adp: number;
}

export interface RecommendationItem {
  player: PlayerInfo;
  mean_score: number;
  std_score: number;
  n_simulations: number;
}

export interface PickRecord {
  overall_pick: number;
  round: number;
  pick_in_round: number;
  manager_id: string;
  player_id: string;
  player_name: string;
  position: string;
  team: string;
}

export interface SessionState {
  draft_id: string;
  current_pick: number;
  total_picks: number;
  is_user_turn: boolean;
  is_complete: boolean;
  picks_replayed: number;
  picks: PickRecord[];
  user_roster: PlayerInfo[];
}

// WebSocket event shapes (type field used to discriminate)
export interface PickMadeEvent {
  type: 'pick_made';
  overall_pick: number;
  round: number;
  pick_in_round: number;
  manager_id: string;
  player_id: string;
  player_name: string;
  position: string;
  team: string;
  is_user_pick: boolean;
  current_pick: number;
  is_user_turn: boolean;
}

export interface RecommendationsEvent {
  type: 'recommendations';
  for_pick: number;
  candidates: RecommendationItem[];
}

export interface DraftCompleteEvent {
  type: 'draft_complete';
}

export type DraftEvent = PickMadeEvent | RecommendationsEvent | DraftCompleteEvent;

export interface SleeperDraftSummary {
  draft_id: string;
  type: string;
  status: 'pre_draft' | 'drafting' | 'complete' | string;
  season: string;
  start_time: number | null;
  settings: { teams?: number; rounds?: number };
}
