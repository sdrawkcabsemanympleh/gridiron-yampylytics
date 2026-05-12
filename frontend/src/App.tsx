import { useDraftSession } from './hooks/useDraftSession';
import { ConnectScreen } from './components/ConnectScreen';
import { StatusBar } from './components/StatusBar';
import { RecommendationsPanel } from './components/RecommendationsPanel';
import { RosterBar } from './components/RosterBar';

export default function App() {
  const {
    session,
    recommendations,
    recommendationsForPick,
    connectionStatus,
    error,
    createAndConnect,
    disconnect,
  } = useDraftSession();

  const isLoading =
    connectionStatus === 'connecting' ||
    (connectionStatus === 'connected' &&
      session?.is_user_turn === true &&
      recommendations.length === 0);

  if (!session || ((connectionStatus === 'disconnected' || connectionStatus === 'error') && !session.is_complete)) {
    return (
      <div className="flex flex-col h-screen">
        <ConnectScreen
          onCreateAndConnect={createAndConnect}
          error={error}
          isConnecting={connectionStatus === 'connecting'}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-slate-950">
      <StatusBar session={session} connectionStatus={connectionStatus} />

      <RecommendationsPanel
        recommendations={recommendations}
        forPick={recommendationsForPick}
        isUserTurn={session.is_user_turn}
        isLoading={isLoading}
        isComplete={session.is_complete}
        userRoster={session.user_roster}
        currentPick={session.current_pick}
        totalPicks={session.total_picks}
        teamCount={session.team_count}
        userDraftSlot={session.user_draft_slot}
        lastPick={session.picks.length > 0 ? session.picks[session.picks.length - 1] : null}
      />

      <RosterBar roster={session.user_roster} />

      {session.is_complete && (
        <div className="px-4 py-3 bg-slate-900 border-t border-slate-700 text-center">
          <span className="text-slate-400 text-sm">Draft complete — </span>
          <button
            onClick={disconnect}
            className="text-emerald-400 text-sm hover:text-emerald-300 underline"
          >
            start over
          </button>
        </div>
      )}
    </div>
  );
}
