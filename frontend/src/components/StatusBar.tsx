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

export function StatusBar({ session, connectionStatus }: Props) {
  const picksUntilUser = (): number | null => {
    if (session.is_user_turn) return 0;
    // Count forward from current_pick through snake order to find user's next pick
    // We don't have full manager list here, so just show pick numbers context
    return null;
  };

  const picksAway = picksUntilUser();

  return (
    <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700 text-sm">
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${STATUS_DOT[connectionStatus]}`} />
        <span className="text-slate-400 font-mono">
          Pick {session.current_pick} / {session.total_picks}
        </span>
      </div>

      <div className="font-semibold">
        {session.is_complete ? (
          <span className="text-slate-400">Draft complete</span>
        ) : session.is_user_turn ? (
          <span className="text-emerald-400">Your pick</span>
        ) : picksAway !== null ? (
          <span className="text-slate-300">Your pick in {picksAway}</span>
        ) : (
          <span className="text-slate-400">Waiting...</span>
        )}
      </div>

      <span className="text-slate-500 font-mono text-xs">{session.draft_id}</span>
    </div>
  );
}
