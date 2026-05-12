import type { PlayerInfo, PickRecord, RecommendationItem } from '../types';

interface Props {
  recommendations: RecommendationItem[];
  forPick: number | null;
  isUserTurn: boolean;
  isLoading: boolean;
  isComplete: boolean;
  userRoster: PlayerInfo[];
  currentPick: number;
  totalPicks: number;
  teamCount: number;
  userDraftSlot: number;
  lastPick: PickRecord | null;
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

function signedValueColor(val: number): string {
  if (val > 0) return 'text-emerald-400';
  if (val < 0) return 'text-rose-400';
  return 'text-slate-400';
}

function riskLabel(std: number, allStds: number[]): { label: string; color: string } {
  const sorted = [...allStds].sort((a, b) => a - b);
  const n = sorted.length;
  const lowCutoff = sorted[Math.floor(n / 3)];
  const highCutoff = sorted[Math.floor(2 * n / 3)];
  if (std <= lowCutoff) return { label: 'Safe floor', color: 'text-emerald-400' };
  if (std <= highCutoff) return { label: 'Balanced', color: 'text-sky-400' };
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

function picksUntilUserTurn(currentPick: number, teamCount: number, userSlot: number): number {
  const pickInRound = ((currentPick - 1) % teamCount) + 1;
  const round = Math.ceil(currentPick / teamCount);
  const userPositionInRound = round % 2 === 1 ? userSlot : teamCount - userSlot + 1;
  if (userPositionInRound >= pickInRound) return userPositionInRound - pickInRound;
  const picksLeftThisRound = teamCount - pickInRound + 1;
  const nextRound = round + 1;
  const userPositionNextRound = nextRound % 2 === 1 ? userSlot : teamCount - userSlot + 1;
  return picksLeftThisRound + userPositionNextRound - 1;
}

export function RecommendationsPanel({
  recommendations, forPick, isUserTurn, isLoading, isComplete, userRoster,
  currentPick, totalPicks, teamCount, userDraftSlot, lastPick,
}: Props) {
  if (isComplete) {
    return <CompletedRoster roster={userRoster} />;
  }

  if (!isUserTurn && recommendations.length === 0) {
    const picksAway = picksUntilUserTurn(currentPick, teamCount, userDraftSlot);
    const round = Math.ceil(currentPick / teamCount);
    const pickInRound = ((currentPick - 1) % teamCount) + 1;
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-sm px-6">
        <div className="text-slate-500">
          Round {round} · Pick {pickInRound}/{teamCount} · Overall {currentPick}/{totalPicks}
        </div>
        {lastPick && (
          <div className="text-xs text-slate-600 text-center">
            Last pick:{' '}
            <span className={`font-semibold ${positionBadge(lastPick.position)} px-1.5 py-0.5 rounded font-mono`}>
              {lastPick.position}
            </span>{' '}
            <span className="text-slate-400">{lastPick.player_name}</span>
            <span className="text-slate-600"> · {lastPick.team}</span>
          </div>
        )}
        <div className={`font-semibold ${picksAway <= 2 ? 'text-amber-400' : 'text-slate-500'}`}>
          {picksAway === 0 ? 'Your pick now' : picksAway === 1 ? 'Your pick next' : `Your pick in ${picksAway}`}
        </div>
      </div>
    );
  }

  if (isLoading || (isUserTurn && recommendations.length === 0)) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2 text-slate-500 text-sm">
        <div className="w-4 h-4 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
        Running simulations for pick {currentPick}...
      </div>
    );
  }

  const allStds = recommendations.map((r) => r.std_score);
  const scaleMin = Math.min(...recommendations.map((r) => r.mean_score - r.std_score));
  const scaleMax = Math.max(...recommendations.map((r) => r.mean_score + r.std_score));
  const scaleRange = scaleMax - scaleMin || 1;

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
      {forPick !== null && (
        <div className="text-xs text-slate-600 mb-1">Recommendations for pick {forPick}</div>
      )}
      {recommendations.map((rec, i) => {
        const risk = riskLabel(rec.std_score, allStds);
        const bandLeft = ((rec.mean_score - rec.std_score - scaleMin) / scaleRange) * 100;
        const bandWidth = Math.max(1, (rec.std_score * 2 / scaleRange) * 100);
        const meanLeft = ((rec.mean_score - scaleMin) / scaleRange) * 100;
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
                <span className="font-mono">
                  <span className="text-slate-300">{rec.mean_score.toFixed(0)}</span>
                  <span className="text-slate-600"> ±{rec.std_score.toFixed(0)}</span>
                </span>
              </div>
              <div className="relative h-3 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`absolute h-full ${i === 0 ? 'bg-emerald-500/35' : 'bg-emerald-500/20'}`}
                  style={{ left: `${bandLeft}%`, width: `${bandWidth}%` }}
                />
                <div
                  className={`absolute top-0 h-full w-px ${i === 0 ? 'bg-emerald-400' : 'bg-emerald-500/60'}`}
                  style={{ left: `${meanLeft}%` }}
                />
              </div>
            </div>

            <div className="mt-2 grid grid-cols-4 gap-1 text-xs">
              <div className="flex flex-col items-center bg-slate-800/60 rounded px-1.5 py-1">
                <span className="text-slate-500 uppercase tracking-wide text-[10px]">VOR</span>
                <span className={`font-mono ${signedValueColor(rec.vor)}`}>{rec.vor >= 0 ? '+' : ''}{rec.vor.toFixed(1)}</span>
              </div>
              <div className="flex flex-col items-center bg-slate-800/60 rounded px-1.5 py-1">
                <span className="text-slate-500 uppercase tracking-wide text-[10px]">VONA</span>
                <span className={`font-mono ${signedValueColor(rec.vona)}`}>{rec.vona >= 0 ? '+' : ''}{rec.vona.toFixed(1)}</span>
              </div>
              <div className="flex flex-col items-center bg-slate-800/60 rounded px-1.5 py-1">
                <span className="text-slate-500 uppercase tracking-wide text-[10px]">Scarcity</span>
                <span className="text-slate-300 font-mono">{(rec.scarcity_score * 100).toFixed(0)}%</span>
              </div>
              <div className="flex flex-col items-center bg-slate-800/60 rounded px-1.5 py-1">
                <span className="text-slate-500 uppercase tracking-wide text-[10px]">Need</span>
                <span className="text-slate-300 font-mono">{(rec.roster_need_score * 100).toFixed(0)}%</span>
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
