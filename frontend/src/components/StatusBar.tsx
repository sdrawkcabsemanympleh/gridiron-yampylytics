import type { ConnectionStatus } from '../hooks/useDraftSession';
import type { SessionState } from '../types';

interface Props {
  session: SessionState;
  connectionStatus: ConnectionStatus;
}

const STATUS_DOT: Record<ConnectionStatus, string> = {
  connected: 'bg-green-500',
  connecting: 'bg-yellow-400 animate-pulse',
  disconnected: 'bg-slate-500',
  error: 'bg-red-500',
};

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

export function StatusBar({ session, connectionStatus }: Props) {
  const picksAway = session.is_user_turn
    ? 0
    : picksUntilUserTurn(session.current_pick, session.team_count, session.user_draft_slot);

  const round = Math.ceil(session.current_pick / session.team_count);

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700 text-sm">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${STATUS_DOT[connectionStatus]}`} />
        <span className="text-slate-400 font-mono">
          Rd {round} · Pick {session.current_pick}/{session.total_picks}
        </span>
      </div>

      <div className="font-semibold">
        {session.is_complete ? (
          <span className="text-slate-400">Draft complete</span>
        ) : session.is_user_turn ? (
          <span className="text-emerald-400">Your pick</span>
        ) : picksAway === 1 ? (
          <span className="text-amber-400">Your pick next</span>
        ) : (
          <span className="text-slate-400">Your pick in {picksAway}</span>
        )}
      </div>

      <span className="text-slate-500 font-mono text-xs">{session.draft_id}</span>
    </div>
  );
}
