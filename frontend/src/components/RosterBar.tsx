import type { PlayerInfo } from '../types';

interface Props {
  roster: PlayerInfo[];
}

const POSITION_ORDER = ['QB', 'RB', 'WR', 'TE', 'K', 'DEF'];

const POSITION_COLORS: Record<string, string> = {
  QB: 'border-red-700 text-red-300',
  RB: 'border-emerald-700 text-emerald-300',
  WR: 'border-sky-700 text-sky-300',
  TE: 'border-amber-700 text-amber-300',
  K:  'border-slate-600 text-slate-400',
  DEF: 'border-purple-700 text-purple-300',
};

export function RosterBar({ roster }: Props) {
  const byPosition = POSITION_ORDER.reduce<Record<string, PlayerInfo[]>>((acc, pos) => {
    acc[pos] = roster.filter((p) => p.position === pos);
    return acc;
  }, {});

  const bench = roster.filter((p) => !POSITION_ORDER.includes(p.position));

  if (roster.length === 0) {
    return (
      <div className="px-4 py-2 border-t border-slate-700 text-xs text-slate-600 text-center">
        No picks yet
      </div>
    );
  }

  return (
    <div className="border-t border-slate-700 px-3 py-2">
      <div className="text-xs text-slate-600 mb-1.5">Your roster</div>
      <div className="flex flex-wrap gap-1.5">
        {POSITION_ORDER.flatMap((pos) =>
          byPosition[pos].map((p) => (
            <div
              key={p.player_id}
              className={`flex items-center gap-1 border rounded px-1.5 py-0.5 text-xs ${POSITION_COLORS[pos] ?? 'border-slate-600 text-slate-400'}`}
            >
              <span className="font-mono opacity-60">{pos}</span>
              <span className="truncate max-w-20">{p.name.split(' ').at(-1)}</span>
            </div>
          )),
        )}
        {bench.map((p) => (
          <div
            key={p.player_id}
            className="flex items-center gap-1 border border-slate-700 rounded px-1.5 py-0.5 text-xs text-slate-500"
          >
            <span className="font-mono opacity-60">{p.position}</span>
            <span className="truncate max-w-20">{p.name.split(' ').at(-1)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
