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

function StatusBanner({
  isUserTurn, isLoading, currentPick, totalPicks, teamCount, userDraftSlot, lastPick,
}: {
  isUserTurn: boolean;
  isLoading: boolean;
  currentPick: number;
  totalPicks: number;
  teamCount: number;
  userDraftSlot: number;
  lastPick: PickRecord | null;
}) {
  const round = Math.ceil(currentPick / teamCount);
  const pickInRound = ((currentPick - 1) % teamCount) + 1;

  if (isUserTurn && isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-800 bg-emerald-950/20">
        <div className="w-3 h-3 border-2 border-emerald-700 border-t-emerald-400 rounded-full animate-spin shrink-0" />
        <span className="text-xs text-emerald-400 font-medium">
          Your pick — running simulations for pick {currentPick}…
        </span>
      </div>
    );
  }

  if (isUserTurn) {
    return (
      <div className="px-3 py-2 border-b border-slate-800 bg-emerald-950/20">
        <span className="text-xs text-emerald-400 font-medium">Your pick — Round {round}</span>
      </div>
    );
  }

  const picksAway = picksUntilUserTurn(currentPick, teamCount, userDraftSlot);
  return (
    <div className="px-3 py-2 border-b border-slate-800 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-xs text-slate-500 min-w-0">
        <span>Round {round} · Pick {pickInRound}/{teamCount} · Overall {currentPick}/{totalPicks}</span>
        {lastPick && (
          <span className="hidden sm:inline truncate text-slate-600">
            — last:{' '}
            <span className={`font-mono px-1 py-0.5 rounded text-[10px] font-semibold ${positionBadge(lastPick.position)}`}>
              {lastPick.position}
            </span>{' '}
            {lastPick.player_name}
          </span>
        )}
      </div>
      <span className={`text-xs font-medium shrink-0 ${picksAway <= 2 ? 'text-amber-400' : 'text-slate-500'}`}>
        {picksAway === 0 ? 'Your pick now' : picksAway === 1 ? 'Next pick' : `${picksAway} picks away`}
      </span>
    </div>
  );
}

function CandidateCard({ rec, rank, isSimulating, allStds, scaleMin, scaleRange }: {
  rec: RecommendationItem;
  rank: number;
  isSimulating: boolean;
  allStds: number[];
  scaleMin: number;
  scaleRange: number;
}) {
  const hasSimScores = rec.n_simulations > 0;
  const risk = hasSimScores ? riskLabel(rec.std_score, allStds) : null;
  const bandLeft = hasSimScores ? ((rec.mean_score - rec.std_score - scaleMin) / scaleRange) * 100 : 0;
  const bandWidth = hasSimScores ? Math.max(1, (rec.std_score * 2 / scaleRange) * 100) : 0;
  const meanLeft = hasSimScores ? ((rec.mean_score - scaleMin) / scaleRange) * 100 : 0;

  return (
    <div
      className={`rounded-lg p-3 border ${
        rank === 0 ? 'border-emerald-700 bg-emerald-950/40' : 'border-slate-700 bg-slate-900/60'
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-slate-500 text-xs font-mono w-4 shrink-0">{rank + 1}</span>
          <div className="min-w-0">
            <div className="font-semibold text-slate-100 truncate">{rec.player.name}</div>
            <div className="text-xs text-slate-400">{rec.player.team}</div>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded font-semibold ${positionBadge(rec.player.position)}`}>
            {rec.player.position}
          </span>
          {risk && <span className={`text-xs ${risk.color}`}>{risk.label}</span>}
        </div>
      </div>

      <div className="mt-2">
        <div className="flex justify-between text-xs mb-1">
          <span className="text-slate-500">Sim score</span>
          {hasSimScores ? (
            <span className="font-mono">
              <span className="text-slate-300">{rec.mean_score.toFixed(0)}</span>
              <span className="text-slate-600"> ±{rec.std_score.toFixed(0)}</span>
            </span>
          ) : (
            <span className="text-slate-600 italic text-[11px]">{isSimulating ? 'simulating…' : '—'}</span>
          )}
        </div>
        <div className="relative h-3 bg-slate-800 rounded-full overflow-hidden">
          {hasSimScores ? (
            <>
              <div
                className={`absolute h-full ${rank === 0 ? 'bg-emerald-500/35' : 'bg-emerald-500/20'}`}
                style={{ left: `${bandLeft}%`, width: `${bandWidth}%` }}
              />
              <div
                className={`absolute top-0 h-full w-px ${rank === 0 ? 'bg-emerald-400' : 'bg-emerald-500/60'}`}
                style={{ left: `${meanLeft}%` }}
              />
            </>
          ) : (
            <div className="absolute inset-0 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 animate-pulse" />
          )}
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
        {hasSimScores && <span>{rec.n_simulations} sims</span>}
      </div>
    </div>
  );
}

export function RecommendationsPanel({
  recommendations, forPick, isUserTurn, isLoading, isComplete, userRoster,
  currentPick, totalPicks, teamCount, userDraftSlot, lastPick,
}: Props) {
  if (isComplete) {
    return <CompletedRoster roster={userRoster} />;
  }

  // No candidates yet (very first connect before any pick events)
  if (recommendations.length === 0) {
    return (
      <div className="flex-1 flex flex-col">
        <StatusBanner
          isUserTurn={isUserTurn} isLoading={isLoading}
          currentPick={currentPick} totalPicks={totalPicks}
          teamCount={teamCount} userDraftSlot={userDraftSlot} lastPick={lastPick}
        />
        <div className="flex-1 flex items-center justify-center gap-2 text-slate-600 text-sm">
          <div className="w-4 h-4 border-2 border-slate-700 border-t-slate-500 rounded-full animate-spin" />
          Loading…
        </div>
      </div>
    );
  }

  const isSimulating = isUserTurn && recommendations.every((r) => r.n_simulations === 0);
  const simRecs = recommendations.filter((r) => r.n_simulations > 0);
  const allStds = simRecs.map((r) => r.std_score);
  const scaleMin = simRecs.length > 0 ? Math.min(...simRecs.map((r) => r.mean_score - r.std_score)) : 0;
  const scaleMax = simRecs.length > 0 ? Math.max(...simRecs.map((r) => r.mean_score + r.std_score)) : 1;
  const scaleRange = scaleMax - scaleMin || 1;

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <StatusBanner
        isUserTurn={isUserTurn} isLoading={isLoading}
        currentPick={currentPick} totalPicks={totalPicks}
        teamCount={teamCount} userDraftSlot={userDraftSlot} lastPick={lastPick}
      />
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {forPick !== null && !isSimulating && (
          <div className="text-xs text-slate-600 mb-1">Recommendations for pick {forPick}</div>
        )}
        {recommendations.map((rec, i) => (
          <CandidateCard
            key={rec.player.player_id}
            rec={rec}
            rank={i}
            isSimulating={isSimulating}
            allStds={allStds}
            scaleMin={scaleMin}
            scaleRange={scaleRange}
          />
        ))}
      </div>
    </div>
  );
}
