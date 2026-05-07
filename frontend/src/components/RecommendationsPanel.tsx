import type { PlayerInfo, RecommendationItem } from '../types';

interface Props {
  recommendations: RecommendationItem[];
  forPick: number | null;
  isUserTurn: boolean;
  isLoading: boolean;
  isComplete: boolean;
  userRoster: PlayerInfo[];
}

const POSITION_COLORS: Record<string, string> = {
  QB:  'text-red-400 bg-red-900/30',
  RB:  'text-emerald-400 bg-emerald-900/30',
  WR:  'text-sky-400 bg-sky-900/30',
  TE:  'text-amber-400 bg-amber-900/30',
  K:   'text-slate-400 bg-slate-800',
  DEF: 'text-purple-400 bg-purple-900/30',
};

function positionBadge(pos: string): string {
  return POSITION_COLORS[pos] ?? 'text-slate-300 bg-slate-800';
}

function riskLabel(std: number, mean: number): { label: string; color: string } {
  const cv = mean > 0 ? std / mean : 0;
  if (cv < 0.08) return { label: 'Safe floor', color: 'text-emerald-400' };
  if (cv < 0.15) return { label: 'Balanced', color: 'text-sky-400' };
  return { label: 'High upside', color: 'text-amber-400' };
}

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'];

function CompletedRoster({ roster }: { roster: PlayerInfo[] }) {
  const sorted = [...roster].sort((a, b) => {
    const ai = POSITION_ORDER.indexOf(a.position);
    const bi = POSITION_ORDER.indexOf(b.position);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3">
      <div className="text-xs text-slate-500 mb-3">Final roster — {roster.length} players</div>
      <div className="space-y-1.5">
        {sorted.map((p) => (
          <div
            key={p.player_id}
            className="flex items-center justify-between px-3 py-2 rounded-lg bg-slate-900 border border-slate-800"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <span className={`text-xs font-mono px-1.5 py-0.5 rounded font-semibold shrink-0 ${positionBadge(p.position)}`}>
                {p.position}
              </span>
              <span className="text-sm text-slate-200 truncate">{p.name}</span>
              <span className="text-xs text-slate-600 shrink-0">{p.team}</span>
            </div>
            <span className="text-xs text-slate-500 font-mono shrink-0 ml-2">
              {p.projected_points > 0 ? `${p.projected_points.toFixed(0)} pts` : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function RecommendationsPanel({
  recommendations, forPick, isUserTurn, isLoading, isComplete, userRoster,
}: Props) {
  if (isComplete) {
    return <CompletedRoster roster={userRoster} />;
  }

  if (!isUserTurn && recommendations.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600 text-sm">
        Opponent picking...
      </div>
    );
  }

  if (isLoading || (isUserTurn && recommendations.length === 0)) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 text-slate-500 text-sm">
        <div className="w-4 h-4 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
        Running simulations...
      </div>
    );
  }

  const best = recommendations[0];

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
      {forPick !== null && (
        <div className="text-xs text-slate-600 mb-1">Recommendations for pick {forPick}</div>
      )}
      {recommendations.map((rec, i) => {
        const risk = riskLabel(rec.std_score, rec.mean_score);
        const scorePct = best.mean_score > 0 ? (rec.mean_score / best.mean_score) * 100 : 0;
        return (
          <div
            key={rec.player.player_id}
            className={`rounded-lg p-3 border ${
              i === 0 ? 'border-emerald-700 bg-emerald-950/40' : 'border-slate-700 bg-slate-900/60'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-slate-500 text-xs font-mono w-4 shrink-0">{i + 1}</span>
                <div className="min-w-0">
                  <div className="font-semibold text-slate-100 truncate">{rec.player.name}</div>
                  <div className="text-xs text-slate-400">{rec.player.team}</div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-1 shrink-0">
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded font-semibold ${positionBadge(rec.player.position)}`}>
                  {rec.player.position}
                </span>
                <span className={`text-xs ${risk.color}`}>{risk.label}</span>
              </div>
            </div>

            <div className="mt-2">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-slate-500">Sim score</span>
                <span className="text-slate-300 font-mono">{rec.mean_score.toFixed(1)}</span>
              </div>
              <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${i === 0 ? 'bg-emerald-500' : 'bg-slate-500'}`}
                  style={{ width: `${scorePct}%` }}
                />
              </div>
            </div>

            <div className="mt-1.5 flex gap-3 text-xs text-slate-500">
              <span>ADP {rec.player.adp.toFixed(1)}</span>
              <span>Proj {rec.player.projected_points.toFixed(0)} pts</span>
              <span>{rec.n_simulations} sims</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
